# Guía Técnica — Futbot v9

Documentación técnica para desarrolladores que desean entender, modificar o extender el código del robot.

---

## Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Módulo: `config.py`](#módulo-configpy)
3. [Módulo: `camera.py`](#módulo-camerapy)
4. [Módulo: `vision.py`](#módulo-visionpy)
5. [Módulo: `pipeline.py`](#módulo-pipelinepy)
6. [Módulo: `motors.py`](#módulo-motorspy)
7. [Módulo: `main.py`](#módulo-mainpy)
8. [Sistema de Stubs](#sistema-de-stubs)
9. [Protocolo UART de Motores](#protocolo-uart-de-motores)
10. [Backends YOLO](#backends-yolo)
11. [Backends de Cámara](#backends-de-cámara)
12. [Cómo Extender el Sistema](#cómo-extender-el-sistema)

---

## Arquitectura General

Futbot sigue una arquitectura de **módulos planos** — un archivo `.py` por responsabilidad, sin anidación de operadores ni capas de abstracción.

### Diagrama de Componentes

```
┌────────────────────────────────────────────────────────────┐
│                         main.py                            │
│  init → while running:                                     │
│    frame = cam.grab()                                      │
│    dets  = vis.detect(frame)                               │
│    cmd   = pip.tick(dets)                                  │
│    mot.send(cmd)                                           │
└──┬──────────┬──────────────┬──────────────┬───────────────┘
   │          │              │              │
   ▼          ▼              ▼              ▼
┌──────┐ ┌────────┐ ┌──────────┐ ┌────────┐
│camera│ │ vision │ │ pipeline │ │ motors │
│  .py │ │   .py  │ │   .py    │ │  .py   │
└──────┘ └────────┘ └──────────┘ └────────┘
   │          │              │              │
   └──────────┴──────┬───────┴──────────────┘
                     │
                     ▼
               ┌──────────┐
               │ config.py│
               └──────────┘
```

### Flujo de Datos Completo

```
Frame (np.ndarray BGR)
    │
    ▼
Vision.detect()
    ├── YOLO inferencia (ONNX/NCNN/TensorRT) → Ball (x,y,radius,confidence)
    ├── HSV pelota naranja                    → Ball (fallback)
    ├── HSV porterías (azul/amarillo)        → Goal (color, x, y)
    ├── HSV línea blanca                     → WhiteLine (detected, position)
    └── Fusión (YOLO > HSV > caché TTL)      → Ball final
    │
    ▼
Detections {ball, goal, white_line, ts}
    │
    ▼
Pipeline.tick()
    ├── SEARCH:  barrido rotacional (timed sweep)
    ├── CHASE:   servo visual proporcional + patada directa
    └── RECOVERY: secuencia reverse→turn→forward + detección de línea
    │
    ▼
MotorCommand {left_speed, right_speed, dur_ms, pan_angle, tilt_angle}
    │
    ▼
Motors.send()
    ├── apply_diff_cap: saturar velocidades a diff_cap (250.0)
    ├── differential: (v_left, v_right) → (0, 0, -v_right, -v_left)
    └── _burst: construir tramas binarias → UART /dev/ttyAMA0
```

### Dependencias entre Módulos

```
config.py ◄── camera.py     (Config)
config.py ◄── vision.py     (Config)
config.py ◄── motors.py     (Config, crc8)
config.py ◄── pipeline.py   (Config)
                  │
vision.py ────────┤ (Detections, Ball)
motors.py ────────┤ (MotorCommand)
                  ▼
            pipeline.py
                  ▲
                  │
main.py ──────────┴── camera.py, vision.py, pipeline.py, motors.py
```

**Sin dependencias circulares.**

---

## Módulo: `config.py`

**Responsabilidad:** Fuente única de verdad para todas las constantes configurables. Sin dependencias de hardware ni de otros módulos.

### Estructura

```python
CRC8_TABLE = [...]        # 256 elementos, polinomio 0x07
crc8(data: bytes) -> int  # Calcula CRC8 usando la tabla

@dataclass
class Config:
    # Cámara
    camera_width: int = 320
    camera_height: int = 240
    camera_backend: str = "libcamera"

    # Visión HSV
    ball_hsv_lower: Tuple[int,int,int] = (0, 80, 80)
    ball_hsv_upper: Tuple[int,int,int] = (65, 255, 255)
    goal_blue_hsv_lower: Tuple[int,int,int] = (95, 180, 60)

    # Visión YOLO
    yolo_backend: str = "onnx"
    yolo_conf_threshold: float = 0.40

    # Pipeline
    chase_speed_base: float = 80.0
    chase_rot_gain: float = 0.8
    search_turn_speed: float = 255.0
    chase_miss_secs: float = 0.8

    # Motores
    uart_port: str = "/dev/ttyAMA0"
    uart_baud: int = 1000000
    diff_cap: float = 250.0

    # Servos
    pan_center: float = 70.0
    tilt_center: float = 45.0

    # Métodos helper
    def resolve_yolo_model_path(self) -> Path
    def resolve_ncnn_model_dir(self) -> Path
```

### Cómo Modificar

Para cambiar cualquier comportamiento, edita el valor por defecto en el dataclass. No requiere tocar otros archivos:

```python
# Ejemplo: hacer el robot más agresivo en persecución
cfg = Config(
    chase_speed_base=100.0,  # más rápido
    chase_rot_gain=1.2,      # giro más agresivo
)
```

---

## Módulo: `camera.py`

**Responsabilidad:** Captura de frames con resolución automática de backend.

### Interfaz Pública

```python
class Camera:
    def __init__(self, config: Config)
    def grab(self) -> np.ndarray | None   # Frame BGR o None si falla
    def release(self)                     # Libera la cámara
    @property width(self) -> int          # Ancho real del frame
    @property height(self) -> int         # Alto real del frame
```

### Backends (probados en orden)

| Orden | Backend | Mecanismo | Plataforma |
|-------|---------|-----------|------------|
| 1 | picamera2 | Biblioteca nativa Python para RPi5 | Linux aarch64 |
| 2 | libcamera subprocess | Worker Python con bindings C vía pipes | Linux aarch64 |
| 3 | GStreamer libcamerasrc | Pipeline GStreamer → OpenCV | Linux aarch64 |
| 4 | V4L2 | OpenCV VideoCapture sobre /dev/video* | Cualquier Linux |

### Adaptadores de Backend

Cada backend se envuelve en un adaptador que expone interfaz tipo `cv2.VideoCapture`:

```python
class _Picamera2Adapter:           # picamera2 → read()/release()
class _LibcameraSubprocessAdapter: # subprocess + pipes → read()/release()
```

El protocolo del subprocess libcamera usa un header binario:
```
MAGIC (4B) | width (4B) | height (4B) | stride (4B) | size (4B) | frame BGR (size B)
```
MAGIC = `\xf8\xb4\xc2\x0d`

---

## Módulo: `vision.py`

**Responsabilidad:** Pipeline de detección híbrida que combina YOLO (red neuronal) con HSV (visión por color clásica).

### Interfaz Pública

```python
class Vision:
    def __init__(self, config: Config)
    def detect(self, frame: np.ndarray) -> Detections

@dataclass
class Ball:           # x, y normalizados (0-1), radius, confidence
@dataclass
class Goal:           # color ("blue"|"yellow"), x, y normalizados
@dataclass
class WhiteLine:      # detected (bool), position ("left"|"right"|"center")
@dataclass
class Detections:     # ball, goal, white_line, ts
```

### Pipeline de Detección (orden)

1. **YOLO:** Si el backend está disponible, ejecuta inferencia sobre el frame
2. **HSV pelota:** Convierte BGR→HSV, aplica máscara de color naranja (dos rangos para cubrir wrap-around del hue), filtra por área, circularidad y radio mínimo. Ignora bordes y franja superior ruidosa
3. **HSV porterías:** Detecta azul y amarillo por separado con umbrales de conteo de píxeles
4. **HSV línea blanca:** Inspecciona el tercio inferior del frame, umbraliza blanco, determina posición (izquierda/centro/derecha) por densidad de píxeles
5. **Fusión:** YOLO > HSV > caché con TTL de 0.5 segundos

### Backends YOLO

Ver [Backends YOLO](#backends-yolo) para detalles de implementación.

---

## Módulo: `pipeline.py`

**Responsabilidad:** Máquina de estados finita (FSM) que convierte detecciones en comandos de motores.

### Interfaz Pública

```python
class Pipeline:
    def __init__(self, config: Config)
    def tick(self, dets: Detections) -> MotorCommand
    def set_frame_width(self, w: int)
    @property state(self) -> str   # "SEARCH" | "CHASE" | "RECOVERY"
```

### Estados y Transiciones

```
SEARCH ──ball detected──► CHASE ──ball lost >0.8s──► RECOVERY
   ▲                         ▲                           │
   │                         │    ball re-detected        │
   │                         └───────────────────────────┘
   │                                     │
   └─────timeout (max_steps*2)───────────┘
```

### Lógica por Estado

#### SEARCH (`_tick_search`)
- Giro rotacional con pausas (`search_scan_secs=0.3s`)
- Dirección determinada por última posición conocida de la pelota
- Velocidad: `search_turn_speed=255`, duración: `search_turn_ms=250ms`

#### CHASE (`_tick_chase`)
- **Pelota visible:**
  - Si `radius >= kick_radius_px (50)`: avance recto a máxima velocidad (patada)
  - Si `|error_x| <= chase_deadband_px (16)`: avance recto (pelota centrada)
  - Si no: giro proporcional — `diff = base * error_norm * gain`, rueda externa acelera, interna desacelera (nunca negativa)
- **Pelota perdida < 0.8s:** avance recto a velocidad reducida (inercia)
- **Pelota perdida > 0.8s:** escaneo ciego con giros direccionales

#### RECOVERY (`_tick_recovery`)
- **Línea blanca detectada:** retroceder inmediatamente
- **Secuencia:** paso 0 → retroceso, paso impar → giro, paso par → avance
- Dirección de giro basada en última posición conocida de la pelota
- Máximo `recovery_max_steps * 2` pasos antes de volver a SEARCH

---

## Módulo: `motors.py`

**Responsabilidad:** Control de motores y servos vía UART serial con protocolo binario propietario.

### Interfaz Pública

```python
class Motors:
    def __init__(self, config: Config)
    def send(self, cmd: MotorCommand)
    def stop(self, dur_ms: int = 300)
    def close(self)

@dataclass
class MotorCommand:
    left_speed: float = 0.0     # Velocidad rueda izquierda (0-255)
    right_speed: float = 0.0    # Velocidad rueda derecha (0-255)
    dur_ms: int = 140           # Duración del comando
    pan_angle: float | None     # Ángulo servo pan (0-180)
    tilt_angle: float | None    # Ángulo servo tilt (0-180)
```

### Mapeo Diferencial

```
v_left positivo  → avance rueda izquierda
v_right negativo → avance rueda derecha

m1, m2 = 0.0, 0.0          (no son ruedas de tracción)
m3     = -v_right           (rueda derecha física)
m4     = -v_left            (rueda izquierda física)

Ejemplo avance recto:
  v_left=80, v_right=-80 → m3=80, m4=-80
```

### Saturación de Velocidad

```python
def _apply_diff_cap(v_left, v_right):
    mx = max(abs(v_left), abs(v_right))
    if mx > cap:            # cap = 250.0
        s = cap / mx        # escalar proporcionalmente
        v_left *= s
        v_right *= s
    return v_left, v_right
```

### Conversión Ángulo → PWM

```
pwm = 500 + (angle / 180.0) * 2000

0°   → 500µs
90°  → 1500µs
180° → 2500µs

Centros por defecto: pan=70°, tilt=45°
```

### Thread Safety

El envío UART está protegido por `threading.Lock`. Las dos tramas (servo + motor) se escriben atómicamente para evitar que comandos concurrentes intercalen bytes.

### Lazy Import

`import serial` ocurre dentro de `Motors.__init__`, no a nivel de módulo. Esto permite importar `MotorCommand` sin tener `pyserial` instalado (útil en tests y modo stub).

---

## Módulo: `main.py`

**Responsabilidad:** Punto de entrada. Inicializa servicios y ejecuta el bucle principal.

### Flujo de Inicialización

1. Crear `Config`
2. Según `FUTBOT_MODE`:
   - `stub` → `CameraStub` + `MotorsStub`
   - `real` → `Camera` + `Motors`
3. Crear `Vision(config)`
4. Crear `Pipeline(config)`, ajustar `frame_width`
5. Bucle principal: `grab → detect → tick → send`
6. Manejo de señales: `SIGINT` / `SIGTERM` para apagado limpio

### Apagado Limpio

```python
finally:
    mot.stop(200)    # Detener motores
    mot.close()      # Cerrar UART
    cam.release()    # Liberar cámara
```

### Modo Stub vs Real

La selección se hace una sola vez en `main()` sin afectar al resto del código. Los módulos `Vision` y `Pipeline` son idénticos en ambos modos — solo cambian las implementaciones de `Camera` y `Motors`.

---

## Sistema de Stubs

Los stubs permiten desarrollar y probar el sistema completo sin hardware físico.

### CameraStub (`stubs/camera_stub.py`)

```python
class CameraStub:
    width: int
    height: int
    grab() -> np.ndarray     # Frame sintético o pregrabado
    release()
```

**Comportamiento:**
- Si existe `stubs/test_frames/*.png`: reproduce los frames en secuencia
- Si no: genera frames sintéticos (fondo verde + círculo naranja en posición aleatoria)
- El círculo naranja es detectable por el pipeline HSV, permitiendo probar el FSM completo

### MotorsStub (`stubs/motors_stub.py`)

```python
class MotorsStub:
    send(cmd: MotorCommand)      # Registra el comando
    stop(dur_ms: int = 300)      # Registra stop
    close()
    get_history() -> list[MotorCommand]  # Historial de comandos
```

**Comportamiento:**
- Cada comando se almacena en una lista interna
- `get_history()` devuelve la lista para inspección en tests
- No requiere `pyserial`

---

## Protocolo UART de Motores

### Formato de Trama

Cada burst envía **dos tramas consecutivas**:

```
FRAME 1 — Servos (cmd 0x04)
┌──────┬──────┬──────┬──────┬─────────────────────────────────┬──────┐
│ 0xAA │ 0x55 │ 0x04 │ len  │           payload               │ CRC8 │
└──────┴──────┴──────┴──────┴─────────────────────────────────┴──────┘

Payload (11 bytes):
  [0x01]              — sub-comando
  [dur_low, dur_high] — duración en ms (uint16 LE)
  [0x02]              — cantidad de servos (2)
  [pan_id]            — ID servo pan (2)
  [pp_low, pp_high]   — PWM pan (uint16 LE)
  [tilt_id]           — ID servo tilt (1)
  [tp_low, tp_high]   — PWM tilt (uint16 LE)

FRAME 2 — Motores (cmd 0x03)
┌──────┬──────┬──────┬──────┬─────────────────────────────────┬──────┐
│ 0xAA │ 0x55 │ 0x03 │ len  │           payload               │ CRC8 │
└──────┴──────┴──────┴──────┴─────────────────────────────────┴──────┘

Payload (22 bytes):
  [0x05, 0x04]                  — sub-cmd + cantidad de motores (4)
  [0x00][m1 as float32 LE]      — motor 1 (5 bytes)
  [0x01][m2 as float32 LE]      — motor 2 (5 bytes)
  [0x02][m3 as float32 LE]      — motor 3 (5 bytes)
  [0x03][m4 as float32 LE]      — motor 4 (5 bytes)
```

### CRC8

- Polinomio: `0x07`
- Calculado sobre `bytes[2:]` (cmd + len + payload)
- Tabla de lookup pre-calculada de 256 elementos en `config.CRC8_TABLE`
- Se añade como byte final de cada trama

### Escritura Atómica

Ambas tramas se concatenan y escriben en una sola llamada `serial.write()` bajo `threading.Lock`:

```python
with self._lock:
    self._ser.write(servo_frame + motor_frame)
```

---

## Backends YOLO

### _YoloOnnxBackend

```python
class _YoloOnnxBackend:
    def __init__(self, config: Config)
    def infer(self, frame: np.ndarray) -> np.ndarray
```

**Pipeline:**
1. Redimensionar frame a `yolo_imgsz × yolo_imgsz` (320×320)
2. Transponer (HWC → CHW), añadir batch dim, normalizar a [0,1]
3. `session.run(None, {"images": img})` → outputs
4. Filtrar detecciones con confianza > 0.1

**Dependencia:** `onnxruntime` (grupo opcional `onnx`)

### _YoloNcnnBackend

```python
class _YoloNcnnBackend:
    def __init__(self, config: Config)
    def infer(self, frame: np.ndarray) -> np.ndarray
```

**Pipeline:**
1. Redimensionar frame a `yolo_imgsz × yolo_imgsz`
2. Convertir a `ncnn.Mat` (BGR → RGB internamente)
3. Normalizar: restar media [0,0,0], dividir por [255,255,255]
4. `extractor.input("in0", mat)` → `extractor.extract("out0")`
5. Convertir salida a numpy y filtrar

**Dependencia:** `ncnn` (grupo opcional `ncnn`). Optimizado para ARM NEON en RPi.

**Archivos de modelo esperados:**
```
models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model/
├── model.ncnn.param
├── model.ncnn.bin
└── metadata.yaml
```

### _YoloTensorrtBackend

```python
class _YoloTensorrtBackend:
    def __init__(self, config: Config)  # raise NotImplementedError
    def infer(self, frame: np.ndarray)   # return None
```

**Estado:** No implementado. Placeholder para futura aceleración por GPU.

### Selección de Backend

En `Vision._init_yolo()`:
```python
if backend == "onnx":    self._yolo = _YoloOnnxBackend(cfg)
elif backend == "ncnn":  self._yolo = _YoloNcnnBackend(cfg)
elif backend == "tensorrt": self._yolo = _YoloTensorrtBackend(cfg)
```

Si el backend falla (excepción), `self._yolo = None` y el sistema opera solo con HSV.

---

## Backends de Cámara

### Orden de Resolución

`Camera._resolve_backend()` prueba 4 backends en orden. El primero que entrega frames válidos se usa:

1. **picamera2** — `_try_picamera2()`
   - Import lazy: `from picamera2 import Picamera2`
   - Configura `RGB888`, inicia, captura frame de prueba
   - Envuelve en `_Picamera2Adapter` que convierte RGB→BGR

2. **libcamera subprocess** — `_try_libcamera_subprocess()`
   - Ejecuta `scripts/_libcamera_worker.py` con `/usr/bin/python3`
   - Comunicación por pipes: frames BGR por stdout, comandos por stdin
   - Protocolo binario con header de 20 bytes

3. **GStreamer** — `_try_gstreamer()`
   - Pipeline: `libcamerasrc ! videoconvert ! appsink`
   - Usa `cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)`

4. **V4L2** — `_try_v4l2_any()`
   - Enumera `/dev/video*`, prueba cada uno
   - Configura resolución y buffersize
   - Útil para webcams USB en desarrollo

### Warmup

Después de abrir la cámara, `_warmup()` descarta los primeros 10 frames para estabilizar exposición y balance de blancos.

---

## Cómo Extender el Sistema

### Agregar un Nuevo Backend YOLO

1. Crear clase en `vision.py`:
   ```python
   class _YoloMyBackend:
       def __init__(self, config: Config): ...
       def infer(self, frame: np.ndarray) -> np.ndarray: ...
   ```
2. Registrar en `Vision._init_yolo()`:
   ```python
   elif backend == "mybackend":
       self._yolo = _YoloMyBackend(self._cfg)
   ```
3. Agregar dependencia opcional en `pyproject.toml`

### Agregar un Nuevo Estado FSM

1. Definir constante en `pipeline.py`:
   ```python
   MY_STATE = "MY_STATE"
   ```
2. Agregar transiciones en `Pipeline.tick()`:
   ```python
   elif self._state == SOME_STATE:
       if condition:
           self._state = MY_STATE
   ```
3. Implementar método `_tick_mystate(self, ...)` → `MotorCommand`
4. Agregar constantes en `config.py`:
   ```python
   my_state_speed: float = 100.0
   my_state_duration_ms: int = 200
   ```

### Agregar un Nuevo Script de Diagnóstico

1. Crear archivo en `scripts/`
2. Importar `Config` de `config`:
   ```python
   import sys; sys.path.insert(0, "..")
   from config import Config
   ```
3. Ejecutar: `uv run python scripts/mi_script.py`

### Modificar Comportamiento sin Tocar Código

Todos los parámetros ajustables están en `Config`. Para cambiar comportamiento en runtime:

```python
from config import Config
cfg = Config(
    chase_speed_base=100.0,  # más rápido
    yolo_conf_threshold=0.3, # más permisivo
)
```

Pasar esta instancia a todos los módulos en `main.py`.

---

## Convenciones de Código

- **Idioma:** Docstrings y comentarios en español
- **Tipado:** Type hints en todas las funciones públicas (`from __future__ import annotations`)
- **Logging:** `logging.getLogger("futbot.<modulo>")`
- **Dataclasses:** Tipos compartidos como dataclasses inmutables
- **Imports:** Lazy imports para dependencias opcionales (serial, onnxruntime, ncnn, picamera2)
- **TDD:** Todo código nuevo requiere tests en `tests/` antes del commit
