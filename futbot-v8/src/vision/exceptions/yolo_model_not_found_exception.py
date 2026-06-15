"""Excepción: el archivo `model.onnx` no está en ninguna ubicación conocida."""

from vision.exceptions.vision_exception import VisionException


class YoloModelNotFoundException(VisionException):
    """No se encontró `model.onnx` ni en la raíz del proyecto ni en `test-robot/`."""
