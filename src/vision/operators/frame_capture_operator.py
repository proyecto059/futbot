"""HILO 1 — Captura de frames de OpenCV en un daemon thread.

Responsabilidad:
    - Abrir la cámara vía `CameraBackendResolver` (picamera2/GStreamer/V4L2).
    - Mantener un buffer de un solo frame (el más reciente) protegido por Lock.
    - El método `read_latest()` es NO BLOQUEANTE: devuelve el último frame o
      None si todavía no hay alguno (útil en el primer tick del servicio).
    - Si no hay cámara disponible, funciona en modo "dummy" sin fallar.

Por qué un hilo propio:
    `cap.read()` en V4L2 es bloqueante hasta que llega el próximo frame del
    sensor (~33 ms a 30 FPS). Si lo hiciéramos en el hilo principal, el FSM
    se sincronizaría con la cámara y perdería reactividad. Con este hilo el
    caller lee siempre el frame más fresco disponible al instante.
"""

from __future__ import annotations

import logging
import time
from threading import Lock, Thread
from typing import Optional

from vision.dto.frame_dto import FrameDto
from vision.exceptions.camera_not_found_exception import CameraNotFoundException
from vision.utils.camera_backend_resolver import CameraBackendResolver
from vision.utils.vision_constants import CAMERA_HEIGHT, CAMERA_WIDTH

log = logging.getLogger("turbopi.vision.capture")


class FrameCaptureOperator:
    """Productor de frames en background (hilo OpenCV)."""

    def __init__(
        self,
        width: int = CAMERA_WIDTH,
        height: int = CAMERA_HEIGHT,
        required: bool = False,
    ) -> None:
        self._width = width
        self._height = height
        self._required = required
        self._cap = None
        self._frame_width = width
        self._exposure = 0
        self._has_camera = False

        cap, frame_width, exposure = CameraBackendResolver.resolve(width, height)
        if cap is not None:
            self._cap = cap
            self._frame_width = int(frame_width)
            self._exposure = int(exposure)
            self._has_camera = True
            log.info("Camara detectada: %dx%d, exposure=%d", width, height, exposure)
        elif self._required:
            raise CameraNotFoundException(
                "No se detecto ninguna camara (picamera2/GStreamer/V4L2)."
            )
        else:
            log.warning("No se detecto camara — modo SIN CAMARA activado")

        self._lock = Lock()
        self._latest_frame: Optional[FrameDto] = None
        self._frames_in = 0

        self._running = False
        self._thread: Optional[Thread] = None

    @property
    def has_camera(self) -> bool:
        return self._has_camera

    @property
    def raw_cap(self):
        return self._cap

    def start(self) -> None:
        if self._has_camera:
            self._running = True
            self._thread = Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            log.info("Hilo de captura iniciado")
        else:
            log.info("Camara no disponible — hilo de captura NO iniciado")

    def _capture_loop(self) -> None:
        while self._running and self._cap is not None:
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest_frame = FrameDto(
                        frame=frame,
                        width=self._frame_width,
                        height=self._height,
                    )
                    self._frames_in += 1

    def read_latest(self) -> Optional[FrameDto]:
        with self._lock:
            return self._latest_frame

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        log.info("Hilo de captura detenido")