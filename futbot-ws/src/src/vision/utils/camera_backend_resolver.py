"""Resuelve el backend de cámara probando picamera2 → GStreamer → V4L2.

Migrado desde `cam.py` (antiguo `find_camera`, `_try_picamera2`, `_try_gstreamer_libcamera`,
`_try_v4l2`). El orden es importante: en Raspberry Pi 5 con IMX219 CSI, picamera2
es el backend nativo y rápido; GStreamer es el fallback si picamera2 no está
instalado; V4L2 cubre webcams USB para desarrollo en laptops.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import struct
import subprocess
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np

from vision.utils.vision_constants import (
    CAMERA_EXPOSURE_DEFAULT,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
)

log = logging.getLogger("turbopi.vision.camera")


class _Picamera2Camera:
    """Adapta `picamera2.Picamera2` a la interfaz tipo `cv2.VideoCapture`.

    Expone read() / get() / release() / isOpened() para que el resto del
    pipeline trate este objeto igual que un VideoCapture de OpenCV.
    """

    def __init__(self, width: int = CAMERA_WIDTH, height: int = CAMERA_HEIGHT) -> None:
        from picamera2 import Picamera2  # import lazy: sólo si estamos en RPi

        self._picam = Picamera2()
        config = self._picam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"},
            buffer_count=2,
        )
        self._picam.configure(config)
        self._picam.start()
        self._width = width
        self._height = height
        self._running = True
        time.sleep(0.3)  # deja que el sensor se estabilice antes del primer frame

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self._running:
            return False, None
        try:
            frame = self._picam.capture_array("main")
        except Exception as exc:  # noqa: BLE001 (log y seguimos)
            log.warning("[picamera2] capture error: %s", exc)
            return False, None
        if frame is None:
            return False, None
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def get(self, prop: int):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._height
        return 0

    def set(self, prop: int, value) -> bool:  # noqa: ARG002
        # picamera2 no expone control de exposición a través de cv2.CAP_PROP_*
        return False

    def grab(self) -> bool:
        return True

    def isOpened(self) -> bool:
        return self._running

    def release(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._picam.stop()
            self._picam.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("[picamera2] release error: %s", exc)


class _LibcameraCap:
    """libcamera via subprocess (system Python 3.12) → frames numpy/OpenCV.

    El worker ``_libcamera_worker.py`` se ejecuta con el intérprete del sistema
    (``/usr/bin/python3.12``) que tiene acceso a los bindings C de libcamera.
    La comunicación es por pipes: frames BGR por stdout, comandos por stdin.
    """

    _EXPOSURE_TO_US = 100
    _HEADER_FMT = "<4sIIII"
    _HEADER_SIZE = struct.calcsize(_HEADER_FMT)
    _MAGIC = b"\xf8\xb4\xc2\x0d"
    _SYSTEM_PYTHON = "/usr/bin/python3"

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self._exposure = CAMERA_EXPOSURE_DEFAULT
        self._running = True
        self._proc = None

        worker = os.path.join(os.path.dirname(__file__), "_libcamera_worker.py")
        if not os.path.isfile(worker):
            raise RuntimeError(f"libcamera worker not found: {worker}")
        if not os.path.isfile(self._SYSTEM_PYTHON):
            raise RuntimeError(f"system Python not found: {self._SYSTEM_PYTHON}")

        self._proc = subprocess.Popen(
            [self._SYSTEM_PYTHON, worker, str(width), str(height)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        deadline = time.time() + 30
        ready_line = b""
        while time.time() < deadline:
            line = self._proc.stderr.readline()
            if not line:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"libcamera worker exited with code {self._proc.returncode}"
                    )
                time.sleep(0.1)
                continue
            ready_line = line.strip()
            if ready_line.startswith(b"READY"):
                break
            if b"Error" in line or b"error" in line or b"FAIL" in line:
                self.release()
                raise RuntimeError(f"libcamera worker error: {line.decode().strip()}")
        else:
            self.release()
            raise RuntimeError("libcamera worker: timed out waiting for READY")

        parts = ready_line.decode().split()
        if len(parts) >= 3:
            self._width = int(parts[1])
            self._height = int(parts[2])

        self._send_command(f"EXPOSURE {CAMERA_EXPOSURE_DEFAULT * self._EXPOSURE_TO_US}")

    def _send_command(self, cmd: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write((cmd + "\n").encode())
            self._proc.stdin.flush()
        except BrokenPipeError:
            self._running = False

    def _read_exact(self, n: int) -> Optional[bytes]:
        if self._proc is None or self._proc.stdout is None:
            return None
        data = b""
        while len(data) < n:
            chunk = self._proc.stdout.read(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def read(self):
        if not self._running or self._proc is None:
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
        self._width = w
        self._height = h
        return True, frame

    def grab(self):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._width
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._height
        if prop == cv2.CAP_PROP_EXPOSURE:
            return self._exposure
        return 0

    def set(self, prop, value):
        if prop == cv2.CAP_PROP_AUTO_EXPOSURE:
            self._send_command(f"AE {1 if value != 1 else 0}")
            return True
        if prop == cv2.CAP_PROP_EXPOSURE:
            self._exposure = int(value)
            self._send_command(f"EXPOSURE {int(value) * self._EXPOSURE_TO_US}")
            return True
        return False

    def isOpened(self):
        return self._running and (self._proc is not None and self._proc.poll() is None)

    def release(self):
        self._running = False
        if self._proc is not None:
            try:
                if self._proc.stdin is not None:
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


class CameraBackendResolver:
    """Intenta abrir una cámara probando backends en orden de preferencia.

    Uso:
        cap, width, exposure = CameraBackendResolver.resolve()
        if cap is None:
            raise CameraNotFoundException(...)
    """

    @staticmethod
    def _try_picamera2(width: int, height: int):
        try:
            cap = _Picamera2Camera(width=width, height=height)
        except ImportError as exc:
            log.info(
                "picamera2 no instalado (%s); probando GStreamer libcamerasrc", exc
            )
            return None
        except Exception as exc:  # noqa: BLE001
            log.info("picamera2 no disponible: %s", exc)
            return None

        # Espera hasta 10 frames para confirmar que entrega imágenes reales
        for _ in range(10):
            ok, f = cap.read()
            if ok and f is not None:
                return cap
            time.sleep(0.05)
        cap.release()
        log.info("picamera2 inicializó pero no entregó frames")
        return None

    @staticmethod
    def _try_gstreamer_libcamera(width: int, height: int):
        pipeline = (
            f"libcamerasrc ! video/x-raw,width={width},height={height},format=BGRx "
            "! videoconvert ! video/x-raw,format=BGR "
            "! appsink drop=1 max-buffers=2 sync=false"
        )
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            return None
        for _ in range(15):
            cap.grab()
        ok, f = cap.read()
        if not (ok and f is not None):
            cap.release()
            return None
        return cap

    # Subcadenas (case-insensitive) que, si aparecen en el `name` del driver
    # V4L2, indican un subdevice del pipeline CSI/ISP/codec del Pi 5 y NO una
    # cámara enumerable. Abrirlos con cv2 provoca `select() timeout` de 10s.
    _V4L2_SKIP_NAME_PATTERNS = (
        "rp1-cfe",
        "pispbe",
        "bcm2835-isp",
        "hevc",
        "vc4",
        "codec",
    )

    @staticmethod
    def _read_v4l2_name(index: int) -> str:
        try:
            with open(f"/sys/class/video4linux/video{index}/name") as fh:
                return fh.read().strip()
        except OSError:
            return ""

    @staticmethod
    def _usb_indices_by_id() -> List[int]:
        """Índices referenciados desde `/dev/v4l/by-id/*` (USB UVC)."""
        indices: List[int] = []
        for p in glob.glob("/dev/v4l/by-id/*"):
            try:
                real = os.path.realpath(p)
            except OSError:
                continue
            m = re.match(r"^/dev/video(\d+)$", real)
            if m:
                indices.append(int(m.group(1)))
        return indices

    @classmethod
    def _enumerate_video_indices(cls) -> List[int]:
        """Devuelve índices plausibles de cámara, USB primero, CSI-subdev filtrados.

        En Pi 5 los subdispositivos del CSI/ISP aparecen como /dev/video19+ y
        algunos (p.ej. rp1-cfe) *abren* pero bloquean en `grab()` con
        `select() timeout`. Se filtran leyendo `/sys/class/video4linux/videoN/name`.
        Además, cualquier índice enlazado desde `/dev/v4l/by-id/*` se prueba
        primero (USB UVC por convención).
        """
        candidates: List[int] = []
        for p in glob.glob("/dev/video*"):
            m = re.match(r"^/dev/video(\d+)$", p)
            if m:
                candidates.append(int(m.group(1)))
        candidates = sorted(set(candidates))

        usb_first = cls._usb_indices_by_id()
        usb_set = set(usb_first)

        kept: List[int] = []
        seen = set()

        for idx in sorted(usb_first):
            name = cls._read_v4l2_name(idx)
            kept.append(idx)
            seen.add(idx)
            log.debug("V4L2: prioridad USB /dev/video%d name=%r", idx, name)

        skip_patterns = cls._V4L2_SKIP_NAME_PATTERNS
        for idx in candidates:
            if idx in seen:
                continue
            name = cls._read_v4l2_name(idx)
            lname = name.lower()
            if any(pat in lname for pat in skip_patterns):
                log.debug("V4L2: skip /dev/video%d name=%r (subdev CSI/ISP)", idx, name)
                continue
            if idx in usb_set:
                continue  # ya añadido arriba
            kept.append(idx)
            seen.add(idx)

        if not kept:
            log.info(
                "V4L2: no hay dispositivos candidatos tras filtro (total descubiertos=%d)",
                len(candidates),
            )
        else:
            log.info("V4L2: candidatos tras filtro: %s", kept)
        return kept

    @staticmethod
    def _try_v4l2_index(width: int, height: int, index: int):
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(3):
            cap.grab()
        ok, f = cap.read()
        if not (ok and f is not None):
            cap.release()
            return None
        return cap

    @classmethod
    def _try_v4l2_any(cls, width: int, height: int):
        """Prueba en orden todos los /dev/videoN hasta dar con uno que entregue frames.

        Cubre webcams USB UVC (p. ej. Innomaker 720p) cuyo índice no está fijo.
        """
        indices = cls._enumerate_video_indices()
        if not indices:
            log.info("V4L2: no existen /dev/video* (¿no hay ninguna cámara?)")
            return None, None
        for idx in indices:
            cap = cls._try_v4l2_index(width, height, idx)
            if cap is not None:
                log.info("V4L2: /dev/video%d entrega frames", idx)
                return cap, idx
            log.debug("V4L2: /dev/video%d no entrega frames", idx)
        log.info(
            "V4L2: probé %d dispositivo(s) /dev/video* y ninguno entregó frames: %s",
            len(indices),
            indices,
        )
        return None, None

    @staticmethod
    def _calibrate_v4l2_exposure(cap) -> int:
        """Fija exposición manual para webcams V4L2 (estabiliza el brillo)."""
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
        cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE_DEFAULT)
        for _ in range(8):
            cap.grab()
        ok, frame = cap.read()
        if ok and frame is not None:
            v_med = int(np.median(frame[::4, ::4, :]))
            log.info(
                "Cámara V4L2 exp=%d v_median_raw=%d", CAMERA_EXPOSURE_DEFAULT, v_med
            )
        return CAMERA_EXPOSURE_DEFAULT

    @staticmethod
    def _try_libcamera_subprocess(width: int, height: int):
        try:
            cap = _LibcameraCap(width, height)
        except Exception as exc:
            log.info("libcamera subprocess no disponible: %s", exc)
            return None
        ok, f = cap.read()
        if ok and f is not None:
            return cap
        cap.release()
        log.info("libcamera subprocess no entregó frames")
        return None

    @classmethod
    def resolve(
        cls,
        width: int = CAMERA_WIDTH,
        height: int = CAMERA_HEIGHT,
    ) -> Tuple[Optional[object], int, int]:
        """Devuelve `(cap, frame_width_real, exposure)` o `(None, 0, 0)` si falla.

        El `frame_width_real` puede diferir de `width` cuando el backend no
        respeta la resolución pedida (GStreamer o V4L2). El caller lo necesita
        para calcular el centro X del frame.
        """
        log.info("Auto-detectando cámara CSI IMX219 (%dx%d)", width, height)

        cap = cls._try_picamera2(width, height)
        if cap is not None:
            log.info("IMX219 CSI detectada vía picamera2 (%dx%d)", width, height)
            return cap, width, CAMERA_EXPOSURE_DEFAULT

        cap = cls._try_libcamera_subprocess(width, height)
        if cap is not None:
            ok, f = cap.read()
            h, w = f.shape[:2] if ok and f is not None else (height, width)
            log.info("Cámara CSI detectada vía libcamera subprocess (%dx%d)", w, h)
            return cap, w, CAMERA_EXPOSURE_DEFAULT

        cap = cls._try_gstreamer_libcamera(width, height)
        if cap is not None:
            ok, f = cap.read()
            h, w = f.shape[:2] if ok and f is not None else (height, width)
            log.info("Cámara CSI detectada vía GStreamer libcamerasrc (%dx%d)", w, h)
            return cap, w, CAMERA_EXPOSURE_DEFAULT

        cap, idx = cls._try_v4l2_any(width, height)
        if cap is not None:
            ok, f = cap.read()
            h, w = f.shape[:2] if ok and f is not None else (height, width)
            exp = cls._calibrate_v4l2_exposure(cap)
            log.info("Cámara V4L2 /dev/video%d (%dx%d) exp=%d", idx, w, h, exp)
            return cap, w, exp

        log.error(
            "No se detectó ninguna cámara. Revisar: (1) cable CSI + `cam -l` para "
            "IMX219; (2) cámara USB conectada y enumerada en `ls /dev/video*`."
        )
        return None, 0, 0