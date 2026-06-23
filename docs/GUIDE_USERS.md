# Guía de Usuario — Futbot v9

**Audiencia:** Operadores del robot físico — no se requiere experiencia en programación.
**Prerrequisitos:** Familiaridad básica con terminal Linux (SSH, comandos de navegación).

---

## Tabla de Contenidos

1. [Advertencias de Seguridad](#advertencias-de-seguridad)
2. [Checklist Pre-Vuelo](#checklist-pre-vuelo)
3. [Preparación del Robot](#preparación-del-robot)
4. [Encendido y Apagado](#encendido-y-apagado)
5. [Modos de Operación](#modos-de-operación)
6. [Calibración](#calibración)
7. [Scripts de Diagnóstico](#scripts-de-diagnóstico)
8. [Monitoreo en Tiempo Real](#monitoreo-en-tiempo-real)
9. [Códigos de Error y Troubleshooting](#códigos-de-error-y-troubleshooting)
10. [Optimización de Rendimiento](#optimización-de-rendimiento)
11. [Mantenimiento](#mantenimiento)
12. [Apéndice A: Referencia Rápida de Comandos](#apéndice-a-referencia-rápida-de-comandos)
13. [Apéndice B: Pines GPIO y Conexiones](#apéndice-b-pines-gpio-y-conexiones)

---

## Advertencias de Seguridad

> ⚠️ **Leer antes de operar el robot.**

| Riesgo | Prevención |
|--------|-----------|
| **Eléctrico** — Cortocircuito en batería LiPo | Usar solo cargador balanceado. No perforar ni deformar la batería. Desconectar al almacenar. |
| **Mecánico** — Movimiento brusco de motores | Mantener manos y objetos alejados de las ruedas durante la operación. No sujetar el robot por los servos. |
| **Incendio** — Sobrecalentamiento de LiPo | Cargar en superficie no inflamable. No dejar cargando sin supervisión. Si se hincha, desechar adecuadamente. |
| **Datos** — Conexión SSH insegura | Cambiar la contraseña por defecto de la RPi antes de conectar a redes externas. |

---

## Checklist Pre-Vuelo

Ejecutar **antes de cada sesión de juego**:

- [ ] Batería cargada (≥11.1V para LiPo 3S)
- [ ] Ribbon cable de cámara CSI firmemente conectado
- [ ] Servos sin obstrucciones mecánicas (mover manualmente a 0° y 180°)
- [ ] Ruedas giran libremente sin fricción excesiva
- [ ] Cable UART conectado a pines GPIO 14 (TX) y 15 (RX)
- [ ] Puerto `/dev/ttyAMA0` existe (`ls -la /dev/ttyAMA0`)
- [ ] Cámara detectada (`libcamera-hello --list-cameras`)
- [ ] Dependencias instaladas (`uv run python -c "import cv2; print(cv2.__version__)"`)

---

## Preparación del Robot

### Conexiones Físicas

| Conexión | Origen | Destino | Verificación |
|----------|--------|---------|-------------|
| Cámara | Puerto CSI RPi5 | Ribbon cable IMX219 | Clip del conector cerrado |
| UART TX | GPIO 14 (pin 8) | RX del driver de motores | Cable dupont firme |
| UART RX | GPIO 15 (pin 10) | TX del driver de motores | Cable dupont firme |
| GND | GPIO GND (pin 6) | GND del driver | Continuidad con multímetro |
| Servo Pan | Canal 2 PWM del driver | Servo horizontal | Conector polarizado correcto |
| Servo Tilt | Canal 1 PWM del driver | Servo vertical | Conector polarizado correcto |
| Alimentación | Batería LiPo | Entrada de potencia del driver | Voltaje ≥11.1V |

### Configuración del Sistema

Por defecto, la RPi5 debe tener habilitado el UART principal:

```bash
# Verificar que el UART está habilitado
sudo raspi-config
# → Interface Options → Serial Port
# → Login shell over serial: No
# → Serial port hardware: Yes
```

---

## Encendido y Apagado

### Encendido

1. Conectar la batería al driver de motores — los LEDs del driver deben encenderse
2. La Raspberry Pi 5 arranca automáticamente al recibir alimentación por el driver
3. Esperar ~30 segundos hasta que el LED verde de actividad parpadee normalmente
4. Conectarse vía SSH desde una laptop:

```bash
ssh futbot@<ip-del-robot>
```

### Apagado Normal

Presiona `Ctrl+C` **una sola vez** en la terminal donde corre `main.py`. El sistema:

1. Detiene todos los motores (`MotorCommand(0,0)`)
2. Cierra la conexión UART
3. Libera la cámara
4. Imprime `futbot apagado`

> Tiempo estimado: <1 segundo. No desconectar la batería durante el apagado.

### Parada de Emergencia

Si el robot no responde a `Ctrl+C`:

1. **Desconectar físicamente la batería** del driver de motores
2. Esperar 5 segundos
3. Reconectar y reiniciar el procedimiento de encendido

---

## Modos de Operación

### Modo Real — Hardware

```bash
cd ~/futbot/futbot
uv run python main.py
# o explícitamente:
FUTBOT_MODE=real uv run python main.py
```

El robot opera con:
- Cámara CSI IMX219 real (resolución automática de backend)
- Comandos UART enviados al driver de motores por `/dev/ttyAMA0`
- Logs con timestamp en formato `HH:MM:SS`

### Modo Stub — Desarrollo sin Robot

```bash
cd ~/futbot/futbot
FUTBOT_MODE=stub uv run python main.py
```

El robot opera con:
- Frames sintéticos (campo verde con pelota naranja en posición aleatoria)
- Comandos de motor registrados en memoria (no enviados por UART)
- Pipeline de visión completo funcional (HSV detecta la pelota sintética)

> Ideal para: desarrollo en laptop, depuración de lógica FSM, pruebas de regresión.

---

## Calibración

### Calibración de Motores

```bash
cd ~/futbot/futbot
uv run python scripts/cal_motors.py
```

Este script interactivo prueba cada dirección secuencialmente:
1. Avance (ambas ruedas adelante)
2. Retroceso (ambas ruedas atrás)
3. Giro izquierda (rueda derecha avanza, izquierda retrocede)
4. Giro derecha (rueda izquierda avanza, derecha retrocede)
5. Stop

**Si alguna dirección no funciona:** verifica el cableado de ese motor en el driver. Las combinaciones `m1-m4` se mapean según la convención:
```
m3 = -v_right  → rueda derecha física
m4 = -v_left   → rueda izquierda física
```

Parámetros ajustables en `config.py`:

```python
diff_cap: float = 250.0            # Velocidad máxima absoluta (0-255)
chase_speed_base: float = 80.0     # Velocidad base de persecución
search_turn_speed: float = 255.0   # Velocidad de giro en búsqueda
recovery_reverse_speed: float = 110.0  # Velocidad de retroceso
recovery_turn_speed: float = 115.0     # Velocidad de giro en recuperación
```

### Calibración de Cámara

```bash
# Enfocar la cámara
uv run python scripts/focus_camera.py

# Capturar imagen de prueba
uv run python scripts/capture_image.py
```

Verificar en la imagen capturada:
- La pelota naranja se ve con colores fieles (no lavada por sobreexposición)
- El campo de visión cubre el área de juego esperada
- No hay artefactos de compresión ni bandas de flicker

Ajustes en `config.py`:

```python
camera_exposure_default: int = 200   # <100: más oscuro, >300: más brillante
camera_width: int = 320              # Resolución horizontal (afecta FPS)
camera_height: int = 240             # Resolución vertical
camera_flip_horizontal: bool = False # True si la cámara está montada invertida
```

### Calibración de Detección de Pelota

```bash
# Prueba dinámica de persecución
uv run python scripts/test_chase_dynamic.py

# Debug visual con overlay de detecciones
uv run python scripts/capture_vision_debug.py
```

Si la pelota no se detecta consistentemente, ajustar umbrales HSV en `config.py`:

```python
# Rango naranja principal
ball_hsv_lower: Tuple[int,int,int] = (0, 80, 80)
ball_hsv_upper: Tuple[int,int,int] = (65, 255, 255)

# Rango rojo (wrap-around del hue)
ball_hsv_lower2: Tuple[int,int,int] = (168, 80, 80)
ball_hsv_upper2: Tuple[int,int,int] = (179, 255, 255)

# Filtros de forma
ball_min_area: int = 30
ball_min_radius: int = 4
adaptive_min_circularity: float = 0.20
```

### Calibración de Persecución (Servo Visual)

```bash
uv run python scripts/cal_chase_fading.py
```

Parámetros clave en `config.py`:

```python
chase_rot_gain: float = 0.8    # Aumentar → giro más agresivo. Reducir → más suave
chase_deadband_px: float = 16  # Zona muerta en píxeles (centro del frame)
kick_radius_px: float = 50     # Tamaño de pelota para activar patada directa
```

---

## Scripts de Diagnóstico

Ubicación: `futbot/scripts/`. Ejecutar con: `uv run python scripts/<script>.py`

| Script | Propósito | Requiere robot físico |
|--------|-----------|----------------------|
| `cal_motors.py` | Calibración interactiva de velocidad y dirección | Sí |
| `cal_chase_fading.py` | Ajuste de transiciones suaves en persecución | Sí |
| `focus_camera.py` | Ajuste de foco del lente CSI | Sí |
| `capture_image.py` | Guarda un frame de la cámara para análisis | Sí |
| `capture_vision_debug.py` | Guarda frame con overlay de todas las detecciones | Sí |
| `capture_attack_geometry.py` | Captura para análisis de ángulo de ataque | Sí |
| `test_motors_raw.py` | Envía comandos UART individuales sin pipeline | Sí |
| `test_chase_dynamic.py` | Prueba de persecución con pelota real | Sí |
| `search_ball_resolutions.py` | Compara detección a diferentes resoluciones | Sí |
| `analyze_image.py` | Analiza una imagen guardada con el pipeline | No |
| `copy_husky.py` | Implementación de referencia del FSM original | No |
| `_libcamera_worker.py` | Worker interno para backend libcamera subprocess | Sí |

---

## Monitoreo en Tiempo Real

### Formato de Logs

Cada línea de log sigue el formato:

```
HH:MM:SS [NIVEL] futbot.<modulo>: mensaje
```

### Capturar Logs a Archivo

```bash
cd ~/futbot/futbot
uv run python main.py 2>&1 | tee futbot-$(date +%Y%m%d-%H%M%S).log
```

### Eventos Clave en los Logs

| Mensaje | Significado | Acción sugerida |
|---------|------------|----------------|
| `futbot iniciando en modo real` | Arranque normal | Ninguna |
| `picamera2: 320x240 OK` | Cámara CSI detectada | Ninguna |
| `UART conectado: /dev/ttyAMA0 @ 1000000 baud` | Driver de motores listo | Ninguna |
| `fsm: SEARCH -> CHASE` | Pelota detectada, iniciando persecución | Ninguna |
| `fsm: CHASE -> RECOVERY` | Pelota perdida | Verificar iluminación/obstrucciones |
| `fsm: RECOVERY -> SEARCH` | Recuperación agotada | Robot no encuentra la pelota |
| `YOLO backend onnx no disponible` | ONNX Runtime no instalado | Sistema usa solo HSV — instalar ONNX si se desea |
| `picamera2 no disponible` | Cámara CSI sin respuesta | Verificar conexión física del ribbon cable |
| `No se detectó ningún backend de cámara` | Error crítico — ningún backend funciona | Revisar todas las conexiones de cámara |
| `Error en runtime:` | Excepción no controlada | Revisar el traceback completo en el log |

---

## Códigos de Error y Troubleshooting

### Categoría A: Movimiento

| Código | Síntoma | Causa probable | Solución |
|--------|---------|---------------|----------|
| A1 | Robot no se mueve | Batería descargada o desconectada | Cargar batería, verificar conexión al driver |
| A2 | Robot no se mueve | Puerto UART no existe | `ls -la /dev/ttyAMA0`. Si no existe, habilitar en raspi-config |
| A3 | Robot no se mueve | pyserial no instalado | `uv run python -c "import serial"` |
| A4 | Giro en dirección incorrecta | Cables de motor invertidos | Intercambiar conectores del motor afectado o ajustar signos en `_differential()` |
| A5 | Robot se mueve erráticamente | Baudrate incorrecto | Verificar que el driver y config.py usen 1,000,000 |
| A6 | Velocidad inconsistente | Batería baja | Cargar batería — voltaje <10.5V reduce torque |

### Categoría B: Cámara

| Código | Síntoma | Causa probable | Solución |
|--------|---------|---------------|----------|
| B1 | "No se detectó ningún backend" | Ribbon cable suelto o dañado | Desconectar y reconectar el cable CSI. Probar con `libcamera-hello` |
| B2 | "picamera2 no disponible" | Librería no instalada | `uv add picamera2` en el entorno |
| B3 | Frames negros o verdes | Exposición incorrecta o warmup insuficiente | Ajustar `camera_exposure_default`, esperar 2s tras inicio |
| B4 | Baja resolución | Backend V4L2 seleccionado en vez de CSI | Forzar backend: `camera_backend = "libcamera"` |
| B5 | Cámara no listada | Interfaz CSI deshabilitada | `sudo raspi-config` → Interfaces → Camera → Enable |

### Categoría C: Detección

| Código | Síntoma | Causa probable | Solución |
|--------|---------|---------------|----------|
| C1 | No detecta pelota naranja | Iluminación inadecuada | Ajustar exposición o umbrales HSV. Usar `capture_vision_debug.py` |
| C2 | Falsos positivos constantes | Umbrales HSV muy permisivos | Reducir rango S y V, aumentar `ball_min_area` |
| C3 | YOLO no carga | Modelo no encontrado | Verificar `models/yoloe26n_v2/onnx/yoloe26n_v2.onnx` |
| C4 | Detecciones intermitentes | Cache TTL muy corto | Aumentar `cache_ttl` en `vision.py` (default 0.5s) |
| C5 | Detecta objetos que no son pelota | Circularidad muy baja | Aumentar `adaptive_min_circularity` a 0.4-0.5 |

### Categoría D: Sistema

| Código | Síntoma | Causa probable | Solución |
|--------|---------|---------------|----------|
| D1 | Crash al iniciar | Python <3.11 | `python3 --version` — instalar 3.11+ |
| D2 | Crash al iniciar | Dependencia faltante | `uv sync` para instalar todas las dependencias |
| D3 | Alto uso de CPU (modo stub) | Bucle sin sleep | Verificar `time.sleep(0.01)` en `main.py` |
| D4 | Memoria creciente | Fuga de memoria en backend | Monitorear con `htop`, probar otro backend de cámara |

---

## Optimización de Rendimiento

### Aumentar FPS

1. Reducir resolución de cámara en `config.py`:
   ```python
   camera_width: int = 160   # menor resolución = mayor FPS
   camera_height: int = 120
   ```
2. Usar NCNN en lugar de ONNX en RPi5 (~2× más rápido)
3. Reducir `yolo_imgsz` de 320 a 224 o 192 (menor precisión, mayor velocidad)

### Reducir Latencia de Control

1. Disminuir `time.sleep(0.01)` en `main.py` a `0.005` o `0.001`
2. Reducir `search_scan_secs` para búsqueda más reactiva
3. Aumentar `chase_rot_gain` para giros más rápidos

### Conservar Batería

1. Reducir `search_turn_speed` (default 255) a 150-180
2. Reducir `chase_speed_base` (default 80) a 50-60
3. Apagar servos cuando no se usen (enviar ángulo central con dur_ms=0)

---

## Mantenimiento

### Diario (antes de cada sesión)

- Verificar carga de batería
- Inspeccionar conexiones físicas (cables, ribbon CSI)
- Limpiar lente de cámara con paño de microfibra
- Ejecutar `uv run python scripts/cal_motors.py` para verificar movimiento

### Semanal

- Ejecutar suite completa de tests: `FUTBOT_MODE=stub uv run pytest tests/ -v`
- Revisar logs de sesiones anteriores para detectar anomalías
- Lubricar engranajes de servos si presentan ruido

### Mensual

- Actualizar dependencias: `uv sync --upgrade`
- Verificar integridad de los archivos de modelo (`models/`)
- Respaldar configuración personalizada de `config.py`

### Almacenamiento Prolongado

- Cargar/descargar batería LiPo a ~3.8V por celda (voltaje de almacenamiento)
- Desconectar batería del driver
- Guardar en ambiente seco, temperatura 10-30°C
- Cubrir lente de cámara para evitar polvo

---

## Apéndice A: Referencia Rápida de Comandos

| Comando | Descripción |
|---------|------------|
| `uv run python main.py` | Iniciar robot en modo real |
| `FUTBOT_MODE=stub uv run python main.py` | Iniciar robot en modo stub |
| `uv run python scripts/cal_motors.py` | Calibrar motores |
| `uv run python scripts/focus_camera.py` | Enfocar cámara |
| `uv run python scripts/capture_image.py` | Capturar imagen de prueba |
| `uv run python scripts/capture_vision_debug.py` | Capturar con overlay de detecciones |
| `uv run python scripts/test_chase_dynamic.py` | Probar persecución |
| `uv run python scripts/test_motors_raw.py` | Probar comandos UART individuales |
| `FUTBOT_MODE=stub uv run pytest tests/ -v` | Ejecutar todos los tests |
| `uv run python main.py 2>&1 \| tee futbot.log` | Iniciar con logs a archivo |
| `libcamera-hello --list-cameras` | Listar cámaras CSI disponibles |
| `ls -la /dev/ttyAMA0` | Verificar puerto UART |
| `uv sync` | Instalar dependencias |
| `uv sync --upgrade` | Actualizar dependencias |
| `uv sync --group onnx` | Instalar backend ONNX |
| `uv sync --group ncnn` | Instalar backend NCNN |

---

## Apéndice B: Pines GPIO y Conexiones

### Raspberry Pi 5 — GPIO Header (pines usados)

```
                    3.3V  (1) (2)  5V
               SDA (GPIO2) (3) (4)  5V
              SCL (GPIO3)  (5) (6)  GND          ← GND del driver
                          (7) (8)  TX (GPIO14)    → RX del driver
             GND           (9) (10) RX (GPIO15)   → TX del driver
                         (11) (12)
                         (13) (14)
                         (15) (16)
                         (17) (18)
                         (19) (20)
                         (21) (22)
                         (23) (24)
             GND          (25) (26)
                         (27) (28)
                         (29) (30)
                         (31) (32)
                         (33) (34)
                         (35) (36)
                         (37) (38)
             GND          (39) (40)
```

### Driver de Motores — Conexiones

| Pin Driver | Conectar a | Notas |
|-----------|-----------|-------|
| VCC | Batería LiPo (+) | 11.1V nominal |
| GND | Batería LiPo (−) + RPi GND (pin 6) | Tierra común obligatoria |
| RX | RPi TX (GPIO14, pin 8) | Señal UART del robot al driver |
| TX | RPi TX (GPIO15, pin 10) | Señal UART del driver al robot |
| SERVO1 | Servo Tilt | Canal 1 (ID=1 en protocolo) |
| SERVO2 | Servo Pan | Canal 2 (ID=2 en protocolo) |
| M1-M4 | Motores DC | M3 = rueda derecha, M4 = rueda izquierda |

### Convención de Colores CSI

```
Ribbon cable IMX219:
  Contactos dorados → hacia el conector CSI (parte metálica)
  Cara azul        → hacia afuera del puerto
```
