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

    def to_dict(self) -> dict:
        return {
            "yellow": bool(self.yellow),
            "yellow_cx": float(self.yellow_cx) if self.yellow_cx is not None else None,
            "blue": bool(self.blue),
            "blue_cx": float(self.blue_cx) if self.blue_cx is not None else None,
        }

    @classmethod
    def empty(cls) -> "GoalsDto":
        return cls(yellow=False, yellow_cx=None, blue=False, blue_cx=None)