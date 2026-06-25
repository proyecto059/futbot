# Pipeline 5 — Documentación de Arquitectura

## 1. Resumen ejecutivo

Pipeline 5 es el controlador principal del robot **futbot**. Su objetivo es **buscar y perseguir una pelota naranja** usando visión por computadora (HSV + YOLO). Se ejecuta como un loop infinito que:

1. Captura un frame de la cámara
2. Detecta si hay pelota (y la filtra para evitar falsos positivos)
3. Decide el estado de la máquina de estados (FSM)
4. Calcula velocidades de motores y las envía al hardware

Pipeline 5 depende de dos servicios externos:
- **HybridVisionService** (`src/src/vision/`) — detección de pelota por HSV clásico + YOLO ONNX
- **MotorService** (`src/motors/`) — control de motores vía I2C/Serial

## 2. Arquitectura general

```
┌──────────┐    frame     ┌────────────────────┐    ball dict    ┌──────────────────┐    (v_left, v_right, dur_ms)    ┌──────────────┐
│  Cámara  │─────────────►│ HybridVisionService │───────────────►│ Pipeline5Service │───────────────────────────────►│ MotorService │
│  IMX219  │              │  (HSV + YOLO ONNX)  │                │   (FSM + ops)    │                                │  (I2C/PWM)   │
└──────────┘              └────────────────────┘                └──────────────────┘                                └──────────────┘
                                                                        │
                                                                  ┌─────┴─────┐
                                                                  │           │
                                                            SearchOperator  AdvanceOperator
                                                            (turn↔pause)    (diferencial)

                                                        AvoidWallOperator (capa de seguridad)
```

### Entry point: `main.py`

`main.py` es el punto de entrada. Su trabajo es:
1. Ajustar el `PYTHONPATH` para poder importar `vision`, `motors`, y `pipeline5`
2. Instanciar `HybridVisionService`, `MotorService` y `Pipeline5Service`
3. Llamar a `pipeline.run()` (loop infinito)
4. En el `finally`, hacer cleanup de todos los servicios

## 3. Máquina de Estados (FSM)

```
           pelota detectada
     ┌──────────────────────────┐
     │                          │
     ▼                          │
  ┌──────┐                  ┌──┴────┐
  │SEARCH│                  │ADVANCE│
  │ gira │                  │avanza │
  └──────┘                  └───────┘
     ▲                          │
     │     pelota perdida       │
     └──────────────────────────┘
        (>0.2s sin verla)
```

### SEARCH — Buscando la pelota

El robot gira sobre su propio eje en ciclos de **0.5s giro + 0.8s pausa**. La dirección del giro se determina según dónde se vio la pelota por última vez (si se perdió a la izquierda, gira a la izquierda para reencontrarla).

Al detectar la pelota, transiciona inmediatamente a **ADVANCE**.

### ADVANCE — Persiguiendo la pelota

El robot avanza hacia adelante ajustando la velocidad diferencial de las ruedas proporcionalmente al error horizontal (distancia del centro de la pelota al centro de la cámara):
- Pelota centrada (error ≤ 20px): ambas ruedas a `ADVANCE_SPEED` (150)
- Pelota a la derecha: rueda izquierda más rápido, derecha más lento → gira a la derecha
- Pelota a la izquierda: rueda derecha más rápido, izquierda más lento → gira a la izquierda

La diferencia máxima entre ruedas es 80% de la velocidad base.

Si la pelota está muy cerca (radio ≥ 45px), avanza recto a máxima velocidad para patearla.

Al perder la pelota por más de 0.2s, transiciona a **SEARCH** en la dirección donde se vio por última vez.

### Filtros de detección (anti falsos positivos)

Antes de usar la detección de pelota, pipeline5 aplica 3 filtros sobre el frame capturado:

| Filtro | Qué hace | Parámetro | Propósito |
|--------|----------|-----------|-----------|
| **Color (HSV)** | Analiza un parche 7×7 alrededor del centro detectado. Rechaza si el Hue mediano está entre 13° y 170° | `median_h ∉ [0,12] ∪ [171,179]` | Solo acepta naranja/rojo, rechaza amarillo, verde, azul, etc. |
| **Saturación** | Rechaza si la saturación mediana < 140 | `median_s < 140` | Exige "naranja chillón", rechaza madera, piel, cartón |
| **Forma** | Si YOLO detectó la pelota, analiza el bounding box. Rechaza si altura/anchura > 1.4 | `h/w > 1.4` | Rechaza objetos altos como pilares o conos |

### Capa de seguridad: AvoidWallOperator

Independientemente del estado FSM, cada tick se analiza una franja de la imagen (25% superior central, que corresponde al suelo frente al robot por la cámara invertida). Si más del 50% de esa franja es negro (pared), se activa una maniobra de escape en 2 fases:

1. **Fase 1 (0.5s):** Marcha atrás recta a -150 PWM para alejarse
2. **Fase 2 (1.0s):** Giro de 180° a baja velocidad (50 PWM)

Esta capa tiene **prioridad máxima**: si se activa, sobrescribe cualquier comando de SEARCH o ADVANCE.

## 4. Catálogo de archivos

| Archivo | Propósito | Dependencias | Qué modificar aquí |
|---------|-----------|--------------|-------------------|
| `main.py` | Entry point, wiring de servicios | `vision`, `motors`, `pipeline5` | Cambiar duración, agregar setup adicional |
| `pipeline_service.py` | FSM, loop principal, filtros, orquestación | Todos los operators, DTOs, constants | Lógica de estados, filtros, transiciones |
| `operators/search_operator.py` | Giro en sitio + pausa cíclica | `pipeline_constants` | Velocidad de giro, duración de fases |
| `operators/advance_operator.py` | Avance con diferencial proporcional | `pipeline_constants` | Velocidad de avance, deadband, ganancia de curva |
| `operators/avoid_wall_operator.py` | Detección de pared negra, escape | `cv2`, `numpy`, `pipeline_constants` | Umbral de negro, cobertura, duración de fases |
| `operators/chase_operator.py` | **Código muerto** — no se usa | `pipeline_constants` (constantes faltantes) | No modificar; referencia histórica |
| `dto/pipeline_output_dto.py` | Dataclass inmutable de salida por tick | — | Agregar campos nuevos al snapshot |
| `utils/pipeline_constants.py` | Velocidades, duraciones, nombres de estado | — | Ajustar velocidades y tiempos |
| `capture_image.py` | Script: captura un frame y lo guarda como JPG | `vision` | Diagnosticar qué ve la cámara |
| `capture_vision_debug.py` | Script: captura frame con overlays de detección | `vision`, `cv2` | Diagnosticar detección de pelota |

## 5. Operadores en detalle

### SearchOperator (`operators/search_operator.py`)

**Propósito:** Girar en sitio para encontrar la pelota.

**Funcionamiento:**
- Tiene 2 fases: `turn` → `pause` → `turn` → ...
- Fase `turn` (500ms): Ambas ruedas giran en direcciones opuestas a `SEARCH_SPEED` (23 PWM)
  - `direction=1` (derecha): `v_left=+23, v_right=-23`
  - `direction=-1` (izquierda): `v_left=-23, v_right=+23`
- Fase `pause` (800ms): Ruedas detenidas, para dar tiempo al sistema de visión
- `reset(direction)`: Se llama al entrar a SEARCH, define hacia dónde girar

**Nota:** La dirección se determina según dónde se vio la pelota por última vez en `pipeline_service.py:127`.

### AdvanceOperator (`operators/advance_operator.py`)

**Propósito:** Avanzar hacia la pelota ajustando la dirección.

**Funcionamiento:**
```
error = cx - (frame_width / 2)          # píxeles de desviación del centro
error_norm = min(|error| / half_w, 1)   # normalizado 0..1
diff = ADVANCE_SPEED * error_norm * 0.8 # diferencia entre ruedas

Si error > 0 (pelota a la derecha):
  v_left  = ADVANCE_SPEED + diff   # rueda izquierda más rápido
  v_right = ADVANCE_SPEED - diff   # rueda derecha más lento
Si error < 0 (pelota a la izquierda):
  v_left  = ADVANCE_SPEED - diff
  v_right = ADVANCE_SPEED + diff
```

- Si `|error| ≤ 20px`: ambas ruedas a `ADVANCE_SPEED` (va recto)
- Si `radius ≥ 45px`: pelota muy cerca, recto a máxima velocidad
- Si no hay pelota pero sí última posición conocida: usa el último `cx`
- Valores clamped entre 0 y 255 (PWM máximo)

### AvoidWallOperator (`operators/avoid_wall_operator.py`)

**Propósito:** Evitar chocar contra paredes negras.

**Funcionamiento:**
1. Convierte el frame a escala de grises
2. Recorta ROI: 25% superior de la imagen (suelo cercano al robot), 20%-80% horizontal
3. Cuenta píxeles con valor < 20 (negro) en esa franja
4. Si `píxeles_negros / total_píxeles > 0.50`: activa escape

**Maniobra de escape:**
- Fase 1: Marcha atrás recta (-150 PWM ambas ruedas) por 0.5s
- Fase 2: Giro de 180° (rueda izq +50, rueda der -50) por 1.0s

**⚠️ Observación:** Los parámetros `black_threshold=20` y `coverage_ratio=0.50` están hardcodeados en `check_and_avoid()` (líneas 59 y 68), sobrescribiendo los valores pasados al constructor.

### ChaseOperator (`operators/chase_operator.py`) — CÓDIGO MUERTO

Este archivo **no se importa ni se usa en ningún lado** de pipeline5. Es un remanente de versiones anteriores.

**⚠️ Además**, importa constantes que **no existen** en `pipeline_constants.py`:
- `CHASE_SPEED_BASE`
- `CHASE_DEADBAND_PX`
- `KICK_RADIUS_PX`

Si alguien intentara usarlo, causaría `ImportError`.

## 6. DTOs y constantes

### PipelineOutputDto (`dto/pipeline_output_dto.py`)

Dataclass inmutable (`frozen=True`) que captura el estado de cada tick del pipeline:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `state` | `str` | Estado FSM actual: `"SEARCH"` o `"ADVANCE"` |
| `ball_visible` | `bool` | Si se detectó pelota en este tick |
| `v_left` | `float` | Velocidad PWM enviada a la rueda izquierda |
| `v_right` | `float` | Velocidad PWM enviada a la rueda derecha |
| `dur_ms` | `int` | Duración del pulso de motor en milisegundos |
| `ts` | `float` | Timestamp Unix del tick |

### Constantes (`utils/pipeline_constants.py`)

| Constante | Valor | Uso |
|-----------|-------|-----|
| `SEARCH` | `"SEARCH"` | Nombre del estado de búsqueda |
| `ADVANCE` | `"ADVANCE"` | Nombre del estado de avance |
| `SHOOT` | `"SHOOT"` | Definido pero nunca usado (estado planeado no implementado) |
| `SEARCH_SPEED` | `23` | PWM durante giro de búsqueda |
| `SEARCH_TURN_DUR_MS` | `500` | Duración de fase de giro en búsqueda |
| `SEARCH_PAUSE_DUR_MS` | `800` | Duración de pausa entre giros |
| `STOP_DUR_MS` | `100` | Duración de pulso de parada |
| `ADVANCE_SPEED` | `150` | PWM base para avance |
| `SHOOT_SPEED` | `255` | PWM máxima para disparo (no usado) |

## 7. Scripts de diagnóstico

### `capture_image.py`

Script standalone que:
1. Inicia `HybridVisionService`
2. Espera hasta 3 segundos a que la cámara produzca un frame
3. Guarda el frame como `captura_camara.jpg`

Útil para verificar que la cámara funciona y ver qué está viendo el robot sin overlays.

### `capture_vision_debug.py`

Script standalone que:
1. Inicia `HybridVisionService`
2. Espera 2 segundos para estabilizar cámara e IA
3. Captura un frame con overlays de diagnóstico:
   - Cruz central de referencia
   - Círculo verde del tamaño del radio detectado
   - Punto rojo en el centro exacto de la pelota
   - Rectángulo azul (parche 7×7 del filtro de color)
   - Etiqueta con la fuente de detección (HSV o YOLO)
4. Guarda como `captura_vision_debug.jpg`

Útil para calibrar la detección de pelota y ver si los filtros están funcionando.

## 8. Guía de modificación

### Cambiar velocidad de búsqueda

Editar `utils/pipeline_constants.py`:
```python
SEARCH_SPEED = 23   # Subir/bajar este valor (0-255)
```

### Cambiar sensibilidad del avance

Editar `operators/advance_operator.py`:
- Línea 35: `abs(error) <= 20` — deadband central (más grande = recto más tiempo)
- Línea 42: `* 0.8` — ganancia de curva (más grande = giros más cerrados)

### Agregar un nuevo estado (ej: SHOOT)

1. En `pipeline_service.py`, agregar lógica de transición al estado SHOOT (ej: cuando `ball["r"] >= 50`)
2. Crear un `ShootOperator` en `operators/` que avance recto a máxima velocidad
3. Agregar la rama `elif self._state == SHOOT:` en `tick()`

### Ajustar umbrales del filtro de color

Editar `pipeline_service.py`:
- Línea 75: `13 <= median_h <= 170` — rango de hue rechazado
- Línea 79: `median_s < 140` — umbral mínimo de saturación
- Línea 94: `(h / w) > 1.4` — proporción para rechazar pilares

### Ajustar detección de pared negra

Editar `operators/avoid_wall_operator.py`:
- Línea 59: `self.black_threshold = 20` — valor máximo para considerar negro (0-255)
- Línea 68: `self.coverage_ratio = 0.50` — porcentaje de pantalla negra para activar
- Línea 34: `-150.0, -150.0` — velocidad de marcha atrás
- Línea 39: `50.0, -50.0` — velocidad de giro

### Cambiar duración del loop

Editar `pipeline_service.py`, línea 166:
```python
time.sleep(0.03)  # 30ms entre ticks (~33 FPS efectivos)
```

## 9. Issues y observaciones

### `operators/chase_operator.py` — Código muerto

- No se importa en `pipeline_service.py`
- Referencia constantes inexistentes (`CHASE_SPEED_BASE`, `CHASE_DEADBAND_PX`, `KICK_RADIUS_PX`)
- Recomendación: eliminar o mover a un archivo de referencia histórica

### `AvoidWallOperator` — Valores hardcodeados

En `check_and_avoid()` (líneas 59 y 68):
```python
self.black_threshold = 20     # Sobrescribe el valor del __init__
self.coverage_ratio = 0.50    # Sobrescribe el valor del __init__
```
Los parámetros pasados al constructor (`black_threshold=30`, `coverage_ratio=0.35`) son ignorados.

### Estado `SHOOT` sin implementar

Definido en `pipeline_constants.py` y existe `SHOOT_SPEED = 255`, pero no hay lógica de transición ni operador para este estado.

### Import inline de cv2/numpy

En `pipeline_service.py:58-59`, `cv2` y `numpy` se importan dentro del método `tick()` en lugar de al inicio del archivo. Esto es inusual pero funcional.

### Convención de signos invertida

En `pipeline_service.py:148`, la rueda izquierda se invierte:
```python
self._motors.drive(-v_left, v_right, dur_ms)
```
Esto es porque la rueda izquierda tiene polaridad invertida en el hardware de este robot.
