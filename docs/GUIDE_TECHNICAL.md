# Guía Técnica — Futbot v9

**Audiencia:** Desarrolladores, arquitectos de software e ingenieros de robótica que desean entender, modificar o extender el sistema.
**Prerrequisitos:** Conocimientos de Python 3.11+, OpenCV, conceptos básicos de FSM y protocolos seriales.

---

## Tabla de Contenidos

1. [Resumen Ejecutivo](#resumen-ejecutivo)
2. [Arquitectura General](#arquitectura-general)
3. [API Reference](#api-reference)
4. [Módulo: `config.py`](#módulo-configpy)
5. [Módulo: `camera.py`](#módulo-camerapy)
6. [Módulo: `vision.py`](#módulo-visionpy)
7. [Módulo: `pipeline.py`](#módulo-pipelinepy)
8. [Módulo: `motors.py`](#módulo-motorspy)
9. [Módulo: `main.py`](#módulo-mainpy)
10. [Sistema de Stubs](#sistema-de-stubs)
11. [Protocolo UART de Motores](#protocolo-uart-de-motores)
12. [Backends YOLO](#backends-yolo)
13. [Backends de Cámara](#backends-de-cámara)
14. [Métricas de Rendimiento](#métricas-de-rendimiento)
15. [Estrategia de Pruebas](#estrategia-de-pruebas)
16. [Cómo Extender el Sistema](#cómo-extender-el-sistema)
17. [Convenciones de Código](#convenciones-de-código)
18. [Matriz de Compatibilidad](#matriz-de-compatibilidad)

---

## Resumen Ejecutivo

Futbot v9 es la novena iteración de un sistema de robótica autónoma para fútbol. Tras 8 versiones previas que acumularon complejidad incrementalmente (operadores anidados, DTOs, comunicación P2P WebSocket), la v9 unifica el código en una **arquitectura de módulos planos** con 6 archivos `.py` y ~1,500 líneas de código.

### Decisiones Clave de Arquitectura

| Decisión | Alternativa rechazada | Razón |
|----------|----------------------|-------|
| Módulos planos (1 archivo por responsabilidad) | Operadores anidados con DTOs (v2-v8) | Curva de aprendizaje plana. Un dev nuevo entiende el sistema en 8 archivos. |
| Inyección manual de dependencias (`main.py` pasa `Config`) | Contenedores DI, decoradores, providers | Sin frameworks. Explícito y depurable. |
| Dataclasses compartidos como tipos de frontera | DTOs por módulo con mapeo | 5 tipos bastan para describir todo el flujo de datos. |
| Lazy imports para dependencias opcionales | Imports a nivel de módulo con try/except | `motor.py` importable sin pyserial. `vision.py` importable sin onnxruntime. |
| FSM de 3 estados (SEARCH/CHASE/RECOVERY) | FSM de 4+ estados con roles (v8-ws) | Cobertura suficiente para juego 1v1 sin complejidad innecesaria. |

### Stack Tecnológico

```
┌─────────────────────────────────────────┐
│ Aplicación                              │
│  main.py → pipeline.py                  │
├─────────────────────────────────────────┤
│ Dominio                                 │
│  vision.py  ←→  motors.py               │
│  camera.py        config.py             │
├─────────────────────────────────────────┤
│ Bibliotecas                             │
│  opencv  onnxruntime/ncnn  pyserial     │
├─────────────────────────────────────────┤
│ Sistema Operativo                       │
│  Raspberry Pi OS (aarch64)              │
├─────────────────────────────────────────┤
│ Hardware                                │
│  RPi5  IMX219 CSI  Driver UART  Servos  │
└─────────────────────────────────────────┘
```

---

## Arquitectura General

### Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────────────┐
│                          main.py                                 │
│                                                                  │
│  cfg = Config()                                                  │
│  cam = Camera(cfg)  |  CameraStub(cfg)                           │
│  vis = Vision(cfg)                                               │
│  mot = Motors(cfg)  |  MotorsStub(cfg)                           │
│  pip = Pipeline(cfg)                                             │
│                                                                  │
│  while running:             ┌──────────────────────┐             │
│    frame = cam.grab() ──────┤ BGR H×W×3 uint8      │             │
│    dets  = vis.detect() ────┤ Detections dataclass  │             │
│    cmd   = pip.tick()  ─────┤ MotorCommand dataclass│             │
│    mot.send(cmd)       ─────┤ bytes → /dev/ttyAMA0  │             │
│                             └──────────────────────┘             │
└──────────────────────────────────────────────────────────────────┘
```

### Diagrama de Secuencia

```
main.py         Camera        Vision        Pipeline       Motors      Driver UART
  │               │             │              │              │              │
  ├─ Config() ────┤             │              │              │              │
  ├─ Camera(cfg)──┤             │              │              │              │
  │               ├─ _resolve_backend()        │              │              │
  │               │  ├─ try picamera2          │              │              │
  │               │  ├─ try libcamera sub      │              │              │
  │               │  ├─ try GStreamer          │              │              │
  │               │  └─ try V4L2              │              │              │
  │               ├─ _warmup() (10 frames)     │              │              │
  ├─ Vision(cfg)──┤             │              │              │              │
  │               │             ├─ _init_yolo()│              │              │
  │               │             │  └─ ONNX/NCNN/TensorRT      │              │
  ├─ Motors(cfg)───────────────┤              │              │              │
  │               │             │              │              ├─ serial.Serial()
  ├─ Pipeline(cfg)─────────────┤              │              │              │
  │               │             │              ├─ state=SEARCH│              │
  │               │             │              │              │              │
  │  ═══ BUCLE PRINCIPAL ═══════════════════════════════════  │              │
  │               │             │              │              │              │
  ├─ cam.grab() ──┤             │              │              │              │
  │               ├─ read() ────► Frame BGR    │              │              │
  ├─ vis.detect(frame) ────────►│              │              │              │
  │               │             ├─ YOLO infer  │              │              │
  │               │             ├─ HSV ball    │              │              │
  │               │             ├─ HSV goal    │              │              │
  │               │             ├─ HSV line    │              │              │
  │               │             └─ fuse ──────► Detections    │              │
  ├─ pip.tick(dets) ──────────────────────────►│              │              │
  │               │             │              ├─ eval FSM    │              │
  │               │             │              └─ MotorCommand│              │
  ├─ mot.send(cmd) ──────────────────────────────────────────►│              │
  │               │             │              │              ├─ _burst() ───► UART write
  │               │             │              │              │              │
  │  ═══ REPETIR ═══════════════════════════════════════════  │              │
```

### Dependencias entre Módulos

```
config.py ◄── camera.py     (Config)
config.py ◄── vision.py     (Config)
config.py ◄── motors.py     (Config, crc8)
config.py ◄── pipeline.py   (Config)
                  │
vision.py ────────┤ (Detections, Ball, Goal, WhiteLine)
motors.py ────────┤ (MotorCommand)
                  ▼
            pipeline.py
                  ▲
                  │
main.py ──────────┴── camera.py, vision.py, pipeline.py, motors.py
```

**No existen dependencias circulares.** `main.py` es el único punto de acoplamiento explícito.

---

## API Reference

### `camera.py`

```python
class Camera:
    def __init__(self, config: Config) -> None
    def grab(self) -> Optional[np.ndarray]
    def release(self) -> None
    @property width(self) -> int
    @property height(self) -> int
```

### `vision.py`

```python
@dataclass
class Ball:
    x: float           # Centro x normalizado (0.0 = izquierda, 1.0 = derecha)
    y: float           # Centro y normalizado (0.0 = arriba, 1.0 = abajo)
    radius: float      # Radio normalizado respecto a max(w, h)
    confidence: float  # Confianza de detección (0.0 - 1.0)

@dataclass
class Goal:
    color: str         # "blue" | "yellow"
    x: float           # Centro x normalizado
    y: float           # Centro y normalizado

@dataclass
class WhiteLine:
    detected: bool     # True si hay línea blanca visible
    position: str      # "left" | "right" | "center"

@dataclass
class Detections:
    ball: Ball | None = None
    goal: Goal | None = None
    white_line: WhiteLine | None = None
    ts: float = 0.0    # Timestamp Unix de procesamiento

class Vision:
    def __init__(self, config: Config) -> None
    def detect(self, frame: np.ndarray) -> Detections
```

### `pipeline.py`

```python
class Pipeline:
    def __init__(self, config: Config) -> None
    def tick(self, dets: Detections) -> MotorCommand
    def set_frame_width(self, w: int) -> None
    @property state(self) -> str  # "SEARCH" | "CHASE" | "RECOVERY"
```

### `motors.py`

```python
@dataclass
class MotorCommand:
    left_speed: float         # 0-255, positivo = avance rueda izquierda
    right_speed: float        # 0-255, negativo = avance rueda derecha
    dur_ms: int = 140         # Duración del comando en ms
    pan_angle: float | None   # 0-180°, None = mantener
    tilt_angle: float | None  # 0-180°, None = mantener

class Motors:
    def __init__(self, config: Config) -> None
    def send(self, cmd: MotorCommand) -> None
    def stop(self, dur_ms: int = 300) -> None
    def close(self) -> None
```

### `stubs/camera_stub.py`

```python
class CameraStub:
    def __init__(self, config: Config) -> None
    def grab(self) -> np.ndarray           # Frame sintético, nunca None
    def release(self) -> None
    @property width(self) -> int
    @property height(self) -> int
```

### `stubs/motors_stub.py`

```python
class MotorsStub:
    def __init__(self, config) -> None
    def send(self, cmd: MotorCommand) -> None
    def stop(self, dur_ms: int = 300) -> None
    def close(self) -> None
    def get_history(self) -> list[MotorCommand]
```

---

## Módulo: `config.py`

**Ruta:** `futbot/config.py` — 139 líneas.
**Dependencias:** Solo stdlib (`dataclasses`, `pathlib`, `typing`).

### Propósito

Fuente única de verdad para 35 parámetros configurables del robot. Expone también `CRC8_TABLE` (256 bytes) y `crc8(data)` para el protocolo UART de motores.

### Estructura del Dataclass

```python
@dataclass
class Config:
    # ── Cámara (6 campos)
    camera_width: int = 320
    camera_height: int = 240
    camera_fps: int = 30
    camera_backend: str = "libcamera"     # libcamera | gstreamer | opencv
    camera_exposure_default: int = 200
    camera_flip_horizontal: bool = False

    # ── Visión HSV pelota (13 campos)
    ball_hsv_lower: tuple = (0, 80, 80)
    ball_hsv_upper: tuple = (65, 255, 255)
    ball_hsv_lower2: tuple = (168, 80, 80)
    ball_hsv_upper2: tuple = (179, 255, 255)
    ball_min_area: int = 30
    # ... 9 campos adicionales de filtros

    # ── Visión HSV porterías (6 campos)
    goal_yellow_hsv_lower: tuple = (18, 130, 130)
    goal_blue_hsv_lower: tuple = (95, 180, 60)
    # ...

    # ── Visión línea blanca (4 campos)
    # ── Visión YOLO (9 campos)
    yolo_backend: str = "onnx"            # onnx | ncnn | tensorrt
    yolo_conf_threshold: float = 0.40
    # ...

    # ── Pipeline CHASE (8 campos)
    chase_speed_base: float = 80.0
    chase_rot_gain: float = 0.8
    chase_deadband_px: float = 16.0
    # ...

    # ── Pipeline SEARCH (4 campos)
    # ── Pipeline RECOVERY (5 campos)
    # ── Motores UART (3 campos)
    # ── Motores Servos (6 campos)
    # ── Rutas (1 campo)

    # ── Métodos helper (2)
    def resolve_yolo_model_path(self) -> Path: ...
    def resolve_ncnn_model_dir(self) -> Path: ...
```

### Principio de Extensibilidad

Cualquier parámetro se puede sobreescribir al instanciar:

```python
cfg = Config(chase_speed_base=100.0, yolo_backend="ncnn")
```

No se requiere modificar código fuente para ajustar comportamiento. Esto permite experimentación rápida sin riesgo de romper la configuración base.

---

## Módulo: `camera.py`

**Ruta:** `futbot/camera.py` — 302 líneas.
**Dependencias:** `opencv-python`, `numpy`, `config.Config`.

### Propósito

Abstraer la captura de frames de 4 backends diferentes detrás de una interfaz única (`grab() → np.ndarray`). La resolución de backend es automática y ocurre en `__init__`.

### Backends y Orden de Prioridad

| Prioridad | Backend | Método | Dependencia | Plataforma |
|-----------|---------|--------|------------|------------|
| 1 | picamera2 | `_Picamera2Adapter` | `picamera2` (lazy import) | RPi5 aarch64 |
| 2 | libcamera subprocess | `_LibcameraSubprocessAdapter` | `/usr/bin/python3`, `scripts/_libcamera_worker.py` | RPi5 aarch64 |
| 3 | GStreamer libcamerasrc | `cv2.VideoCapture` con pipeline GStreamer | `libcamera`, `gstreamer` | RPi5 aarch64 |
| 4 | V4L2 | `cv2.VideoCapture` sobre `/dev/video*` | Ninguna adicional | Cualquier Linux |

### Protocolo Binario del Subprocess libcamera

```
Header (20 bytes, little-endian):
  MAGIC    4B   b'\xf8\xb4\xc2\x0d'
  width    4B   uint32
  height   4B   uint32
  stride   4B   uint32 (bytes por fila)
  size     4B   uint32 (bytes totales del frame)

Frame:   BGR planar, stride // 4 columnas, 4 canales (BGRA)
         Se recorta a [:h, :w, :3] para obtener BGR puro.
```

### Warmup

`_warmup()` descarta los primeros 10 frames tras abrir la cámara. Esto es necesario porque las cámaras CSI requieren varias capturas para estabilizar exposición automática y balance de blancos. Sin warmup, los primeros frames pueden ser completamente negros o verdes.

---

## Módulo: `vision.py`

**Ruta:** `futbot/vision.py` — 324 líneas.
**Dependencias:** `opencv-python`, `numpy`, `config.Config`, `onnxruntime` (opcional), `ncnn` (opcional).

### Propósito

Pipeline de detección híbrido: YOLO (red neuronal) + HSV (visión clásica por color). La fusión da prioridad a YOLO cuando está disponible y tiene confianza suficiente, con HSV como fallback determinista y caché TTL de 0.5 segundos para suavizar detecciones intermitentes.

### Flujo de `detect(frame)`

```
1. YOLO inferencia
   └─ Resize 320×320 → normalize /255 → session.run / net.extract
   └─ _parse_yolo_ball: filtrar por class_id + confianza
   └─ Produce Ball (x, y, radius, confidence)

2. HSV pelota naranja
   └─ BGR→HSV → inRange(2 rangos, wrap-around hue) → findContours
   └─ Filtrar: área, radio, circularidad, bordes, hot_pixel_y_max
   └─ Produce Ball (confidence=0.7 fijo)

3. HSV porterías
   └─ inRange azul → countNonZero → moments → Goal("blue", x, y)
   └─ inRange amarillo → countNonZero → moments → Goal("yellow", x, y)

4. HSV línea blanca
   └─ ROI = tercio inferior del frame
   └─ inRange blanco (V alto, S bajo) → countNonZero
   └─ Comparar mitad izquierda vs derecha → posición

5. Fusión
   └─ YOLO (si confianza ≥ threshold) > HSV > caché (TTL 0.5s)
```

### Backends YOLO

Ver [Backends YOLO](#backends-yolo) para detalles de implementación de cada backend.

---

## Módulo: `pipeline.py`

**Ruta:** `futbot/pipeline.py` — 198 líneas.
**Dependencias:** `config.Config`, `vision.Detections`, `vision.Ball`, `motors.MotorCommand`.

### Propósito

Máquina de estados finita que convierte detecciones (`Detections`) en comandos de motores (`MotorCommand`). Opera a ~100 Hz (limitado por `time.sleep(0.01)` en `main.py`).

### Tabla de Transiciones

| Estado actual | Condición | Estado siguiente | Reset al entrar |
|--------------|-----------|-----------------|-----------------|
| SEARCH | `ball != None` | CHASE | `_last_chase_time = 0` |
| CHASE | `ball == None AND miss_secs ≥ 0.8` | RECOVERY | `_recovery_step = 0`, elegir dirección |
| RECOVERY | `ball != None` | CHASE | `_last_chase_time = 0` |
| RECOVERY | `_recovery_step ≥ max_steps * 2` | SEARCH | `_last_search_time = 0`, `_last_cx = None` |

### Lógica de Control por Estado

#### SEARCH — `_tick_search(now)`
```
Cada search_scan_secs (0.3s):
  dirección = last_cx < frame_center ? "left" : "right"
  v_left  = -search_turn_speed (255) si left, +255 si right
  v_right = +search_turn_speed (255) si left, -255 si right
  dur_ms  = search_turn_ms (250)
Entre pasos: MotorCommand(0, 0) — pausa activa
```

#### CHASE — `_tick_chase(now, ball, ball_visible, frame_center)`

**Con pelota visible:**
```
Si radius ≥ kick_radius_px (50):  # patada directa
  MotorCommand(base, base, 100)
Si |cx - center| ≤ deadband (16 px):  # centrado
  MotorCommand(base, base, 100)
Si no:  # servo visual proporcional
  error_norm = |error| / frame_center  (0 a 1)
  diff = base * error_norm * rot_gain  (0.8)
  Si error > 0:  vL = base + diff,  vR = max(0, base - diff)
  Si error < 0:  vL = max(0, base - diff), vR = base + diff
```

**Pelota perdida < 0.8s:** inercia — `MotorCommand(blind_speed, blind_speed, 100)`

**Pelota perdida ≥ 0.8s:** escaneo ciego con giros direccionales cada `blind_scan_secs` (0.2s)

#### RECOVERY — `_tick_recovery(now, ball_visible, line)`
```
Si línea blanca detectada: retroceder inmediatamente
Secuencia (step 0..max_steps*2 - 1):
  step == 0:              retroceso
  step impar:             giro en recovery_dir
  step par (no cero):     avance corto
```

---

## Módulo: `motors.py`

**Ruta:** `futbot/motors.py` — 134 líneas.
**Dependencias:** `pyserial` (lazy), `config.Config`, `config.crc8`.

### Propósito

Control de motores y servos vía UART serial usando un protocolo binario propietario. Cada comando de alto nivel (`MotorCommand`) se traduce a dos tramas binarias con CRC8 y se envía atómicamente al driver en `/dev/ttyAMA0` a 1 MBaud.

### Pipeline de `send(cmd)`

```
1. _apply_diff_cap(vL, vR)
   └─ Saturar velocidades a max 250.0, escalando proporcionalmente

2. _differential(vL, vR)
   └─ (0.0, 0.0, -vR, -vL)
   └─ m1 y m2 siempre 0 (no usados para tracción)
   └─ m3 = -vR (rueda derecha física)
   └─ m4 = -vL (rueda izquierda física)

3. _burst(pan, tilt, dur_ms, m1, m2, m3, m4)
   └─ Convertir ángulos a PWM (500-2500 µs)
   └─ Construir trama servos (cmd 0x04, 11 bytes payload) + CRC8
   └─ Construir trama motores (cmd 0x03, 22 bytes payload) + CRC8
   └─ Escribir atómicamente al UART bajo threading.Lock
```

### Thread Safety

```python
with self._lock:
    self._ser.write(servo_frame + motor_frame)
```

El `threading.Lock` garantiza que las dos tramas de un comando se escriban sin intercalación de otro comando concurrente. Sin esto, dos hilos podrían alternar bytes y corromper el protocolo.

---

## Módulo: `main.py`

**Ruta:** `futbot/main.py` — 105 líneas.
**Dependencias:** Todos los módulos del proyecto.

### Propósito

Orquestador del sistema. Único punto de entrada. Responsable de:
1. Instanciar `Config`
2. Seleccionar implementaciones reales o stub según `FUTBOT_MODE`
3. Conectar los 4 módulos en el orden correcto
4. Ejecutar el bucle principal
5. Manejar señales de apagado (`SIGINT`, `SIGTERM`)

### Ciclo de Vida

```python
Config()                           # Parámetros por defecto
Camera(cfg) | CameraStub(cfg)      # Según FUTBOT_MODE
Vision(cfg)                        # Inicializa backend YOLO
Motors(cfg) | MotorsStub(cfg)      # Según FUTBOT_MODE
Pipeline(cfg)                      # Estado inicial = SEARCH

while running:
    frame = cam.grab()             # np.ndarray o None
    dets  = vis.detect(frame)      # Detections
    cmd   = pip.tick(dets)         # MotorCommand
    mot.send(cmd)                  # UART write o registro
    sleep(0.01)

finally:
    mot.stop(200); mot.close()     # Apagado limpio
    cam.release()                  # Liberar cámara
```

---

## Sistema de Stubs

**Ubicación:** `futbot/stubs/`

### CameraStub

Genera frames sintéticos de 320×240 con:
- Fondo verde oscuro (BGR 50,120,50) simulando césped
- Círculo naranja (BGR 0,140,255) en posición aleatoria dentro del 50% central
- Radio fijo de 25 píxeles — detectable por el pipeline HSV

Si existe `stubs/test_frames/*.png`, reproduce esos frames en secuencia circular. Útil para pruebas deterministas con frames reales capturados del robot.

### MotorsStub

Implementa la misma interfaz que `Motors` pero sin dependencia de `pyserial`:
- `send(cmd)` → copia el comando a una lista interna
- `get_history()` → devuelve el historial cronológico de comandos
- `stop()` / `close()` → no-ops que registran el comando

### Activación

Controlado por la variable de entorno `FUTBOT_MODE`:
- `FUTBOT_MODE=stub` → stubs
- `FUTBOT_MODE=real` o sin definir → hardware real

La selección ocurre únicamente en `main.py`. Los módulos `Vision` y `Pipeline` son idénticos en ambos modos.

---

## Protocolo UART de Motores

### Estructura General

Cada comando de alto nivel produce un **burst** de dos tramas consecutivas:

```
FRAME 1 — Servos (cmd 0x04)
┌─────┬─────┬─────┬─────┬───────────────────────────┬──────┐
│0xAA │0x55 │0x04 │ len │         payload           │ CRC8 │
└─────┴─────┴─────┴─────┴───────────────────────────┴──────┘

Payload (11 bytes):
  byte 0:    0x01 (sub-comando)
  byte 1-2:  dur_ms (uint16 LE)
  byte 3:    0x02 (2 servos)
  byte 4:    servo_pan_id (2)
  byte 5-6:  pan_pwm (uint16 LE)
  byte 7:    servo_tilt_id (1)
  byte 8-9:  tilt_pwm (uint16 LE)

FRAME 2 — Motores (cmd 0x03)
┌─────┬─────┬─────┬─────┬───────────────────────────┬──────┐
│0xAA │0x55 │0x03 │ len │         payload           │ CRC8 │
└─────┴─────┴─────┴─────┴───────────────────────────┴──────┘

Payload (22 bytes):
  byte 0-1: 0x05, 0x04 (sub-cmd + 4 motores)
  byte 2:   0x00 (índice motor 0)
  byte 3-6: m1 (float32 LE)
  byte 7:   0x01 (índice motor 1)
  byte 8-11: m2 (float32 LE)
  byte 12:  0x02 (índice motor 2)
  byte 13-16: m3 (float32 LE)
  byte 17:  0x03 (índice motor 3)
  byte 18-21: m4 (float32 LE)
```

### Cálculo CRC8

- **Polinomio:** 0x07
- **Rango de bytes:** `frame[2:]` (cmd + len + payload, excluyendo header)
- **Tabla:** Pre-calculada de 256 elementos en `config.CRC8_TABLE`
- **Implementación:**
  ```python
  def crc8(data: bytes) -> int:
      c = 0
      for b in data:
          c = CRC8_TABLE[c ^ b]
      return c
  ```

### Conversión Ángulo → PWM

```
pwm = 500 + (angle / 180.0) × 2000

Ángulo:  0°    45°    90°    180°
PWM:     500   1000   1500   2500  µs
```

Ángulos centrales por defecto:
- `pan_center = 70°` → PWM ~1278 µs
- `tilt_center = 45°` → PWM ~1000 µs

### Mapeo Diferencial

```
v_left positivo  → rueda izquierda avanza
v_right negativo → rueda derecha avanza

m1 = 0.0       (motor 1 — no usado para tracción)
m2 = 0.0       (motor 2 — no usado para tracción)
m3 = -v_right  (motor 3 — rueda derecha física)
m4 = -v_left   (motor 4 — rueda izquierda física)

Ejemplos:
  Avance recto:       vL=80,  vR=-80  → m3=80,  m4=-80
  Retroceso:           vL=-80, vR=80   → m3=-80, m4=80
  Giro izquierda:     vL=-80, vR=-80  → m3=80,  m4=80
  Giro derecha:       vL=80,  vR=80   → m3=-80, m4=-80
  Stop:               vL=0,   vR=0    → m3=0,   m4=0
```

---

## Backends YOLO

### `_YoloOnnxBackend`

**Pipeline:** resize 320² → transpose HWC→CHW → add batch dim → normalize /255.0 → `session.run({"images": img})` → filtrar confianza >0.1.

**Ventajas:** Multiplataforma (x86, ARM, CUDA), formato de modelo portable (.onnx).
**Desventajas:** Mayor latencia en RPi5 (~45 ms) comparado con NCNN.

### `_YoloNcnnBackend`

**Pipeline:** resize 320² → `ncnn.Mat.from_pixels(BGR)` → `substract_mean_normalize([0,0,0], [1/255]³)` → `extractor.input → extractor.extract` → filtrar.

**Ventajas:** Optimizado para ARM NEON. ~2× más rápido que ONNX en RPi5 (~22 ms).
**Desventajas:** Solo Linux aarch64. Requiere archivos .param y .bin (formato NCNN específico).

**Archivos esperados en el modelo:**
```
models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model/
├── model.ncnn.param
├── model.ncnn.bin
└── metadata.yaml
```

### `_YoloTensorrtBackend`

**Estado:** No implementado. `__init__` lanza `NotImplementedError`. `infer()` retorna `None`.
**Propósito futuro:** Aceleración por GPU/NPU en hardware compatible (Jetson, aceleradoras PCIe).

### Selección de Backend

```python
# En Vision._init_yolo():
if backend == "onnx":     self._yolo = _YoloOnnxBackend(cfg)
elif backend == "ncnn":   self._yolo = _YoloNcnnBackend(cfg)
elif backend == "tensorrt": self._yolo = _YoloTensorrtBackend(cfg)
```

Si la inicialización lanza excepción, `self._yolo = None` y el sistema continúa solo con HSV.

---

## Backends de Cámara

### Tabla Comparativa

| Backend | Inicialización | Latencia | Robustez | Usar cuando |
|---------|---------------|----------|----------|------------|
| picamera2 | ~0.5s | Baja (~5ms) | Alta | RPi5 con picamera2 instalado |
| libcamera subprocess | ~1-15s | Media (~15ms) | Media | RPi5 sin picamera2 |
| GStreamer | ~0.3s | Media (~20ms) | Media | RPi5 con GStreamer y libcamera |
| V4L2 | ~0.2s | Variable | Baja | Desarrollo en laptop con webcam USB |

### Resolución Automática

`Camera.__init__()` recorre los 4 backends en orden. El primero que entrega un frame válido se usa. Si ninguno funciona, lanza `RuntimeError` con instrucciones de diagnóstico.

---

## Métricas de Rendimiento

### Pipeline de Visión

| Operación | ONNX Runtime | NCNN (ARM NEON) | Solo HSV |
|-----------|-------------|-----------------|----------|
| Captura de frame | ~3 ms | ~3 ms | ~3 ms |
| YOLO resize + normalize | ~2 ms | ~2 ms | — |
| YOLO inferencia | ~40 ms | ~17 ms | — |
| YOLO parse output | ~0.5 ms | ~0.5 ms | — |
| HSV pelota | ~2 ms | ~2 ms | ~2 ms |
| HSV porterías | ~1 ms | ~1 ms | ~1 ms |
| HSV línea blanca | ~1 ms | ~1 ms | ~1 ms |
| Fusión | ~0.1 ms | ~0.1 ms | ~0.1 ms |
| **Total detect()** | **~45 ms** | **~22 ms** | **~5 ms** |

> Mediciones en Raspberry Pi 5, modelo yoloe26n_v2, 320×240, CPU a 2.4 GHz, 4 núcleos activos.

### Throughput del Pipeline Completo

| Modo | Latencia por ciclo | FPS máximo teórico | FPS efectivo (con sleep 0.01s) |
|------|-------------------|-------------------|-------------------------------|
| ONNX | ~55 ms | ~18 | ~18 |
| NCNN | ~30 ms | ~33 | ~33 |
| HSV solo | ~12 ms | ~83 | ~83 |

> El FPS efectivo está acotado por `time.sleep(0.01)` en `main.py`, que impone un máximo de ~100 FPS. Para aumentar el FPS, reducir o eliminar este sleep (a costa de mayor uso de CPU).

### Uso de Recursos

| Modo | CPU (4 núcleos) | RAM | Swap |
|------|-----------------|-----|------|
| ONNX | 80-90% | ~180 MB | 0 |
| NCNN | 50-60% | ~150 MB | 0 |
| HSV solo | 15-20% | ~120 MB | 0 |

---

## Estrategia de Pruebas

### Pirámide de Testing

```
         ┌─────────┐
         │   E2E   │  1 test  — test_integration.py (bucle completo con stubs)
         ├─────────┤
         │  Unit   │  15 tests — test_config, test_camera, test_vision,
         │         │              test_motors, test_pipeline
         └─────────┘
```

### Tests Unitarios

| Módulo | Archivo | Enfoque |
|--------|---------|---------|
| config | `test_config.py` | Constantes por defecto, función CRC8 |
| camera | `test_camera.py` | Instanciación sin hardware (espera RuntimeError) |
| vision | `test_vision.py` | Dataclasses, detección HSV con frames sintéticos (círculo naranja) |
| motors | `test_motors.py` | MotorCommand, mapeo diferencial, conversión PWM, CRC8 en trama |
| pipeline | `test_pipeline.py` | FSM: inicia en SEARCH, transición a CHASE, servo visual centrado, transición a RECOVERY |

### Test de Integración

`test_integration.py` ejecuta 10 ticks del bucle completo con `CameraStub` y `MotorsStub`. Verifica que:
1. Se producen comandos de motor (al menos 1)
2. Las velocidades están en rango [-300, 300]
3. El pipeline no crashea en 10 iteraciones

### CI/CD Sugerido

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install uv && cd futbot && uv sync
      - run: cd futbot && FUTBOT_MODE=stub uv run pytest tests/ -v
```

---

## Cómo Extender el Sistema

### Agregar un Nuevo Backend YOLO

1. Crear clase en `vision.py`:
   ```python
   class _YoloMyBackend:
       def __init__(self, config: Config): ...
       def infer(self, frame: np.ndarray) -> Optional[np.ndarray]: ...
       def _process_output(self, output) -> Optional[np.ndarray]: ...
   ```

2. Registrar en `Vision._init_yolo()`:
   ```python
   elif backend == "mybackend":
       self._yolo = _YoloMyBackend(self._cfg)
   ```

3. Agregar como dependencia opcional en `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   mybackend = ["mi-libreria>=1.0"]
   ```

### Agregar un Nuevo Estado FSM

1. Definir constante en `pipeline.py`:
   ```python
   MY_STATE = "MY_STATE"
   ```

2. Agregar transición en `Pipeline.tick()`:
   ```python
   elif self._state == EXISTING_STATE:
       if transition_condition:
           self._state = MY_STATE
   ```

3. Implementar método `_tick_mystate(self, ...)` → `MotorCommand`

4. Agregar constantes en `Config`:
   ```python
   my_state_param: float = 100.0
   ```

### Agregar un Nuevo Backend de Cámara

1. Crear método `_try_mybackend(self, w, h)` en `Camera`
2. Agregar al orden en `_resolve_backend()`:
   ```python
   cap = self._try_mybackend(w, h)
   if cap:
       return cap, w, h
   ```
3. Si requiere adaptador, crear clase `_MyBackendAdapter` con interfaz `read()`/`release()`

---

## Convenciones de Código

| Aspecto | Convención |
|---------|-----------|
| Idioma | Docstrings y comentarios en español |
| Tipado | `from __future__ import annotations`. Type hints en todas las funciones públicas. |
| Logging | `logging.getLogger("futbot.<modulo>")`. Niveles: INFO para hitos, WARNING para fallbacks, ERROR para excepciones. |
| Dataclasses | Tipos compartidos como `@dataclass` con valores por defecto. |
| Imports | Lazy para dependencias opcionales (`serial`, `onnxruntime`, `ncnn`, `picamera2`). |
| TDD | Todo código nuevo requiere test antes del commit. |
| Commits | Formato: `<tipo>: <descripción en español>`. Tipos: `feat`, `fix`, `docs`, `chore`, `refactor`. |
| Sin dependencias circulares | `vision.py` ← `pipeline.py` → `motors.py`. `pipeline.py` importa tipos, no instancias. |

---

## Matriz de Compatibilidad

### Python y Bibliotecas

| Python | OpenCV | ONNX Runtime | NCNN | PySerial | Estado |
|--------|--------|-------------|------|----------|--------|
| 3.11 | 4.13+ | 1.24+ | ✓ | 3.5+ | ✅ Soportado |
| 3.12 | 4.13+ | 1.24+ | ✓ | 3.5+ | ✅ Recomendado |
| 3.13 | 4.13+ | 1.24+ | ✗ | 3.5+ | ⚠️ NCNN no probado |
| 3.14 | 4.13+ | 1.24+ | ✗ | 3.5+ | ⚠️ NCNN no probado |
| 3.15+ | — | — | — | — | ❌ Bloqueado por `requires-python` |

### Plataformas

| Plataforma | picamera2 | libcamera subprocess | GStreamer | V4L2 | ONNX | NCNN |
|-----------|-----------|---------------------|-----------|------|------|------|
| RPi5 (aarch64) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| RPi4 (aarch64) | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Linux x86_64 (dev) | ✗ | ✗ | ✗ | ✅ | ✅ | ✗ |
| macOS (dev) | ✗ | ✗ | ✗ | ✅ | ✅ | ✗ |
| Windows (dev) | ✗ | ✗ | ✗ | ⚠️ | ✅ | ✗ |

### Backends YOLO vs Plataforma

| Backend | RPi5 | RPi4 | x86_64 Linux | macOS | Windows |
|---------|------|------|-------------|-------|---------|
| ONNX | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| NCNN | ✅ | ⚠️ | ✗ | ✗ | ✗ |
| TensorRT | ✗ | ✗ | ✗ | ✗ | ✗ |
| Solo HSV | ✅ | ✅ | ✅ | ✅ | ✅ |
