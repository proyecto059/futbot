### Tarea 2: Crear `camera.py`

**Archivos:**
- Crear: `futbot/camera.py`
- Test: `futbot/tests/test_camera.py`

**Interfaces:**
- Produce: `Camera` class con `grab() -> np.ndarray | None`, `release()`, `width`, `height`
- Consume: `Config` de `config.py`

El archivo `futbot/config.py` ya existe del Task 1.

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
    # En entorno sin cámara, debe lanzar RuntimeError con mensaje adecuado
    try:
        cam = Camera(cfg)
        assert cam is not None
        cam.release()
    except RuntimeError as e:
        assert "cámara" in str(e).lower() or "camera" in str(e).lower()
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; python -m pytest tests/test_camera.py -v
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
cd futbot; python -m pytest tests/test_camera.py -v
```
Esperado: 1 passed (test verifica que se lanza RuntimeError sin cámara)

- [ ] **Paso 5: Commit**

```bash
git add futbot/camera.py futbot/tests/test_camera.py
git commit -m "feat: crear camera.py con resolucion de backend unificada"
```
