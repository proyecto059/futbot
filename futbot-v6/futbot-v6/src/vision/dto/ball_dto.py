"""DTO de una detección de bola unificada (viene de HSV, YOLO o caché)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# De dónde viene la detección. `cache` indica última detección válida reutilizada
# dentro del TTL definido en `BALL_FUSION_CACHE_TTL_SEC`.
BallSource = Literal["hsv", "yolo", "cache"]


@dataclass(frozen=True)
class BallDto:
    """Posición y confianza de la bola en coordenadas de imagen."""

    cx: int
    cy: int
    r: float
    conf: float
    source: BallSource

    def to_dict(self) -> dict:
        return {
            "cx": int(self.cx),
            "cy": int(self.cy),
            "r": float(self.r),
            "conf": float(self.conf),
            "source": self.source,
        }

    @classmethod
    def from_hsv(cls, cx: int, cy: int, r: float) -> "BallDto":
        """Construye un BallDto a partir de la salida cruda del operador HSV.

        El HSV no da confianza de red, así que se marca en 1.0 para que en
        una fusión empate o gane frente a YOLO con la regla "HSV > YOLO".
        """
        return cls(cx=int(cx), cy=int(cy), r=float(r), conf=1.0, source="hsv")

    def with_source(self, source: BallSource) -> "BallDto":
        """Devuelve copia con otro `source` (útil al marcar una detección como `cache`)."""
        return BallDto(cx=self.cx, cy=self.cy, r=self.r, conf=self.conf, source=source)


def ball_to_dict(ball: Optional[BallDto]) -> Optional[dict]:
    """Helper para serializar `ball` cuando puede ser None."""
    return ball.to_dict() if ball is not None else None
