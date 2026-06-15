"""DTO de una detección de robot rival (viene siempre de YOLO, clase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RobotDto:
    """Bounding box de un robot detectado por YOLO."""

    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    cx: int
    cy: int
    r: float
    conf: float

    def to_dict(self) -> dict:
        return {
            "bbox": [int(v) for v in self.bbox],
            "cx": int(self.cx),
            "cy": int(self.cy),
            "r": float(self.r),
            "conf": float(self.conf),
        }
