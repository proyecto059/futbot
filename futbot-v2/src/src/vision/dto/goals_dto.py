"""DTO del estado de los dos arcos (amarillo y azul) en el frame actual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GoalsDto:
    """Presencia y centroide horizontal de cada arco.

    - `yellow` / `blue`: True si se detectó suficiente área de ese color.
    - `yellow_cx` / `blue_cx`: centroide en X (pixeles) o None si no se detectó.
      El FSM usa estos valores para orientar el robot hacia el arco a atacar.
    """

    yellow: bool
    yellow_cx: Optional[float]
    blue: bool
    blue_cx: Optional[float]
    yellow_cy: Optional[float] = None
    blue_cy: Optional[float] = None
    yellow_bbox: Optional[list[int]] = None
    blue_bbox: Optional[list[int]] = None
    yellow_pixels: int = 0
    blue_pixels: int = 0

    def to_dict(self) -> dict:
        return {
            "yellow": bool(self.yellow),
            "yellow_cx": float(self.yellow_cx) if self.yellow_cx is not None else None,
            "yellow_cy": float(self.yellow_cy) if self.yellow_cy is not None else None,
            "yellow_bbox": list(self.yellow_bbox) if self.yellow_bbox is not None else None,
            "yellow_pixels": int(self.yellow_pixels),
            "blue": bool(self.blue),
            "blue_cx": float(self.blue_cx) if self.blue_cx is not None else None,
            "blue_cy": float(self.blue_cy) if self.blue_cy is not None else None,
            "blue_bbox": list(self.blue_bbox) if self.blue_bbox is not None else None,
            "blue_pixels": int(self.blue_pixels),
        }

    @classmethod
    def empty(cls) -> "GoalsDto":
        return cls(yellow=False, yellow_cx=None, blue=False, blue_cx=None)
