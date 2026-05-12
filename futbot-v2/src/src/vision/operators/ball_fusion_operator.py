"""Fusión de las dos fuentes de detección de bola (HSV + YOLO) con caché.

    Regla:
    1. Si HSV detectó la bola en este frame → usar HSV (preciso, fresco).
    2. Si no hay HSV → None (perdimos la bola).

Motivación (heredada del HybridBallDetector original):
    HSV corre a 30+ FPS en el hilo principal y es muy sensible al color exacto.
    YOLO corre en paralelo a ~15 FPS y es más robusto a iluminación pero menos
    preciso en la posición. En la cancha actual YOLO y caché producen falsos
    positivos contra la pared/portería, así que no se usan para controlar el chase.
"""

from __future__ import annotations

from typing import Optional, Tuple

from vision.dto.ball_dto import BallDto
from vision.utils.vision_constants import BALL_FUSION_CACHE_TTL_SEC


class BallFusionOperator:
    """Fusiona HSV + YOLO + caché con TTL."""

    def __init__(self, cache_ttl: float = BALL_FUSION_CACHE_TTL_SEC) -> None:
        self._cache_ttl = float(cache_ttl)
        # Última bola reportada + timestamp (para decidir si la caché sigue válida)
        self._last_ball: Optional[BallDto] = None
        self._last_ts: float = 0.0

    def merge(
        self,
        hsv_ball: Optional[BallDto],
        yolo_ball: Optional[BallDto],
        now_ts: float,
    ) -> Optional[BallDto]:
        """Aplica la regla HSV > YOLO > caché. Mantiene estado interno."""
        if hsv_ball is not None:
            self._last_ball = hsv_ball
            self._last_ts = now_ts
            return hsv_ball

        # No devolvemos caché: una bola vieja o YOLO falso mueve el robot mal.
        if self._last_ball is not None:
            self._last_ball = None
        return None

    def last_known(self) -> Tuple[Optional[BallDto], float]:
        """Devuelve (última bola, timestamp) para debug."""
        return self._last_ball, self._last_ts
