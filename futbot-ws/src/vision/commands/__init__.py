"""Contratos de entrada al pipeline (DTOs inmutables de configuración y request)."""

from vision.commands.detect_vision_command import DetectVisionCommand
from vision.commands.vision_config_command import VisionConfigCommand

__all__ = ["DetectVisionCommand", "VisionConfigCommand"]