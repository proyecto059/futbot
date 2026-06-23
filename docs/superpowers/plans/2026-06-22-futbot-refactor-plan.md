# Futbot Refactor — Plan de Implementación

> **Para agentes implementadores:** REQUIRED SUB-SKILL: Usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan checkbox (`- [ ]`) para seguimiento.

**Objetivo:** Unificar las 9 versiones de futbot (v2-v8 + ws) en una sola base de código plana de 8 módulos `.py` para un robot autónomo sobre Raspberry Pi 5.

**Arquitectura:** Estructura plana — un archivo `.py` por responsabilidad. Inyección manual de dependencias en `main.py`. Dataclasses para tipos compartidos. Sin anidación de operadores ni capas DTO/pipe/strategy.

**Stack técnico:** Python 3.11+, uv, opencv-python, numpy, pyserial, onnxruntime (opcional), ncnn (opcional), tensorrt (opcional)

## Restricciones Globales

- Python >=3.11, <3.15
- opencv-python>=4.13 (no headless)
- numpy>=2,<3
- pyserial>=3.5
- Sin dependencias de futbot-ws: websockets, smbus2
- Variable `FUTBOT_MODE`: `real` (hardware RPi5) o `stub` (desarrollo local)
- Rama `develop` — no tocar `main`
- Código en español donde sea práctico
- TDD: primero test, luego implementación

---

## Estructura de Archivos

| Archivo | Responsabilidad | Origen |
|---------|----------------|--------|
| `futbot/config.py` | Constantes globales (cámara, visión, pipeline, motores, CRC8) | `pipeline_constants.py` + `motor_constants.py` + `vision_constants.py` |
| `futbot/camera.py` | Captura de frames con resolución de backend | `frame_capture_operator.py` + `camera_backend_resolver.py` |
| `futbot/vision.py` | YOLO multi-backend + HSV + fusión de detecciones | `hybrid_vision_service.py` + 9 operadores |
| `futbot/pipeline.py` | FSM BUSCAR → PERSEGUIR → RECUPERAR | `pipeline_service.py` + `chase_operator.py` + `search_operator.py` |
| `futbot/motors.py` | UART serial + protocolo binario + CRC8 + servos | `motor_service.py` + 3 operadores + `motor_constants.py` |
| `futbot/main.py` | Orquestador: inicializa servicios, corre bucle | Nueva implementación |
| `futbot/stubs/__init__.py` | Instalador de mocks de hardware | `futbot-ws/stubs/hardware_stubs.py` |
| `futbot/stubs/camera_stub.py` | Cámara fake que reproduce frames pregrabados | Nuevo |
| `futbot/stubs/motors_stub.py` | Motores fake que loguean comandos | Nuevo |
| `futbot/tests/test_config.py` | Test de carga de configuración | Adaptado |
| `futbot/tests/test_camera.py` | Test de cámara con stub | Adaptado |
| `futbot/tests/test_vision.py` | Test de detección | Adaptado |
| `futbot/tests/test_motors.py` | Test de protocolo de motores | Adaptado |
| `futbot/tests/test_pipeline.py` | Test de FSM | Adaptado |
| `futbot/tests/test_integration.py` | Test de integración con stubs | Nuevo |
| `futbot/pyproject.toml` | Dependencias del proyecto | Nuevo |
| `futbot/README.md` | Documentación | Nuevo |

---

### Tarea 1: Crear `config.py`

**Archivos:**
- Crear: `futbot/config.py`
- Test: `futbot/tests/test_config.py`

**Interfaces:**
- Produce: `Config` dataclass, `CRC8_TABLE` list, `crc8()` function

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_config.py
import sys
sys.path.insert(0, ".")  # permitir import desde raíz

def test_config_defaults():
    from config import Config
    cfg = Config()
    assert cfg.camera_width == 320
    assert cfg.camera_height == 240
    assert cfg.camera_backend == "libcamera"
    assert cfg.yolo_conf_threshold == 0.40
    assert cfg.search_speed == 255
    assert cfg.chase_speed_base == 80
    assert cfg.uart_port == "/dev/ttyAMA0"
    assert cfg.uart_baud == 1000000
    assert cfg.servo_pan_id == 2
    assert cfg.servo_tilt_id == 1
    assert cfg.pan_center == 70
    assert cfg.tilt_center == 45

def test_crc8():
    from config import crc8
    assert crc8(b"\x04\x0b\x01") == crc8(b"\x04\x0b\x01")
    assert isinstance(crc8(b"test"), int)
    assert 0 <= crc8(b"test") <= 255
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; pytest tests/test_config.py -v
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Paso 3: Escribir `config.py`**

```python
"""Configuración global del robot — fuente única de verdad.

Todas las constantes que usa el proyecto están aquí. Sin imports de otros
módulos del proyecto. Sin dependencias de hardware.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

# ── CRC8 ────────────────────────────────────────────────────────────────────────
# Tabla de lookup para CRC8 (polinomio 0x07). Pre-calculada para checksums
# de paquetes UART sin costo en runtime.
CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]


def crc8(data: bytes) -> int:
    """Calcula el CRC8 de *data* usando la tabla de lookup pre-calculada."""
    c = 0
    for b in data:
        c = CRC8_TABLE[c ^ b]
    return c


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Todas las constantes configurables del robot."""

    # Cámara
    camera_width: int = 320
    camera_height: int = 240
    camera_fps: int = 30
    camera_backend: str = "libcamera"  # libcamera | gstreamer | opencv
    camera_exposure_default: int = 200
    camera_flip_horizontal: bool = False

    # Visión — HSV pelota naranja
    ball_hsv_lower: Tuple[int, int, int] = (0, 80, 80)
    ball_hsv_upper: Tuple[int, int, int] = (65, 255, 255)
    ball_hsv_lower2: Tuple[int, int, int] = (168, 80, 80)
    ball_hsv_upper2: Tuple[int, int, int] = (179, 255, 255)
    ball_min_area: int = 30
    ball_min_radius: int = 4
    ball_close_radius: int = 60
    adaptive_min_circularity: float = 0.20
    adaptive_max_radius: int = 150
    hot_pixel_y_max: int = 60
    border_margin: int = 25
    adaptive_hue_ema_alpha: float = 0.15
    adaptive_reacquire_min_miss: int = 2
    adaptive_miss_reset_frames: int = 30

    # Visión — HSV goles
    goal_yellow_hsv_lower: Tuple[int, int, int] = (18, 130, 130)
    goal_yellow_hsv_upper: Tuple[int, int, int] = (50, 255, 255)
    goal_blue_hsv_lower: Tuple[int, int, int] = (95, 180, 60)
    goal_blue_hsv_upper: Tuple[int, int, int] = (140, 255, 255)
    goal_min_pixels: int = 120
    goal_min_component_area: int = 500

    # Visión — Línea blanca
    line_white_hsv_lower: Tuple[int, int, int] = (0, 0, 190)
    line_white_hsv_upper: Tuple[int, int, int] = (180, 60, 255)
    line_detect_min_pixels: int = 3000
    line_detect_min_ratio: float = 0.035

    # Visión — YOLO
    yolo_imgsz: int = 320
    yolo_conf_threshold: float = 0.40
    yolo_ball_class_id: int = 0
    yolo_robot_class_id: int = 4
    yolo_model_path: str = "models/yoloe26n_v2/onnx/yoloe26n_v2.onnx"
    yolo_ncnn_model_dir: str = "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
    yolo_backend: str = "onnx"  # onnx | ncnn | tensorrt
    yolo_thread_sleep_sec: float = 0.001

    # Pipeline — Persecución (CHASE)
    chase_speed_base: float = 80.0
    chase_rot_gain: float = 0.8
    chase_deadband_px: float = 16.0
    kick_radius_px: float = 50.0
    chase_miss_secs: float = 0.8
    chase_blind_speed: float = 60.0
    chase_blind_ms: int = 100
    chase_blind_scan_secs: float = 0.2

    # Pipeline — Búsqueda (SEARCH)
    search_turn_speed: float = 255.0
    search_turn_ms: int = 250
    search_scan_secs: float = 0.3
    max_search_duration_ms: int = 5000

    # Pipeline — Recuperación (RECOVERY)
    recovery_reverse_speed: float = 110.0
    recovery_reverse_ms: int = 220
    recovery_turn_speed: float = 115.0
    recovery_turn_ms: int = 180
    recovery_max_steps: int = 5

    # Motores — UART
    uart_port: str = "/dev/ttyAMA0"
    uart_baud: int = 1000000
    diff_cap: float = 250.0

    # Motores — Servos
    servo_pan_id: int = 2
    servo_tilt_id: int = 1
    servo_min_angle: float = 0.0
    servo_max_angle: float = 180.0
    pan_center: float = 70.0
    tilt_center: float = 45.0

    # Rutas
    models_dir: str = "models"

    def resolve_yolo_model_path(self) -> Path:
        return Path(self.yolo_model_path)

    def resolve_ncnn_model_dir(self) -> Path:
        return Path(self.yolo_ncnn_model_dir)
```

- [ ] **Paso 4: Ejecutar tests para verificar que pasan**

```bash
cd futbot; pytest tests/test_config.py -v
```
Esperado: 2 passed

- [ ] **Paso 5: Commit**

```bash
git add futbot/config.py futbot/tests/test_config.py
git commit -m "feat: crear config.py con constantes unificadas de v8"
```

---

### Tarea 2: Crear `camera.py`

**Archivos:**
- Crear: `futbot/camera.py`
- Test: `futbot/tests/test_camera.py`

**Interfaces:**
- Produce: `Camera` class con `grab() -> np.ndarray | None`, `release()`
- Consume: `Config` de `config.py`

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_camera.py
import sys
sys.path.insert(0, ".")

def test_camera_creates_instance():
    """Verifica que Camera se puede instanciar sin hardware (fallback V4L2)."""
    from config import Config
    from camera import Camera
    cfg = Config()
    # En entorno sin cámara, debe lanzar CameraNotFoundError o similar
    try:
        cam = Camera(cfg)
        assert cam is not None
        cam.release()
    except RuntimeError as e:
        assert "cámara" in str(e).lower() or "camera" in str(e).lower()
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; pytest tests/test_camera.py -v
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'camera'`

- [ ] **Paso 3: Escribir `camera.py`**

```python
"""Captura de frames — resuelve backend de cámara automáticamente.

Backends probados en orden:
  1. picamera2 (nativo en RPi5, CSI IMX219)
  2. libcamera via subprocess (system Python con bindings C)
  3. GStreamer libcamerasrc
  4. V4L2 (/dev/video*)

El módulo expone una clase Camera con interfaz simple:
  cam = Camera(config)
  frame = cam.grab()  # np.ndarray BGR o None
  cam.release()
"""

from __future__ import annotations

import logging
import os
import re
import struct
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from config import Config

log = logging.getLogger("futbot.camera")


class Camera:
    """Fachada unificada de captura de cámara."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._cap, self._width, self._height = self._resolve_backend()
        if self._cap is None:
            raise RuntimeError(
                "No se detectó ningún backend de cámara "
                "(picamera2/GStreamer/V4L2). Revisar: (1) cable CSI + "
                "'cam -l' para IMX219; (2) cámara USB conectada."
            )
        self._warmup()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Captura el último frame. Retorna None si falla."""
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        if self._cfg.camera_flip_horizontal:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        try:
            self._cap.release()
        except Exception:
            pass

    def _warmup(self) -> None:
        """Descarta los primeros frames hasta obtener uno válido."""
        for _ in range(10):
            ok, _ = self._cap.read()
            if ok:
                break
            time.sleep(0.05)

    # ── Resolución de backend ─────────────────────────────────────────────

    def _resolve_backend(self) -> Tuple[object | None, int, int]:
        w, h = self._cfg.camera_width, self._cfg.camera_height

        # 1. picamera2
        cap = self._try_picamera2(w, h)
        if cap:
            return cap, w, h

        # 2. libcamera subprocess
        cap = self._try_libcamera_subprocess(w, h)
        if cap:
            return cap, w, h

        # 3. GStreamer
        cap = self._try_gstreamer(w, h)
        if cap:
            rw, rh = self._get_frame_dims(cap, w, h)
            return cap, rw, rh

        # 4. V4L2
        cap, idx = self._try_v4l2_any(w, h)
        if cap:
            rw, rh = self._get_frame_dims(cap, w, h)
            return cap, rw, rh

        return None, 0, 0

    def _try_picamera2(self, w: int, h: int):
        try:
            from picamera2 import Picamera2
        except ImportError:
            return None
        try:
            picam = Picamera2()
            config = picam.create_video_configuration(
                main={"size": (w, h), "format": "RGB888"},
                buffer_count=2,
            )
            picam.configure(config)
            picam.start()
            time.sleep(0.3)
            frame = picam.capture_array("main")
            if frame is not None:
                log.info("picamera2: %dx%d OK", w, h)
                return _Picamera2Adapter(picam)
            picam.stop()
            picam.close()
        except Exception as e:
            log.info("picamera2 no disponible: %s", e)
        return None

    def _try_libcamera_subprocess(self, w: int, h: int):
        """libcamera vía subprocess con el intérprete del sistema."""
        worker = Path(__file__).parent / "scripts" / "_libcamera_worker.py"
        system_python = "/usr/bin/python3"
        if not worker.is_file() or not os.path.isfile(system_python):
            return None
        try:
            proc = subprocess.Popen(
                [system_python, str(worker), str(w), str(h)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Esperar READY
            deadline = time.time() + 15
            while time.time() < deadline:
                line = proc.stderr.readline()
                if not line:
                    if proc.poll() is not None:
                        return None
                    time.sleep(0.1)
                    continue
                if line.strip().startswith(b"READY"):
                    break
            else:
                proc.kill()
                return None
            log.info("libcamera subprocess: %dx%d OK", w, h)
            return _LibcameraSubprocessAdapter(proc, w, h)
        except Exception as e:
            log.info("libcamera subprocess: %s", e)
        return None

    def _try_gstreamer(self, w: int, h: int):
        pipeline = (
            f"libcamerasrc ! video/x-raw,width={w},height={h},format=BGRx "
            "! videoconvert ! video/x-raw,format=BGR "
            "! appsink drop=1 max-buffers=2 sync=false"
        )
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            return None
        for _ in range(8):
            cap.grab()
        ok, _ = cap.read()
        if ok:
            log.info("GStreamer libcamerasrc: %dx%d OK", w, h)
            return cap
        cap.release()
        return None

    def _try_v4l2_any(self, w: int, h: int):
        import glob
        indices = []
        for path in sorted(glob.glob("/dev/video*")):
            m = re.match(r"/dev/video(\d+)", path)
            if m:
                indices.append(int(m.group(1)))
        for idx in indices:
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if not cap.isOpened():
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(3):
                cap.grab()
            ok, _ = cap.read()
            if ok:
                log.info("V4L2 /dev/video%d: %dx%d OK", idx, w, h)
                return cap, idx
            cap.release()
        return None, None

    def _get_frame_dims(self, cap, default_w: int, default_h: int) -> Tuple[int, int]:
        ok, frame = cap.read()
        if ok and frame is not None:
            return frame.shape[1], frame.shape[0]
        return default_w, default_h


# ── Adaptadores de backend ────────────────────────────────────────────────────

class _Picamera2Adapter:
    """Adapta Picamera2 a interfaz tipo cv2.VideoCapture."""

    def __init__(self, picam):
        self._picam = picam
        self._running = True

    def read(self):
        if not self._running:
            return False, None
        try:
            frame = self._picam.capture_array("main")
        except Exception:
            return False, None
        if frame is None:
            return False, None
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def isOpened(self):
        return self._running

    def release(self):
        if not self._running:
            return
        self._running = False
        try:
            self._picam.stop()
            self._picam.close()
        except Exception:
            pass


class _LibcameraSubprocessAdapter:
    """Adapta worker libcamera (subprocess + pipes) a interfaz cv2.VideoCapture."""

    _HEADER_FMT = "<4sIIII"
    _HEADER_SIZE = struct.calcsize(_HEADER_FMT)
    _MAGIC = b"\xf8\xb4\xc2\x0d"

    def __init__(self, proc, w: int, h: int):
        self._proc = proc
        self._width = w
        self._height = h
        self._running = True

    def read(self):
        if not self._running:
            return False, None
        header = self._read_exact(self._HEADER_SIZE)
        if header is None:
            self._running = False
            return False, None
        magic, w, h, stride, size = struct.unpack(self._HEADER_FMT, header)
        if magic != self._MAGIC:
            self._running = False
            return False, None
        data = self._read_exact(size)
        if data is None:
            self._running = False
            return False, None
        arr = np.frombuffer(data, dtype=np.uint8).reshape((h, stride // 4, 4))
        frame = arr[:h, :w, :3].copy()
        self._width, self._height = w, h
        return True, frame

    def _read_exact(self, n: int):
        data = b""
        while len(data) < n:
            chunk = self._proc.stdout.read(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def release(self):
        self._running = False
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.write(b"QUIT\n")
                    self._proc.stdin.flush()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2)
            self._proc = None
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; pytest tests/test_camera.py -v
```
Esperado: 1 passed (test verifica que instancia o lanza error esperado sin cámara)

- [ ] **Paso 5: Commit**

```bash
git add futbot/camera.py futbot/tests/test_camera.py
git commit -m "feat: crear camera.py con resolucion de backend unificada"
```

---

### Tarea 3: Crear `vision.py`

**Archivos:**
- Crear: `futbot/vision.py`
- Test: `futbot/tests/test_vision.py`

**Interfaces:**
- Produce: `Vision` class con `detect(frame: np.ndarray) -> Detections`
- Produce: `Detections`, `Ball`, `Goal`, `WhiteLine` dataclasses
- Consume: `Config` de `config.py`

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_vision.py
import sys
sys.path.insert(0, ".")
import numpy as np

def test_detections_dataclass():
    """Verifica que los dataclasses de detección se crean correctamente."""
    from vision import Ball, Goal, WhiteLine, Detections

    ball = Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)
    assert ball.x == 0.5

    goal = Goal(color="blue", x=0.3, y=0.8)
    assert goal.color == "blue"

    line = WhiteLine(detected=True, position="center")
    assert line.detected

    dets = Detections(ball=ball, goal=goal, white_line=line)
    assert dets.ball is not None
    assert dets.goal is not None
    assert dets.white_line is not None

def test_detections_empty():
    from vision import Detections
    dets = Detections()
    assert dets.ball is None
    assert dets.goal is None
    assert dets.white_line is None

def test_vision_hsv_ball_detection():
    """Verifica que la detección HSV encuentra una bola naranja sintética."""
    from vision import Vision
    from config import Config
    cfg = Config()
    vis = Vision(cfg)
    # Frame negro con círculo naranja en el centro
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2 = __import__("cv2")
    orange_bgr = (0, 140, 255)  # BGR = naranja
    cv2.circle(frame, (160, 120), 30, orange_bgr, -1)
    dets = vis.detect(frame)
    assert dets.ball is not None
    assert 0.3 < dets.ball.x < 0.7
    assert 0.3 < dets.ball.y < 0.7

def test_vision_no_ball():
    """Frame vacío no debe detectar nada."""
    from vision import Vision
    from config import Config
    cfg = Config()
    vis = Vision(cfg)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    dets = vis.detect(frame)
    assert dets.ball is None
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; pytest tests/test_vision.py -v
```
Esperado: FAIL

- [ ] **Paso 3: Escribir `vision.py`**

```python
"""Pipeline de visión — detección híbrida YOLO + HSV.

Clase Vision con método detect(frame) -> Detections.
Soporte multi-backend YOLO: ONNX, NCNN, TensorRT.
Fallback HSV para pelota naranja.
Detección de porterías por color y línea blanca del campo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from config import Config

log = logging.getLogger("futbot.vision")


# ── Dataclasses de detección ──────────────────────────────────────────────────

@dataclass
class Ball:
    """Detección de pelota con coordenadas normalizadas (0.0 a 1.0)."""
    x: float          # centro x normalizado
    y: float          # centro y normalizado
    radius: float     # radio normalizado
    confidence: float


@dataclass
class Goal:
    """Detección de portería."""
    color: str        # "blue" | "yellow"
    x: float
    y: float


@dataclass
class WhiteLine:
    """Detección de línea blanca del campo."""
    detected: bool
    position: str     # "left" | "right" | "center"


@dataclass
class Detections:
    """Resultado unificado de detección."""
    ball: Ball | None = None
    goal: Goal | None = None
    white_line: WhiteLine | None = None
    ts: float = 0.0


# ── Clase Vision ──────────────────────────────────────────────────────────────

class Vision:
    """Pipeline híbrido de detección: YOLO + HSV + fusión."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._yolo = None
        self._last_yolo_output = None
        self._ball_cache: Optional[Ball] = None
        self._ball_cache_ts: float = 0.0
        self._cache_ttl: float = 0.5  # segundos

        # Intentar cargar backend YOLO
        self._init_yolo()

    def _init_yolo(self) -> None:
        """Inicializa el backend YOLO según configuración."""
        backend = self._cfg.yolo_backend
        try:
            if backend == "onnx":
                self._yolo = _YoloOnnxBackend(self._cfg)
            elif backend == "ncnn":
                self._yolo = _YoloNcnnBackend(self._cfg)
            elif backend == "tensorrt":
                self._yolo = _YoloTensorrtBackend(self._cfg)
            log.info("YOLO backend %s inicializado", backend)
        except Exception as e:
            log.warning("YOLO backend %s no disponible: %s. Solo HSV activo.", backend, e)
            self._yolo = None

    def detect(self, frame: np.ndarray) -> Detections:
        """Ejecuta el pipeline completo de detección sobre un frame.

        Orden:
          1. YOLO (si está disponible) en este hilo
          2. HSV pelota (siempre, como fallback/refuerzo)
          3. HSV porterías
          4. HSV línea blanca
          5. Fusión de detecciones
        """
        now = time.time()
        h, w = frame.shape[:2]

        # 1. YOLO
        yolo_ball = None
        if self._yolo is not None:
            yolo_raw = self._yolo.infer(frame)
            yolo_ball = self._parse_yolo_ball(yolo_raw, w, h)

        # 2. HSV pelota
        hsv_ball = self._detect_hsv_ball(frame, w, h)

        # 3. HSV porterías
        goal = self._detect_goal(frame, w, h)

        # 4. HSV línea blanca
        line = self._detect_white_line(frame, w, h)

        # 5. Fusión (YOLO > HSV > caché)
        ball = self._fuse_ball(yolo_ball, hsv_ball, now)

        return Detections(ball=ball, goal=goal, white_line=line, ts=now)

    # ── YOLO ──────────────────────────────────────────────────────────────

    def _parse_yolo_ball(self, raw, w: int, h: int) -> Optional[Ball]:
        if raw is None or len(raw) == 0:
            return None
        for det in raw:
            cls_id = int(det[5]) if len(det) >= 6 else -1
            if cls_id == self._cfg.yolo_ball_class_id:
                x1, y1, x2, y2 = det[:4]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                rx = (x2 - x1) / 2  # radio en píxeles
                conf = float(det[4]) if len(det) >= 5 else 1.0
                if conf >= self._cfg.yolo_conf_threshold:
                    return Ball(
                        x=cx / w,
                        y=cy / h,
                        radius=rx / max(w, h),
                        confidence=conf,
                    )
        return None

    # ── HSV pelota naranja ────────────────────────────────────────────────

    def _detect_hsv_ball(self, frame: np.ndarray, w: int, h: int) -> Optional[Ball]:
        lo = np.array(self._cfg.ball_hsv_lower, dtype=np.uint8)
        hi = np.array(self._cfg.ball_hsv_upper, dtype=np.uint8)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lo, hi)
        # Segundo rango para rojos (hue wrap-around)
        lo2 = np.array(self._cfg.ball_hsv_lower2, dtype=np.uint8)
        hi2 = np.array(self._cfg.ball_hsv_upper2, dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lo2, hi2)
        mask = cv2.bitwise_or(mask, mask2)
        # Ignorar franja superior ruidosa
        mask[:self._cfg.hot_pixel_y_max, :] = 0
        # Ignorar bordes
        bm = self._cfg.border_margin
        mask[:bm, :] = 0
        mask[-bm:, :] = 0
        mask[:, :bm] = 0
        mask[:, -bm:] = 0
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._cfg.ball_min_area:
                continue
            (cx, cy), radius = cv2.minEnclosingCircle(cnt)
            if radius < self._cfg.ball_min_radius:
                continue
            # Filtro de circularidad
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < self._cfg.adaptive_min_circularity:
                    continue
            return Ball(
                x=cx / w,
                y=cy / h,
                radius=radius / max(w, h),
                confidence=0.7,  # HSV tiene confianza fija
            )
        return None

    # ── HSV porterías ─────────────────────────────────────────────────────

    def _detect_goal(self, frame: np.ndarray, w: int, h: int) -> Optional[Goal]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Buscar azul
        lo_b = np.array(self._cfg.goal_blue_hsv_lower, dtype=np.uint8)
        hi_b = np.array(self._cfg.goal_blue_hsv_upper, dtype=np.uint8)
        mask_b = cv2.inRange(hsv, lo_b, hi_b)
        blue_pixels = cv2.countNonZero(mask_b)
        if blue_pixels >= self._cfg.goal_min_pixels:
            moments = cv2.moments(mask_b)
            if moments["m00"] > 0:
                return Goal(color="blue", x=moments["m10"] / moments["m00"] / w,
                            y=moments["m01"] / moments["m00"] / h)
        # Buscar amarillo
        lo_y = np.array(self._cfg.goal_yellow_hsv_lower, dtype=np.uint8)
        hi_y = np.array(self._cfg.goal_yellow_hsv_upper, dtype=np.uint8)
        mask_y = cv2.inRange(hsv, lo_y, hi_y)
        yellow_pixels = cv2.countNonZero(mask_y)
        if yellow_pixels >= self._cfg.goal_min_pixels:
            moments = cv2.moments(mask_y)
            if moments["m00"] > 0:
                return Goal(color="yellow", x=moments["m10"] / moments["m00"] / w,
                            y=moments["m01"] / moments["m00"] / h)
        return None

    # ── HSV línea blanca ──────────────────────────────────────────────────

    def _detect_white_line(self, frame: np.ndarray, w: int, h: int) -> WhiteLine:
        # Solo inspeccionar el tercio inferior del frame
        roi = frame[int(h * 0.66):, :]
        roi_h, roi_w = roi.shape[:2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(self._cfg.line_white_hsv_lower, dtype=np.uint8)
        hi = np.array(self._cfg.line_white_hsv_upper, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        white_pixels = cv2.countNonZero(mask)
        total = roi_w * roi_h
        ratio = white_pixels / total if total > 0 else 0
        if white_pixels < self._cfg.line_detect_min_pixels or ratio < self._cfg.line_detect_min_ratio:
            return WhiteLine(detected=False, position="center")
        # Determinar posición: izquierda, centro o derecha
        left_half = mask[:, :roi_w // 2]
        right_half = mask[:, roi_w // 2:]
        left_count = cv2.countNonZero(left_half)
        right_count = cv2.countNonZero(right_half)
        if left_count > right_count * 1.5:
            position = "left"
        elif right_count > left_count * 1.5:
            position = "right"
        else:
            position = "center"
        return WhiteLine(detected=True, position=position)

    # ── Fusión de pelota ──────────────────────────────────────────────────

    def _fuse_ball(
        self, yolo_ball: Optional[Ball], hsv_ball: Optional[Ball], now: float
    ) -> Optional[Ball]:
        # YOLO tiene prioridad si está disponible con confianza suficiente
        if yolo_ball is not None and yolo_ball.confidence >= self._cfg.yolo_conf_threshold:
            self._ball_cache = yolo_ball
            self._ball_cache_ts = now
            return yolo_ball
        # HSV como fallback
        if hsv_ball is not None:
            self._ball_cache = hsv_ball
            self._ball_cache_ts = now
            return hsv_ball
        # Usar caché si no expiró
        if self._ball_cache is not None and (now - self._ball_cache_ts) < self._cache_ttl:
            return self._ball_cache
        return None


# ── Backends YOLO ─────────────────────────────────────────────────────────────

class _YoloOnnxBackend:
    """Backend YOLO vía ONNX Runtime."""

    def __init__(self, config: Config) -> None:
        import onnxruntime as ort
        model_path = str(config.resolve_yolo_model_path())
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray):
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        img = img.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        outputs = self._session.run(None, {"images": img})
        return self._process_output(outputs[0])

    def _process_output(self, output):
        # output shape: (1, N, 6) o similar
        if output is None:
            return None
        result = output[0] if len(output.shape) == 3 else output
        return result[result[:, 4] > 0.1] if len(result) > 0 else []


class _YoloNcnnBackend:
    """Backend YOLO vía NCNN (optimizado para ARM en RPi)."""

    def __init__(self, config: Config) -> None:
        import ncnn
        model_dir = str(config.resolve_ncnn_model_dir())
        self._net = ncnn.Net()
        self._net.load_param(f"{model_dir}/model.ncnn.param")
        self._net.load_model(f"{model_dir}/model.ncnn.bin")
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray):
        import ncnn
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        mat = ncnn.Mat.from_pixels(img, ncnn.Mat.PixelType.PIXEL_BGR, self._imgsz, self._imgsz)
        mat.substract_mean_normalize([0, 0, 0], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return self._process_output(out)

    def _process_output(self, out):
        if out is None:
            return None
        data = np.array(out)
        return data[data[:, 4] > 0.1] if len(data) > 0 else []


class _YoloTensorrtBackend:
    """Backend YOLO vía TensorRT."""

    def __init__(self, config: Config) -> None:
        raise NotImplementedError("TensorRT backend no implementado en esta versión")

    def infer(self, frame: np.ndarray):
        return None
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; pytest tests/test_vision.py -v
```
Esperado: 3-4 passed (los tests de HSV deberían pasar; YOLO se omite sin modelo)

- [ ] **Paso 5: Commit**

```bash
git add futbot/vision.py futbot/tests/test_vision.py
git commit -m "feat: crear vision.py con deteccion hibrida YOLO+HSV"
```

---

### Tarea 4: Crear `motors.py`

**Archivos:**
- Crear: `futbot/motors.py`
- Test: `futbot/tests/test_motors.py`

**Interfaces:**
- Produce: `Motors` class con `send(cmd: MotorCommand)`, `stop()`, `close()`
- Produce: `MotorCommand` dataclass
- Consume: `Config` de `config.py`, `crc8` de `config.py`

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_motors.py
import sys
sys.path.insert(0, ".")

def test_motor_command_dataclass():
    from motors import MotorCommand
    cmd = MotorCommand(left_speed=80.0, right_speed=-80.0, dur_ms=140)
    assert cmd.left_speed == 80.0
    assert cmd.right_speed == -80.0
    assert cmd.dur_ms == 140
    assert cmd.pan_angle is None
    assert cmd.tilt_angle is None

def test_differential_mapping():
    """Verifica el mapeo de velocidades de rueda a 4 motores."""
    # Simulamos el DifferentialOperator
    def apply(v_left, v_right, cap=250.0):
        mx = max(abs(v_left), abs(v_right))
        if mx > cap:
            s = cap / mx
            v_left *= s
            v_right *= s
        return (0.0, 0.0, -v_right, -v_left)

    # Avance recto: v_left positivo, v_right negativo
    m1, m2, m3, m4 = apply(80.0, -80.0)
    assert m1 == 0.0
    assert m2 == 0.0
    assert m3 == 80.0  # -v_right = -(-80) = 80
    assert m4 == -80.0  # -v_left = -80

    # Giro derecha
    m1, m2, m3, m4 = apply(80.0, -80.0)
    assert m3 > 0

    # Stop
    m1, m2, m3, m4 = apply(0.0, 0.0)
    assert (m1, m2, m3, m4) == (0.0, 0.0, 0.0, 0.0)

def test_pwm_conversion():
    """Verifica la conversión ángulo -> PWM."""
    def angle_to_pwm(angle):
        return int(500 + (max(0, min(180, angle)) / 180.0) * 2000)
    assert angle_to_pwm(0) == 500
    assert angle_to_pwm(90) == 1500
    assert angle_to_pwm(180) == 2500

def test_crc8_uart_frame():
    """Verifica CRC8 en una trama de ejemplo."""
    from config import crc8
    # Frame servo: header 0xAA 0x55, cmd 0x04, len 11, payload...
    sd = bytes([0x01, 0x8C, 0x00, 2, 2, 0xDC, 0x05, 1, 0x84, 0x03])
    frame = bytes([0xAA, 0x55, 0x04, len(sd)]) + sd
    checksum = crc8(frame[2:])
    assert 0 <= checksum <= 255
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; pytest tests/test_motors.py -v
```
Esperado: FAIL

- [ ] **Paso 3: Escribir `motors.py`**

```python
"""Control de motores vía UART serial — protocolo binario propietario.

Clase Motors: envía comandos de velocidad y ángulos de servo al driver de
motores conectado por UART (/dev/ttyAMA0).

Protocolo: dos tramas binarias (servo + motor) con CRC8, escritas
atómicamente bajo threading.Lock.

MotorCommand: dataclass con velocidades diferenciales y ángulos de servo.
"""

from __future__ import annotations

import logging
import struct
import threading
from dataclasses import dataclass

import serial

from config import CRC8_TABLE, Config, crc8

log = logging.getLogger("futbot.motors")


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class MotorCommand:
    """Comando de movimiento para el driver de motores.

    left_speed, right_speed: -1.0 a 1.0 (velocidad diferencial normalizada)
      o valores absolutos 0-255 según el modo.
    dur_ms: duración del comando en milisegundos.
    pan_angle, tilt_angle: ángulos de servo en grados (0-180), None = mantener.
    """
    left_speed: float = 0.0
    right_speed: float = 0.0
    dur_ms: int = 140
    pan_angle: float | None = None
    tilt_angle: float | None = None


# ── Clase Motors ──────────────────────────────────────────────────────────────

class Motors:
    """Fachada única para control de motores y servos vía UART."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._ser = serial.Serial(config.uart_port, config.uart_baud)
        self._lock = threading.Lock()
        log.info("UART conectado: %s @ %d baud", config.uart_port, config.uart_baud)

    def send(self, cmd: MotorCommand) -> None:
        """Envía un comando de movimiento al driver de motores.

        Convierte velocidades diferenciales a 4 motores, ángulos a PWM,
        construye las tramas binarias con CRC8 y las escribe al UART.
        """
        v_left, v_right = self._apply_diff_cap(cmd.left_speed, cmd.right_speed)
        m1, m2, m3, m4 = self._differential(v_left, v_right)
        pan = cmd.pan_angle if cmd.pan_angle is not None else self._cfg.pan_center
        tilt = cmd.tilt_angle if cmd.tilt_angle is not None else self._cfg.tilt_center
        self._burst(pan, tilt, cmd.dur_ms, m1, m2, m3, m4)

    def stop(self, dur_ms: int = 300) -> None:
        """Detiene todos los motores."""
        self._burst(self._cfg.pan_center, self._cfg.tilt_center, dur_ms,
                     0.0, 0.0, 0.0, 0.0)

    def close(self) -> None:
        """Cierra la conexión UART."""
        self._ser.close()
        log.info("UART cerrado")

    # ── Conversión diferencial ────────────────────────────────────────────

    def _apply_diff_cap(self, v_left: float, v_right: float) -> tuple[float, float]:
        cap = self._cfg.diff_cap
        mx = max(abs(v_left), abs(v_right))
        if mx > cap:
            s = cap / mx
            v_left *= s
            v_right *= s
        return v_left, v_right

    def _differential(self, v_left: float, v_right: float) -> tuple[float, float, float, float]:
        """Convierte velocidades de rueda a cuarteto de motor.

        Convención:
          - v_left positivo → avance rueda izquierda
          - v_right negativo → avance rueda derecha
          - m1, m2 siempre 0.0 (no son ruedas de tracción)
          - m3 = -v_right → rueda derecha física
          - m4 = -v_left  → rueda izquierda física
        """
        return (0.0, 0.0, -v_right, -v_left)

    # ── Protocolo binario (burst) ─────────────────────────────────────────

    def _burst(
        self,
        pan: float, tilt: float, dur_ms: int,
        m1: float, m2: float, m3: float, m4: float,
    ) -> None:
        """Construye y envía las dos tramas (servo + motor) al UART."""
        # PWM: 500µs @ 0° → 2500µs @ 180°
        pp = int(500 + (max(0, min(180, pan)) / 180.0) * 2000)
        tp = int(500 + (max(0, min(180, tilt)) / 180.0) * 2000)
        d = int(dur_ms)

        # Trama de servos (cmd 0x04)
        sd = bytearray([
            0x01,
            d & 0xFF,
            (d >> 8) & 0xFF,
            2,
            self._cfg.servo_pan_id,
            pp & 0xFF,
            (pp >> 8) & 0xFF,
            self._cfg.servo_tilt_id,
            tp & 0xFF,
            (tp >> 8) & 0xFF,
        ])
        fs = bytearray(b"\xaa\x55") + bytes([0x04, len(sd)]) + sd
        fs.append(crc8(fs[2:]))

        # Trama de motores (cmd 0x03)
        md = bytearray([0x05, 4])
        for mid, val in ((1, m1), (2, m2), (3, m3), (4, m4)):
            md += struct.pack("<Bf", mid - 1, float(val))
        fm = bytearray(b"\xaa\x55") + bytes([0x03, len(md)]) + md
        fm.append(crc8(fm[2:]))

        with self._lock:
            self._ser.write(fs + fm)
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; pytest tests/test_motors.py -v
```
Esperado: 4 passed

- [ ] **Paso 5: Commit**

```bash
git add futbot/motors.py futbot/tests/test_motors.py
git commit -m "feat: crear motors.py con protocolo UART y control diferencial"
```

---

### Tarea 5: Crear `pipeline.py`

**Archivos:**
- Crear: `futbot/pipeline.py`
- Test: `futbot/tests/test_pipeline.py`

**Interfaces:**
- Produce: `Pipeline` class con `tick(dets: Detections) -> MotorCommand`
- Consume: `Config` de `config.py`, `Detections` de `vision.py`, `MotorCommand` de `motors.py`

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_pipeline.py
import sys
sys.path.insert(0, ".")

def test_pipeline_starts_in_search():
    from pipeline import Pipeline
    from config import Config
    cfg = Config()
    pip = Pipeline(cfg)
    assert pip.state == "SEARCH"

def test_search_to_chase_transition():
    """Al detectar pelota, debe transicionar a CHASE."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    # Pelota visible → debe ir a CHASE
    dets = Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9))
    cmd = pip.tick(dets)
    assert pip.state == "CHASE"
    # En CHASE debe producir velocidades no nulas
    assert cmd.left_speed != 0 or cmd.right_speed != 0

def test_chase_to_recovery_transition():
    """Al perder la pelota por suficiente tiempo, debe ir a RECOVERY."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    # Primero ir a CHASE
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    assert pip.state == "CHASE"
    # Perder pelota — varias ticks sin detección
    for _ in range(50):
        cmd = pip.tick(Detections())
    assert pip.state in ("RECOVERY", "SEARCH")

def test_ball_centered_goes_straight():
    """Pelota en el centro debe producir avance recto."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    cmd = pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    # Ambas ruedas deben ser positivas o tener magnitudes similares
    assert cmd.left_speed > 0
    assert cmd.right_speed > 0
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; pytest tests/test_pipeline.py -v
```
Esperado: FAIL

- [ ] **Paso 3: Escribir `pipeline.py`**

```python
"""Pipeline FSM — máquina de estados del robot.

Estados:
  SEARCH    → barrido rotacional buscando la pelota.
  CHASE     → servo visual: avance con giro proporcional al error.
  RECOVERY  → búsqueda en espiral para re-adquirir la pelota.

Transiciones:
  SEARCH → CHASE    (pelota detectada)
  CHASE  → RECOVERY (pelota perdida > timeout)
  RECOVERY → CHASE  (pelota re-detectada)
  RECOVERY → SEARCH (timeout sin encontrar)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from config import Config
from motors import MotorCommand
from vision import Ball, Detections

log = logging.getLogger("futbot.pipeline")

# Estados
SEARCH = "SEARCH"
CHASE = "CHASE"
RECOVERY = "RECOVERY"


class Pipeline:
    """Controlador FSM que convierte detecciones en comandos de motores."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._state: str = SEARCH
        self._last_cx: Optional[float] = None
        self._miss_start: Optional[float] = None
        self._last_ball_time: float = 0.0
        self._last_search_time: float = 0.0
        self._last_chase_time: float = 0.0
        self._recovery_step: int = 0
        self._recovery_dir: str = "left"
        self._frame_width: int = config.camera_width

    @property
    def state(self) -> str:
        return self._state

    def set_frame_width(self, w: int) -> None:
        self._frame_width = w

    def tick(self, dets: Detections) -> MotorCommand:
        """Evalúa el estado actual, decide transición y retorna comando."""
        now = time.time()
        ball: Optional[Ball] = dets.ball
        ball_visible = ball is not None
        line = dets.white_line
        frame_center = self._frame_width / 2

        # Actualizar tracking de pelota
        cx = None
        if ball_visible:
            cx = ball.x * self._frame_width  # convertir normalizado → píxeles
        if ball_visible:
            self._last_cx = cx
            self._miss_start = None
        elif self._miss_start is None:
            self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0

        # ── Transiciones ──────────────────────────────────────────────────
        prev = self._state

        if self._state == CHASE:
            if not ball_visible and miss_secs >= self._cfg.chase_miss_secs:
                self._state = RECOVERY

        elif self._state == RECOVERY:
            if ball_visible:
                self._state = CHASE
            elif self._recovery_step >= self._cfg.recovery_max_steps * 2:
                self._state = SEARCH

        elif self._state == SEARCH:
            if ball_visible:
                self._state = CHASE

        # Reset al entrar a un estado
        if self._state != prev:
            log.info("fsm: %s → %s", prev, self._state)
            if self._state == SEARCH:
                self._last_search_time = 0.0
                self._last_cx = None
            elif self._state == CHASE:
                self._last_chase_time = 0.0
            elif self._state == RECOVERY:
                self._recovery_step = 0
                self._recovery_dir = (
                    "left" if self._last_cx is None or self._last_cx < frame_center
                    else "right"
                )

        # ── Acción según estado ──────────────────────────────────────────

        if self._state == SEARCH:
            cmd = self._tick_search(now)
        elif self._state == CHASE:
            cmd = self._tick_chase(now, ball, ball_visible, frame_center)
        elif self._state == RECOVERY:
            cmd = self._tick_recovery(now, ball_visible, line)
        else:
            cmd = MotorCommand(0.0, 0.0, 100)

        return cmd

    def _tick_search(self, now: float) -> MotorCommand:
        """Barrido rotacional: gira, espera, gira en dirección opuesta."""
        if now - self._last_search_time >= self._cfg.search_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < self._frame_width / 2
            ) else "right"
            speed = self._cfg.search_turn_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_search_time = now
            return MotorCommand(v_left, v_right, self._cfg.search_turn_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_chase(
        self, now: float, ball: Optional[Ball], ball_visible: bool, frame_center: float
    ) -> MotorCommand:
        """Servo visual: giro proporcional al error horizontal."""
        if ball_visible and ball is not None:
            self._last_ball_time = now
            cx = ball.x * self._frame_width
            radius = ball.radius * max(self._frame_width, self._cfg.camera_height)

            # Patada directa si la pelota está muy grande (cerca)
            if radius >= self._cfg.kick_radius_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error = cx - frame_center
            if abs(error) <= self._cfg.chase_deadband_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error_norm = min(abs(error) / frame_center, 1.0)
            diff = self._cfg.chase_speed_base * error_norm * self._cfg.chase_rot_gain
            base = self._cfg.chase_speed_base

            if error > 0:
                v_left = base + diff
                v_right = max(0.0, base - diff)
            else:
                v_left = max(0.0, base - diff)
                v_right = base + diff
            return MotorCommand(v_left, v_right, 100)

        # Pelota perdida — escaneo ciego
        if now - self._last_ball_time < self._cfg.chase_miss_secs:
            return MotorCommand(self._cfg.chase_blind_speed,
                                self._cfg.chase_blind_speed, 100)

        if now - self._last_chase_time >= self._cfg.chase_blind_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < frame_center
            ) else "right"
            speed = self._cfg.chase_blind_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_chase_time = now
            return MotorCommand(v_left, v_right, self._cfg.chase_blind_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_recovery(
        self, now: float, ball_visible: bool, line
    ) -> MotorCommand:
        """Recuperación: alterna retroceso y giro para reencontrar pelota."""
        # Si detecta línea blanca, retroceder y girar
        if line is not None and line.detected:
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)

        step = self._recovery_step
        self._recovery_step += 1

        if step == 0:
            # Retroceder
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
        elif step % 2 == 1:
            # Girar
            speed = self._cfg.recovery_turn_speed
            if self._recovery_dir == "left":
                return MotorCommand(-speed, speed, self._cfg.recovery_turn_ms)
            else:
                return MotorCommand(speed, -speed, self._cfg.recovery_turn_ms)
        else:
            # Avanzar un poco
            return MotorCommand(self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; pytest tests/test_pipeline.py -v
```
Esperado: 4 passed

- [ ] **Paso 5: Commit**

```bash
git add futbot/pipeline.py futbot/tests/test_pipeline.py
git commit -m "feat: crear pipeline.py con FSM SEARCH/CHASE/RECOVERY"
```

---

### Tarea 6: Crear `main.py`

**Archivos:**
- Crear: `futbot/main.py`
- Test: `futbot/tests/test_integration.py`

**Interfaces:**
- Produce: `main()` function — entry point
- Consume: `Config`, `Camera`, `Vision`, `Motors`, `Pipeline`

- [ ] **Paso 1: Escribir el test de integración**

```python
# futbot/tests/test_integration.py
import sys
sys.path.insert(0, ".")

def test_full_loop_with_stubs():
    """Ejecuta el bucle completo con stubs y verifica que no crashea."""
    import os
    os.environ["FUTBOT_MODE"] = "stub"

    from config import Config
    from stubs.camera_stub import CameraStub
    from stubs.motors_stub import MotorsStub
    from vision import Vision
    from pipeline import Pipeline
    import numpy as np

    cfg = Config()
    cam = CameraStub(cfg)
    vis = Vision(cfg)
    mot = MotorsStub(cfg)
    pip = Pipeline(cfg)

    # Ejecutar 10 ticks del bucle
    for _ in range(10):
        frame = cam.grab()
        if frame is None:
            continue
        dets = vis.detect(frame)
        cmd = pip.tick(dets)
        mot.send(cmd)

    history = mot.get_history()
    assert len(history) > 0, "Debe haber al menos un comando enviado"
    # Verificar que los comandos tienen estructura válida
    for cmd in history:
        assert -300 <= cmd.left_speed <= 300
        assert -300 <= cmd.right_speed <= 300
```

- [ ] **Paso 2: Ejecutar test para verificar que falla (no hay stubs aún)**

```bash
cd futbot; pytest tests/test_integration.py -v
```
Esperado: FAIL — `ModuleNotFoundError`

- [ ] **Paso 3: Crear stubs primero (dependencia)**

```python
# futbot/stubs/__init__.py
"""Stubs de hardware para desarrollo local sin Raspberry Pi.

Uso:
    export FUTBOT_MODE=stub
    python main.py
"""

from stubs.camera_stub import CameraStub
from stubs.motors_stub import MotorsStub
```

```python
# futbot/stubs/camera_stub.py
"""Cámara stub: reproduce frames pregrabados o genera frames sintéticos."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import Config


class CameraStub:
    """Cámara fake para desarrollo local."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._width = config.camera_width
        self._height = config.camera_height
        self._frame_idx = 0
        self._frames = self._load_test_frames()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Devuelve un frame sintético o pregrabado."""
        if self._frames:
            frame = self._frames[self._frame_idx % len(self._frames)]
            self._frame_idx += 1
            return frame.copy()

        # Frame sintético: fondo verde con círculo naranja
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:] = (50, 120, 50)  # BGR verde campo

        # Círculo naranja (pelota) en posición aleatoria
        cx = random.randint(self._width // 4, 3 * self._width // 4)
        cy = random.randint(self._height // 4, 3 * self._height // 4)
        cv2.circle(frame, (cx, cy), 25, (0, 140, 255), -1)

        return frame

    def release(self) -> None:
        pass

    def _load_test_frames(self) -> list[np.ndarray]:
        """Carga frames pregrabados desde stubs/test_frames/ si existen."""
        test_dir = Path(__file__).parent / "test_frames"
        if not test_dir.exists():
            return []
        frames = []
        for path in sorted(test_dir.glob("*.png")):
            frame = cv2.imread(str(path))
            if frame is not None:
                frames.append(frame)
        return frames
```

```python
# futbot/stubs/motors_stub.py
"""Motores stub: registra comandos en vez de enviarlos por UART."""

from __future__ import annotations

from motors import MotorCommand


class MotorsStub:
    """Motores fake que loguean comandos para desarrollo local."""

    def __init__(self, config) -> None:
        self._cfg = config
        self._history: list[MotorCommand] = []

    def send(self, cmd: MotorCommand) -> None:
        self._history.append(MotorCommand(
            left_speed=cmd.left_speed,
            right_speed=cmd.right_speed,
            dur_ms=cmd.dur_ms,
            pan_angle=cmd.pan_angle,
            tilt_angle=cmd.tilt_angle,
        ))

    def stop(self, dur_ms: int = 300) -> None:
        self._history.append(MotorCommand(0.0, 0.0, dur_ms))

    def close(self) -> None:
        pass

    def get_history(self) -> list[MotorCommand]:
        return self._history
```

- [ ] **Paso 4: Ejecutar test de integración**

```bash
cd futbot; FUTBOT_MODE=stub pytest tests/test_integration.py -v
```
Esperado: 1 passed

- [ ] **Paso 5: Escribir `main.py`**

```python
"""Punto de entrada del robot futbolero.

Inicializa los servicios (cámara, visión, motores, pipeline) y ejecuta el
bucle principal FSM.

Modos vía variable de entorno FUTBOT_MODE:
  real  → hardware real en Raspberry Pi 5
  stub  → desarrollo local con stubs (sin hardware)

Uso:
  FUTBOT_MODE=stub python main.py   # desarrollo local
  python main.py                    # hardware real (default)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("futbot")

MODE = os.environ.get("FUTBOT_MODE", "real")
running = True


def _shutdown(signum, frame):
    global running
    log.info("Señal %s recibida, apagando...", signum)
    running = False


def main():
    from config import Config

    cfg = Config()
    cam = None
    mot = None

    log.info("futbot iniciando en modo %s", MODE)

    try:
        if MODE == "stub":
            from stubs.camera_stub import CameraStub
            from stubs.motors_stub import MotorsStub
            cam = CameraStub(cfg)
            mot = MotorsStub(cfg)
            log.info("Usando stubs de hardware")
        else:
            from camera import Camera
            from motors import Motors
            cam = Camera(cfg)
            mot = Motors(cfg)

        from vision import Vision
        from pipeline import Pipeline

        vis = Vision(cfg)
        pip = Pipeline(cfg)
        pip.set_frame_width(cam.width)

        log.info("Servicios inicializados. Ancho de frame: %d", cam.width)
        log.info("Bucle principal iniciado")

        while running:
            frame = cam.grab()
            if frame is None:
                time.sleep(0.005)
                continue

            dets = vis.detect(frame)
            cmd = pip.tick(dets)
            mot.send(cmd)

            time.sleep(0.01)

    except KeyboardInterrupt:
        log.info("Apagado por teclado")
    except Exception as exc:
        log.exception("Error en runtime: %s", exc)
    finally:
        if mot is not None:
            try:
                mot.stop(200)
                mot.close()
            except Exception:
                pass
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass
        log.info("futbot apagado")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    main()
```

- [ ] **Paso 6: Ejecutar todos los tests**

```bash
cd futbot; FUTBOT_MODE=stub pytest tests/ -v
```
Esperado: todos los tests pasan (config, pipeline, motors, vision, integration)

- [ ] **Paso 7: Commit**

```bash
git add futbot/main.py futbot/stubs/ futbot/tests/test_integration.py
git commit -m "feat: crear main.py con orquestador y stubs de hardware"
```

---

### Tarea 7: Migrar `scripts/`

**Archivos:**
- Copiar: `futbot-v8/scripts/*` → `futbot/scripts/`
- Copiar: `futbot-v8/src/vision/utils/_libcamera_worker.py` → `futbot/scripts/_libcamera_worker.py`

**Interfaces:**
- Ninguna — los scripts son independientes

- [ ] **Paso 1: Copiar scripts desde v8**

```bash
cp -r futbot-v8/scripts/* futbot/scripts/
```

- [ ] **Paso 2: Copiar libcamera worker**

```bash
cp futbot-v8/src/vision/utils/_libcamera_worker.py futbot/scripts/_libcamera_worker.py
```

- [ ] **Paso 3: Verificar que los scripts son ejecutables**

```bash
ls futbot/scripts/
```
Esperado: lista de 11+ scripts incluyendo `_libcamera_worker.py`

- [ ] **Paso 4: Commit**

```bash
git add futbot/scripts/
git commit -m "chore: migrar scripts de diagnostico y calibracion desde v8"
```

---

### Tarea 8: Copiar `models/`

**Archivos:**
- Copiar: `futbot-v8/models/` → `futbot/models/`

- [ ] **Paso 1: Copiar modelos**

```bash
cp -r futbot-v8/models/* futbot/models/
```

- [ ] **Paso 2: Commit**

```bash
git add futbot/models/
git commit -m "chore: copiar modelos ML desde v8"
```

---

### Tarea 9: Crear `pyproject.toml` y `README.md`

**Archivos:**
- Crear: `futbot/pyproject.toml`
- Crear: `futbot/README.md`

- [ ] **Paso 1: Escribir `pyproject.toml`**

```toml
[project]
name = "futbot"
version = "9.0.0"
description = "Robot autónomo de fútbol sobre Raspberry Pi 5"
requires-python = ">=3.11,<3.15"

dependencies = [
    "opencv-python>=4.13",
    "numpy>=2,<3",
    "pyserial>=3.5",
]

[project.optional-dependencies]
onnx = [
    "onnxruntime>=1.24",
]
ncnn = [
    "ncnn",
]
model-tools = [
    "onnxruntime>=1.24",
    "ultralytics>=8.4",
]

[dependency-groups]
dev = [
    "pytest>=9.0",
]

[tool.uv]
required-environments = [
    "sys_platform == 'linux' and platform_machine == 'aarch64'",
]
```

- [ ] **Paso 2: Escribir `README.md`**

```markdown
# Futbot v9

Robot autónomo de fútbol sobre Raspberry Pi 5 con cámara CSI IMX219.

## Estructura

```
futbot/
├── main.py           # Punto de entrada
├── config.py         # Constantes globales
├── camera.py         # Captura de frames (libcamera/GStreamer/V4L2)
├── vision.py         # Detección híbrida YOLO + HSV
├── pipeline.py       # FSM: BUSCAR → PERSEGUIR → RECUPERAR
├── motors.py         # Control UART de motores y servos
├── stubs/            # Mocks para desarrollo local
├── models/           # Modelos ML (ONNX, NCNN)
├── scripts/          # Diagnóstico y calibración
└── tests/            # Tests con pytest
```

## Requisitos

- Python 3.11+
- Raspberry Pi 5 (para hardware real)
- Cámara CSI IMX219
- Driver de motores conectado por UART (/dev/ttyAMA0)

## Instalación

```bash
# Instalar uv (gestor de paquetes)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependencias
uv sync

# Opcional: instalar backend YOLO
uv sync --group onnx    # ONNX Runtime
uv sync --group ncnn    # NCNN (optimizado ARM)
```

## Uso

```bash
# Desarrollo local (sin hardware)
FUTBOT_MODE=stub uv run python main.py

# Hardware real en Raspberry Pi 5
uv run python main.py
```

## Tests

```bash
FUTBOT_MODE=stub uv run pytest tests/ -v
```

## Arquitectura

Flujo de datos: `camera.py → vision.py → pipeline.py → motors.py`

Cada módulo depende solo de `config.py` y de los dataclasses compartidos:
- `vision.py` define `Detections`, `Ball`, `Goal`, `WhiteLine`
- `motors.py` define `MotorCommand`
- `pipeline.py` importa ambos

Sin inyección de dependencias compleja: `main.py` instancia y conecta todo.
```

- [ ] **Paso 3: Commit**

```bash
git add futbot/pyproject.toml futbot/README.md
git commit -m "docs: crear pyproject.toml y README para v9"
```

---

### Tarea 10: Limpieza final y verificación

- [ ] **Paso 1: Verificar estructura final**

```bash
ls futbot/
```
Esperado: `config.py`, `camera.py`, `vision.py`, `pipeline.py`, `motors.py`, `main.py`, `stubs/`, `models/`, `scripts/`, `tests/`, `pyproject.toml`, `README.md`

- [ ] **Paso 2: Ejecutar suite completa de tests**

```bash
cd futbot; FUTBOT_MODE=stub python -m pytest tests/ -v
```
Esperado: todos los tests pasan (~10-14 tests)

- [ ] **Paso 3: Verificar que main.py inicia en modo stub**

```bash
cd futbot; timeout 3 python -c "import os; os.environ['FUTBOT_MODE']='stub'; exec(open('main.py').read())" 2>&1 || true
```
Esperado: mensajes de inicio, sin crashes

- [ ] **Paso 4: Commit final**

```bash
git add -A futbot/
git commit -m "feat: completar refactor v9 — estructura plana unificada"
```

---

## Dependencias entre tareas

```
T1 (config.py) ──┬── T2 (camera.py) ──┬── T5 (pipeline.py) ──┬── T6 (main.py) ── T10 (verificación)
                 │                    │                       │
                 ├── T3 (vision.py) ──┘                       │
                 │                                            │
                 └── T4 (motors.py) ──────────────────────────┘

T7 (scripts/) — independiente, puede correr en paralelo
T8 (models/) — independiente, puede correr en paralelo
T9 (pyproject.toml + README) — después de T6
```

T1 debe ir primero (todos dependen de config.py). T2, T3, T4 pueden correr en paralelo tras T1. T5 requiere T3 y T4. T6 requiere T2 y T5 (y stubs). T7 y T8 son independientes.
