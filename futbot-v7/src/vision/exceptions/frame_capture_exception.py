"""Excepción: falló la lectura de un frame después de abrir la cámara."""

from vision.exceptions.vision_exception import VisionException


class FrameCaptureException(VisionException):
    """El backend se abrió pero `read()` devolvió error repetidamente."""
