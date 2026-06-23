# Refactor de Futbot — Documento de Diseño

**Fecha:** 2026-06-22
**Rama:** `develop` (a crear manualmente por el usuario)
**Estado:** Diseño aprobado — pendiente de implementación

---

## 1. Motivación

El código de futbot ha acumulado 9 directorios de versiones (v2 a v8, más ws) a lo largo del tiempo. Cada versión agregó funcionalidades de forma incremental sin limpiar las iteraciones anteriores, resultando en:

- Código duplicado entre versiones
- Código muerto (firmware Arduino, HuskyLens, P2P WebSocket)
- Un exceso de capas tipo NestJS (servicio/operador/DTO) heredado de `futbot-ws` que introduce abstracción innecesaria para un sistema de un solo robot
- Curva de aprendizaje elevada para nuevos colaboradores

Este refactor unifica las mejores partes de todas las versiones en una sola base de código plana, modular y optimizada para un robot autónomo independiente sobre Raspberry Pi 5.

---

## 2. Decisiones de Diseño

| Decisión | Justificación |
|----------|---------------|
| **Estructura plana** (un `.py` por responsabilidad, sin subdirectorios) | Máxima claridad con mínimos archivos. Un desarrollador nuevo entiende el proyecto leyendo 8 archivos. |
| **YOLO multi-backend conservado** (ONNX + NCNN + TensorRT) | Requerido. Da flexibilidad para aceleración por hardware en RPi5. |
| **Stubs de hardware conservados** | Requerido. Permite desarrollo y pruebas locales sin el robot físico. |
| **P2P WebSocket + roles eliminados** | No se necesita. Solo un robot autónomo. |
| **Ultrasónico eliminado** | Ya no se utiliza. |
| **Código Arduino/HuskyLens eliminado** | Prototipos legacy, no usados en el sistema RPi5 actual. |
| **Inyección de dependencias manual** (sin contenedores DI) | Paso simple por constructor en `main.py`. Sin decoradores, providers ni frameworks. |
| **Dataclasses para tipos compartidos** | Ligeros, sin dependencias externas, amigables con el IDE. |
| **`config.py` como fuente única de verdad** | Todas las constantes, umbrales, rutas y puertos en un solo lugar. |
| **Variable de entorno `FUTBOT_MODE`** (`real` / `stub`) | Intercambia hardware real por mocks sin cambiar código. |

---

## 3. Estructura Final del Proyecto

```
futbot/
├── main.py                 # Punto de entrada: inicializa servicios, ejecuta el bucle FSM
├── config.py               # Todas las constantes: velocidades, umbrales, puertos, rutas
├── camera.py               # Captura de frames (libcamera/GStreamer/OpenCV)
├── vision.py               # YOLO multi-backend + HSV + fusión de detecciones
├── pipeline.py             # FSM: BUSCAR → PERSEGUIR → RECUPERAR
├── motors.py               # Driver UART serial de motores (protocolo binario + CRC8 + servos)
├── stubs/                  # Mocks de hardware para desarrollo local
│   ├── __init__.py
│   ├── camera_stub.py
│   ├── motors_stub.py
│   └── test_frames/        # Frames pregrabados para pruebas
├── models/                 # Modelos ML (ONNX, NCNN, TensorRT)
├── scripts/                # Herramientas de diagnóstico y calibración
├── tests/                  # Suite de pruebas con pytest
├── docs/                   # Planes de diseño y documentación
├── pyproject.toml          # Dependencias Python gestionadas con uv
├── Changelog.md            # Historial de versiones rastreado desde archivos
└── README.md               # Documentación del proyecto
```

---

## 4. Responsabilidades de Cada Módulo

### 4.1 `main.py`
- Inicializa los servicios en orden: Cámara → Visión → Motores → Pipeline
- Ejecuta el bucle principal: `frame = cam.grab()` → `dets = vis.detect(frame)` → `cmd = pip.tick(dets)` → `mot.send(cmd)`
- Maneja SIGINT/SIGTERM para apagado limpio
- Lee la variable de entorno `FUTBOT_MODE` para seleccionar backends reales o stubs

```python
# pseudocódigo de main.py
import os, signal
from camera import Camera
from vision import Vision
from motors import Motors
from pipeline import Pipeline
from config import Config
from stubs.camera_stub import CameraStub
from stubs.motors_stub import MotorsStub

mode = os.environ.get("FUTBOT_MODE", "real")
cfg = Config()

cam = CameraStub(cfg) if mode == "stub" else Camera(cfg)
vis = Vision(cfg)
mot = MotorsStub(cfg) if mode == "stub" else Motors(cfg)
pip = Pipeline(cfg)

running = True
signal.signal(signal.SIGINT, lambda *_: setattr(sys.modules[__name__], "running", False))

while running:
    frame = cam.grab()
    dets = vis.detect(frame)
    cmd = pip.tick(dets)
    mot.send(cmd)

mot.stop()
cam.release()
```

### 4.2 `config.py`
Archivo único con todos los valores configurables. Sin imports de otros módulos del proyecto.

```python
@dataclass
class Config:
    # Cámara
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    camera_backend: str = "libcamera"  # libcamera | gstreamer | opencv

    # Visión
    yolo_model_path: str = "models/onnx/yolo26n.onnx"
    yolo_backend: str = "onnx"  # onnx | ncnn | tensorrt
    yolo_conf_threshold: float = 0.3
    ball_hsv_lower: tuple = (10, 100, 100)
    ball_hsv_upper: tuple = (30, 255, 255)
    goal_blue_hsv_lower: tuple = (90, 50, 50)
    goal_blue_hsv_upper: tuple = (130, 255, 255)
    goal_yellow_hsv_lower: tuple = (20, 50, 50)
    goal_yellow_hsv_upper: tuple = (40, 255, 255)

    # Pipeline (FSM)
    search_speed: float = 0.4
    chase_speed: float = 0.7
    recovery_speed: float = 0.5
    chase_kp: float = 1.5          # ganancia proporcional para servo visual
    search_rotation_speed: float = 0.3
    max_search_duration_ms: int = 5000
    ball_lost_timeout_ms: int = 2000

    # Motores
    uart_port: str = "/dev/ttyAMA0"
    uart_baud: int = 1000000
    servo_pan_id: int = 2
    servo_tilt_id: int = 1
    servo_center_pan: float = 90.0
    servo_center_tilt: float = 90.0

    # Directorio de modelos
    models_dir: str = "models"
```

### 4.3 `camera.py`
- **Clase `Camera`**: envuelve `VideoCapture` de OpenCV con backend libcamera/GStreamer
- `grab() -> np.ndarray`: devuelve frame BGR como array numpy
- Detección automática de backend para RPi5 (libcamera CSI → pipeline GStreamer → fallback OpenCV)
- Maneja frames de calentamiento, reconexión ante fallos, timeout

```python
class Camera:
    def __init__(self, config: Config): ...
    def grab(self) -> np.ndarray: ...
    def release(self): ...
```

### 4.4 `vision.py`
- **Clase `Vision`**: pipeline unificado de detección
- `detect(frame: np.ndarray) -> Detections`: ejecuta inferencia YOLO + fallback HSV + detección de portería + detección de línea blanca
- YOLO multi-backend: selecciona ONNX, NCNN o TensorRT según configuración y disponibilidad
- Fusión de pelota: combina detecciones YOLO con segmentación de color HSV
- Detección de portería: identifica portería azul vs amarilla por umbrales de color en ROI
- Detección de línea blanca: umbralizado + operaciones morfológicas para detectar borde del campo

```python
class Vision:
    def __init__(self, config: Config): ...
    def detect(self, frame: np.ndarray) -> Detections: ...

@dataclass
class Ball:
    x: float          # centro x normalizado (0.0 a 1.0)
    y: float          # centro y normalizado
    radius: float     # radio normalizado
    confidence: float

@dataclass
class Goal:
    color: str        # "blue" | "yellow"
    x: float
    y: float

@dataclass
class WhiteLine:
    detected: bool
    position: str     # "left" | "right" | "center"

@dataclass
class Detections:
    ball: Ball | None = None
    goal: Goal | None = None
    white_line: WhiteLine | None = None
```

### 4.5 `pipeline.py`
- **Clase `Pipeline`**: controlador FSM con 3 estados
- `tick(dets: Detections) -> MotorCommand`: evalúa el estado actual, transiciona si es necesario, devuelve comando de motores
- Importa `MotorCommand` desde `motors.py`, `Detections` desde `vision.py`
- Estados: `BUSCAR` → `PERSEGUIR` → `RECUPERAR`
  - **BUSCAR**: Barrido rotacional para encontrar la pelota. Si se detecta → PERSEGUIR.
  - **PERSEGUIR**: Servo visual — el error horizontal controla el giro diferencial, velocidad de avance proporcional al tamaño de la pelota. Si se pierde la pelota > timeout → RECUPERAR.
  - **RECUPERAR**: Búsqueda en espiral para readquirir la pelota. Si se detecta línea blanca → retroceder y girar. Si se encuentra la pelota → PERSEGUIR. Si timeout → BUSCAR.

```python
class Pipeline:
    def __init__(self, config: Config): ...
    def tick(self, dets: Detections) -> MotorCommand: ...
```

### 4.6 `motors.py`
- **Clase `Motors`**: comunicación UART serial con la placa driver de motores
- `send(cmd: MotorCommand)`: convierte a tramas de protocolo binario, escribe al puerto serial
- Protocolo binario: dos tramas (trama de servos + trama de motores) con CRC8, escritas atómicamente bajo lock
- Mapeo de tracción diferencial: `(v_left, v_right)` → `(m1, m2, m3, m4)` valores float32
- Control de servos: ángulos pan/tilt → anchos de pulso PWM (500-2500µs)
- Reconexión automática ante fallo del puerto serial
- Define el dataclass `MotorCommand` (consumido por `pipeline.py`)

```python
@dataclass
class MotorCommand:
    left_speed: float     # -1.0 a 1.0
    right_speed: float    # -1.0 a 1.0
    pan_angle: float | None = None    # servo pan
    tilt_angle: float | None = None   # servo tilt

class Motors:
    def __init__(self, config: Config): ...
    def send(self, cmd: MotorCommand): ...
    def stop(self): ...
```

### 4.7 `stubs/`
Implementaciones mock para desarrollo local sin hardware físico:

- **`camera_stub.py`**: `CameraStub` lee frames pregrabados desde `stubs/test_frames/` en secuencia o aleatoriamente
- **`motors_stub.py`**: `MotorsStub` registra `MotorCommand` en stdout/archivo en lugar de enviar por serial

Se activan con `FUTBOT_MODE=stub`.

---

## 5. Flujo de Datos

```
┌─────────┐     np.ndarray     ┌─────────┐    Detections    ┌──────────┐   MotorCommand   ┌────────┐
│ camera  │ ──────────────────►│ vision  │ ────────────────►│ pipeline │ ────────────────►│ motors │
│   .py   │                    │   .py   │                  │   .py    │                   │  .py   │
└─────────┘                    └─────────┘                  └──────────┘                   └────────┘
                                                                                               │
                                                                                      UART serial
                                                                                               │
                                                                                     ┌─────────▼─────────┐
                                                                                     │ Placa driver de   │
                                                                                     │ motores           │
                                                                                     │ (/dev/ttyAMA0)    │
                                                                                     └───────────────────┘
```

`main.py` orquesta el bucle. Reglas de dependencia:
- Todos los módulos dependen de `config.py`
- `vision.py` define `Detections`, `Ball`, `Goal`, `WhiteLine` — sin imports de otros módulos
- `motors.py` define `MotorCommand` — sin imports de otros módulos (excepto `config.py`)
- `pipeline.py` importa `Detections` de `vision.py` y `MotorCommand` de `motors.py`
- `main.py` importa todos los módulos y los conecta entre sí
- Sin dependencias circulares: `vision.py` ← `pipeline.py` → `motors.py`

---

## 6. Lo Que Se Conserva

| Componente | Origen en v8 | Destino |
|-----------|-------------|---------|
| Controlador FSM de 3 estados | `src/pipeline/pipeline_service.py` + `operators/` | `pipeline.py` |
| YOLO multi-backend (ONNX/NCNN/TensorRT) | `src/vision/operators/yolo_inference_operator.py` | `vision.py` |
| Detección HSV de pelota (fallback) | `src/vision/operators/hsv_ball_detector_operator.py` | `vision.py` |
| Fusión de pelota (YOLO + HSV) | `src/vision/operators/ball_fusion_operator.py` | `vision.py` |
| Detección de color de portería | `src/vision/operators/goal_color_operator.py` | `vision.py` |
| Detección de línea blanca | `src/vision/operators/white_line_operator.py` | `vision.py` |
| Captura de frames + resolución de backend | `src/vision/operators/frame_capture_operator.py` | `camera.py` |
| Exportación JSON para diagnóstico | `src/vision/operators/json_export_operator.py` | `vision.py` |
| Protocolo binario UART + CRC8 | `src/motors/operators/burst_operator.py` | `motors.py` |
| Mapeo de tracción diferencial | `src/motors/operators/differential_operator.py` | `motors.py` |
| Constantes de navegación | `src/pipeline/utils/pipeline_constants.py` | `config.py` |
| Constantes de motores + tabla CRC8 | `src/motors/utils/motor_constants.py` | `config.py` / `motors.py` |
| Stubs de hardware | `futbot-ws/stubs/` | `stubs/` |
| Scripts de diagnóstico/calibración (11) | `scripts/` | `scripts/` |
| Suite de pruebas (15 tests) | `tests/` | `tests/` |
| Modelos ML | `models/` | `models/` |
| Documentos de diseño | `docs/plans/` | `docs/` |

---

## 7. Lo Que Se Elimina

| Componente | Razón |
|-----------|--------|
| P2P WebSocket (`communication/`, `ws_runner.py`, `role_state.py`, `ap_manager.py`) | Robot único, sin necesidad de comunicación multi-robot |
| Estrategia de roles (`strategy/`, `roles_dto.py`) | Sin roles de atacante/defensor |
| Validación de mensajes (`pipes/validation_pipe.py`) | Sin WebSocket no hay mensajes que validar |
| Config WiFi AP (`config/`, hostapd, dnsmasq, netplan) | Sin red multi-robot |
| Makefile de deploy | Simplificado a un script único |
| `husky.ino` (firmware Arduino) | Prototipo legacy, no usado en el sistema RPi5 |
| `huskytest.py` | Test legacy de HuskyLens |
| `main.py` raíz (559 líneas, FSM monolítico) | Reemplazado por el nuevo `main.py` modular |
| `cam.py` (683 líneas, SerialBus + I2C + shims de visión) | Separado en `camera.py` y `motors.py` |
| `test-robot/` (sub-proyecto legacy, 33 entradas) | Banco de pruebas de hardware obsoleto |
| Servicio ultrasónico (`src/ultrasonic/`) | Sensor fuera de uso |
| `capture_frame.py`, `debug_vision.py` (scripts raíz) | Movidos a `scripts/` |
| Código duplicado entre directorios v2-v8 | Unificado en una sola base de código |
| `config.env` (plantilla de entorno de ws) | Reemplazado por `config.py` |
| `conftest.py` (fixture de stubs de hardware de ws) | Reimplementado en el nuevo `tests/` |

---

## 8. Dependencias (`pyproject.toml`)

```toml
[project]
name = "futbot"
version = "9.0.0"
description = "Robot autónomo de fútbol sobre Raspberry Pi 5"
requires-python = ">=3.11"
dependencies = [
    "opencv-python>=4.13",
    "numpy>=2.0",
    "pyserial>=3.5",
]

[project.optional-dependencies]
onnx = ["onnxruntime"]
ncnn = ["ncnn"]
tensorrt = ["tensorrt"]
model-tools = ["ultralytics"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Eliminado respecto a v8: `opencv-python-headless`, `smbus2` (sin I2C al quitar ultrasónico), `websockets`.

---

## 9. Plan de Migración

Todo el trabajo ocurre en la rama `develop` (creada manualmente por el usuario). `main` permanece intacta.

| Paso | Resultado | Material de origen |
|------|-----------|-------------------|
| 1 | `config.py` | `pipeline_constants.py` + `motor_constants.py` de v8 |
| 2 | `camera.py` | `frame_capture_operator.py` + backend resolver de `cam.py` de v8 |
| 3 | `vision.py` | Colapsar 9 operadores de `src/vision/operators/` |
| 4 | `motors.py` | Colapsar `motor_service.py` + 3 operadores + constantes de v8 |
| 5 | `pipeline.py` | Colapsar `pipeline_service.py` + 3 operadores de v8 |
| 6 | `main.py` | Nuevo orquestador (implementación desde cero) |
| 7 | `stubs/` | Adaptar desde `futbot-ws/stubs/` |
| 8 | `tests/` | Migrar y adaptar la suite de pruebas existente |
| 9 | `scripts/` | Migrar desde `scripts/` de v8 |
| 10 | `pyproject.toml` + `README.md` | Actualizar |
| 11 | `models/` | Copiar desde `models/` de v8 |

---

## 10. Estrategia de Pruebas

- **Pruebas unitarias**: Cada módulo (`vision.py`, `pipeline.py`, `motors.py`) probado en aislamiento con stubs de dependencias
- **Pruebas de integración**: Bucle completo de `main.py` con todos los stubs activos, verificando transiciones correctas de la FSM para secuencias de frames conocidas
- **Pruebas en hardware real**: Ejecutar en RPi5 con `FUTBOT_MODE=real` — validación manual antes de fusionar a `main`
- **Modo stub**: `FUTBOT_MODE=stub` permite ciclo completo de desarrollo y pruebas en cualquier laptop

---

## 11. Criterios de Éxito

1. Un solo directorio `futbot/` reemplaza los 9 directorios de versiones
2. Ejecutar `python main.py` con `FUTBOT_MODE=stub` completa un bucle FSM completo
3. Los 15 tests existentes pasan con la estructura adaptada
4. YOLO multi-backend funciona (mínimo ONNX, con NCNN/TensorRT opcionales)
5. Todos los scripts de diagnóstico/calibración funcionales
6. El código se entiende leyendo 8 archivos en secuencia
