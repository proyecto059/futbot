"""Excepción: no se pudo abrir ningún backend de cámara."""

from vision.exceptions.vision_exception import VisionException


class CameraNotFoundException(VisionException):
    """Ningún backend (picamera2 / GStreamer / V4L2) devolvió un frame válido.

    Causas típicas:
      - Cable CSI desconectado
      - `libcamera` no reconoce el sensor
      - El usuario corre fuera de la Raspberry Pi sin webcam conectada
    """
