"""Excepción: error durante la ejecución del modelo YOLO."""

from vision.exceptions.vision_exception import VisionException


class YoloInferenceException(VisionException):
    """Error capturado en el worker thread de YOLO (blob, session.run, parseo)."""