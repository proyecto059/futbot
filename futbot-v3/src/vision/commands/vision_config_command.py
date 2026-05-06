"""Configuración de `HybridVisionService` (inmutable)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from vision.utils.vision_constants import (
    BALL_FUSION_CACHE_TTL_SEC,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    resolve_yolo_model_path,
)


@dataclass(frozen=True)
class VisionConfigCommand:
    """Parámetros globales del pipeline.

    Valores por defecto replican el comportamiento histórico de `cam.py`.
    Use `VisionConfigCommand.default()` para construir con los defaults.
    """

    # Cámara
    camera_width: int = CAMERA_WIDTH
    camera_height: int = CAMERA_HEIGHT

    # YOLO
    yolo_model_path: Optional[Path] = None

    # Fusión
    cache_ttl_sec: float = BALL_FUSION_CACHE_TTL_SEC

    # Debug
    enable_debug: bool = True

    @classmethod
    def default(cls) -> "VisionConfigCommand":
        return cls(yolo_model_path=resolve_yolo_model_path())

    def with_yolo_path(self, path: Path) -> "VisionConfigCommand":
        return VisionConfigCommand(
            camera_width=self.camera_width,
            camera_height=self.camera_height,
            yolo_model_path=path,
            cache_ttl_sec=self.cache_ttl_sec,
            enable_debug=self.enable_debug,
        )
