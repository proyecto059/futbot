"""Captura de frames — resuelve backend de cámara automáticamente.

Backends probados en orden de preferencia:
  1. picamera2 (nativo en RPi5, CSI IMX219, vía librería Python)
  2. libcamera vía subprocess (system Python con bindings C, comunicación por pipes)
  3. GStreamer libcamerasrc (pipeline GStreamer → OpenCV)
  4. V4L2 (/dev/video*, cámaras USB o CSI emuladas)

El módulo expone una clase `Camera` con interfaz simple:
    cam = Camera(config)
    frame = cam.grab()  # np.ndarray BGR o None si falla
    cam.release()

Los backends 1 y 2 se envuelven en adaptadores (`_Picamera2Adapter`,
`_LibcameraSubprocessAdapter`) que exponen la misma interfaz que
`cv2.VideoCapture` (read, release, isOpened).

Flujo de inicialización:
  1. `_resolve_backend()` → prueba cada backend en orden
  2. `_warmup()` → descarta los primeros frames para estabilizar exposición
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
    """Fachada unificada de captura de cámara.

    Oculta la complejidad de los 4 backends. El consumidor solo llama a
    `grab()` para obtener el frame más reciente en formato BGR.

    Atributos:
        width: Ancho real del frame capturado (puede diferir del configurado).
        height: Alto real del frame capturado.
    """

    def __init__(self, config: Config) -> None:
        """Inicializa la cámara resolviendo el mejor backend disponible.

        Recorre los 4 backends en orden. Si ninguno funciona, lanza
        RuntimeError con instrucciones de diagnóstico.

        Args:
            config: Instancia de Config con parámetros de cámara.

        Raises:
            RuntimeError: Si ningún backend de cámara está disponible.
        """
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
        """Ancho real del frame en píxeles (tras resolver el backend)."""
        return self._width

    @property
    def height(self) -> int:
        """Alto real del frame en píxeles (tras resolver el backend)."""
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Captura el frame más reciente de la cámara.

        Returns:
            Frame en formato BGR como array numpy (H, W, 3), o None si
            la captura falla (cámara desconectada, error del backend).
        """
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        if self._cfg.camera_flip_horizontal:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        """Libera la cámara y todos los recursos asociados.

        Es seguro llamarla múltiples veces. Las excepciones se suprimen
        para garantizar un apagado limpio sin crashes.
        """
        try:
            self._cap.release()
        except Exception:
            pass

    def _warmup(self) -> None:
        """Descarta los primeros frames hasta obtener uno válido.

        Las cámaras CSI necesitan algunas capturas para estabilizar
        exposición y balance de blancos. Sin warmup, los primeros frames
        pueden ser negros o verdes.
        """
        for _ in range(10):
            ok, _ = self._cap.read()
            if ok:
                break
            time.sleep(0.05)

    # ── Resolución de backend ─────────────────────────────────────────────

    def _resolve_backend(self) -> Tuple[object | None, int, int]:
        """Prueba los 4 backends en orden y devuelve el primero que funciona.

        Returns:
            Tupla (capture_obj, ancho_real, alto_real). Si ningún backend
            funciona, devuelve (None, 0, 0).
        """
        w, h = self._cfg.camera_width, self._cfg.camera_height

        cap = self._try_picamera2(w, h)
        if cap:
            return cap, w, h

        cap = self._try_libcamera_subprocess(w, h)
        if cap:
            return cap, w, h

        cap = self._try_gstreamer(w, h)
        if cap:
            rw, rh = self._get_frame_dims(cap, w, h)
            return cap, rw, rh

        cap, idx = self._try_v4l2_any(w, h)
        if cap:
            rw, rh = self._get_frame_dims(cap, w, h)
            return cap, rw, rh

        return None, 0, 0

    def _try_picamera2(self, w: int, h: int):
        """Intenta abrir la cámara CSI vía picamera2 (backend nativo RPi5).

        Args:
            w: Ancho deseado en píxeles.
            h: Alto deseado en píxeles.

        Returns:
            _Picamera2Adapter si funciona, None si falla.
        """
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
        """Intenta abrir la cámara vía libcamera en subprocess.

        Ejecuta `scripts/_libcamera_worker.py` con el Python del sistema
        (`/usr/bin/python3`) que tiene los bindings C de libcamera.
        La comunicación es por pipes: frames BGR por stdout,
        comandos por stdin. Espera la señal READY del worker.

        Args:
            w: Ancho deseado.
            h: Alto deseado.

        Returns:
            _LibcameraSubprocessAdapter si funciona, None si falla.
        """
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
        """Intenta abrir la cámara CSI vía pipeline GStreamer + OpenCV.

        Usa `libcamerasrc` como fuente y `appsink` como salida.
        Descarta 8 frames de warmup antes de validar.

        Args:
            w: Ancho deseado.
            h: Alto deseado.

        Returns:
            Objeto cv2.VideoCapture si funciona, None si falla.
        """
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
        """Busca una cámara V4L2 funcional entre todos los /dev/video*.

        Útil para webcams USB durante desarrollo local. Prueba cada
        dispositivo en orden, configurando resolución y buffersize.

        Args:
            w: Ancho deseado.
            h: Alto deseado.

        Returns:
            Tupla (cv2.VideoCapture, índice) o (None, None) si falla.
        """
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
        """Obtiene las dimensiones reales del frame desde el backend.

        Algunos backends (GStreamer, V4L2) pueden entregar frames con
        dimensiones diferentes a las solicitadas.

        Args:
            cap: Objeto de captura (cv2.VideoCapture o adaptador).
            default_w: Ancho por defecto si no se puede leer.
            default_h: Alto por defecto si no se puede leer.

        Returns:
            Tupla (ancho_real, alto_real).
        """
        ok, frame = cap.read()
        if ok and frame is not None:
            return frame.shape[1], frame.shape[0]
        return default_w, default_h


# ── Adaptadores de backend ────────────────────────────────────────────────────

class _Picamera2Adapter:
    """Adapta el objeto Picamera2 a la interfaz de cv2.VideoCapture.

    picamera2 usa `capture_array("main")` que devuelve RGB888.
    El adaptador lo convierte a BGR para que el resto del pipeline
    trabaje de forma consistente.

    Atributos:
        _picam: Instancia de Picamera2.
        _running: Flag de control de ciclo de vida.
    """

    def __init__(self, picam):
        """Inicializa el adaptador con una instancia de Picamera2 ya iniciada.

        Args:
            picam: Instancia configurada e iniciada de Picamera2.
        """
        self._picam = picam
        self._running = True

    def read(self):
        """Captura un frame del sensor.

        Returns:
            Tupla (True, frame_BGR) si funciona, (False, None) si falla.
        """
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
        """Verifica si el adaptador sigue activo.

        Returns:
            True si la cámara está funcionando.
        """
        return self._running

    def release(self):
        """Detiene y cierra la instancia de Picamera2."""
        if not self._running:
            return
        self._running = False
        try:
            self._picam.stop()
            self._picam.close()
        except Exception:
            pass


class _LibcameraSubprocessAdapter:
    """Adapta el worker libcamera (subprocess) a la interfaz de cv2.VideoCapture.

    El worker envía frames BGR por stdout con un header binario de 20 bytes.
    El adaptador lee el header, extrae dimensiones y tamaño, y reconstruye
    el array numpy.

    Protocolo del header:
        MAGIC (4B) | width (4B uint32) | height (4B uint32) |
        stride (4B uint32) | size (4B uint32)
    MAGIC = b'\\xf8\\xb4\\xc2\\x0d'

    Atributos de clase:
        _HEADER_FMT: Formato struct para el header (little-endian).
        _HEADER_SIZE: 20 bytes.
        _MAGIC: Bytes mágicos para validar el header.
    """

    _HEADER_FMT = "<4sIIII"
    _HEADER_SIZE = struct.calcsize(_HEADER_FMT)
    _MAGIC = b"\xf8\xb4\xc2\x0d"

    def __init__(self, proc, w: int, h: int):
        """Inicializa el adaptador con el proceso worker ya arrancado.

        Args:
            proc: Objeto Popen del worker libcamera.
            w: Ancho inicial esperado.
            h: Alto inicial esperado.
        """
        self._proc = proc
        self._width = w
        self._height = h
        self._running = True

    def read(self):
        """Lee un frame completo del pipe stdout del worker.

        Returns:
            Tupla (True, frame_BGR) o (False, None) si el worker murió
            o el pipe se cerró.
        """
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
        """Lee exactamente n bytes del pipe stdout del worker.

        Args:
            n: Número exacto de bytes a leer.

        Returns:
            Bytes leídos, o None si el pipe se cerró antes de completar.
        """
        data = b""
        while len(data) < n:
            chunk = self._proc.stdout.read(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def release(self):
        """Envía comando QUIT al worker y espera a que termine.

        Si el worker no responde en 3 segundos, lo mata con SIGKILL.
        """
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
