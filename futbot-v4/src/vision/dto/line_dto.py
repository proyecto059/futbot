"""DTO de la detección de línea blanca en la ROI inferior del frame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LineDto:
    """Línea blanca detectada (borde del campo) para lógica AVOID_MAP.

    - `detected`: True si los pixeles blancos exceden el umbral.
    - `cx`: centroide horizontal de la línea (None si no detectada).
    - `pixels`: conteo crudo de pixeles blancos (útil para debug / tuning).
    """

    detected: bool
    cx: Optional[float]
    pixels: int

    def to_dict(self) -> dict:
        return {
            "detected": bool(self.detected),
            "cx": float(self.cx) if self.cx is not None else None,
            "pixels": int(self.pixels),
        }

    @classmethod
    def empty(cls) -> "LineDto":
        return cls(detected=False, cx=None, pixels=0)
