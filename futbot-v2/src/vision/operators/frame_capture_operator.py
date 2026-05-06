"""HILO 1 — Captura de frames de OpenCV en un daemon thread.

Responsabilidad:
    - Abrir la cámara vía `CameraBackendResolver` (picamera2/GStreamer/V4L2).
    - Mantener un buffer de un solo frame (el más reciente) protegido por Lock.
    - El método `read_latest()` es NO BLOQUEANTE: devuelve el último frame o
      None si todavía no hay ninguno (útil en el primer tick del servicio).

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
    ) -> None:
        # Resuelve backend de cámara inmediatamente (fallar rápido si no hay)
        cap, frame_width, exposure = CameraBackendResolver.resolve(width, height)
        if cap is None:
            raise CameraNotFoundException(
                "No se detectó ningún backend de cámara (picamera2/GStreamer/V4L2)."
            )

        self._cap = cap
        self._frame_width = int(frame_width)
        self._exposure = int(exposure)

        # Estado compartido hilo-principal ↔ hilo-captura
        self._lock = Lock()
        self._latest_frame: Optional[FrameDto] = None
        self._frames_in = 0

        self._running = False
        self._thread: Optional[Thread] = None

    # ── API pública ──────────────────────────────────────────────────────

    @property
    def frame_width(self) -> int:
        """Ancho real del frame (puede diferir del pedido si el backend no respeta size)."""
        return self._frame_width

    @property
    def exposure(self) -> int:
        return self._exposure

    @property
    def raw_cap(self):
        """Acceso al VideoCapture crudo (para operadores que necesitan ajustar exposición)."""
        return self._cap

    def start(self) -> None:
        """Arranca el hilo de captura. Idempotente."""
        if self._running:
            return
        self._running = True
        self._thread = Thread(target=self._loop, name="vision-capture", daemon=True)
        self._thread.start()

    def read_latest(self) -> Optional[FrameDto]:
        """Devuelve el frame más reciente (copia) o None si aún no hay ninguno.

        NO BLOQUEANTE. El caller debe tolerar que la primera llamada devuelva
        None mientras el hilo captura el primer frame.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            # Copia defensiva: otros operadores pueden mantener el frame vivo
            # mientras el productor ya escribió el siguiente.
            return FrameDto.of(self._latest_frame.image.copy(), self._latest_frame.ts)

    def frames_captured(self) -> int:
        """Contador total de frames leídos (para debug/telemetría)."""
        with self._lock:
            return self._frames_in

    def close(self) -> None:
        """Detiene el hilo y libera la cámara."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            self._cap.release()
        except Exception as exc:  # noqa: BLE001
            log.warning("error liberando cámara: %s", exc)

    # ── Loop interno del hilo ────────────────────────────────────────────

    def _loop(self) -> None:
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                # Evita busy-loop si el backend está temporalmente sin frames
                time.sleep(0.005)
                continue
            ts = time.time()
            with self._lock:
                self._latest_frame = FrameDto.of(frame, ts)
                self._frames_in += 1
