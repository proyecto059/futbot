"""Jerarquía de excepciones específicas del pipeline de visión."""

from vision.exceptions.camera_not_found_exception import CameraNotFoundException
from vision.exceptions.frame_capture_exception import FrameCaptureException
from vision.exceptions.vision_exception import VisionException
from vision.exceptions.yolo_inference_exception import YoloInferenceException
from vision.exceptions.yolo_model_not_found_exception import (
    YoloModelNotFoundException,
)

__all__ = [
    "CameraNotFoundException",
    "FrameCaptureException",
    "VisionException",
    "YoloInferenceException",
    "YoloModelNotFoundException",
]