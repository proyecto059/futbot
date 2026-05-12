"""Detección de arcos por color HSV (amarillo y azul).

El FSM usa `yellow_cx` / `blue_cx` para orientar el robot hacia el arco a atacar.
La detección se hace sobre el frame completo (sin ROI) porque los arcos pueden
aparecer en cualquier parte del campo visual.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.dto.goals_dto import GoalsDto
from vision.utils.vision_constants import (
    GOAL_MIN_PIXELS,
    HSV_GOAL_BLUE_HI,
    HSV_GOAL_BLUE_LO,
    HSV_GOAL_YELLOW_HI,
    HSV_GOAL_YELLOW_LO,
)


class GoalColorDetectionOperator:
    """Stateless: calcula presencia + centroide X de cada arco en cada frame."""

    @staticmethod
    def _centroid_cx(mask: np.ndarray, pixels: int) -> float | None:
        """Centroide X de la máscara si hay suficientes pixeles, si no None."""
        if pixels < GOAL_MIN_PIXELS:
            return None
        moments = cv2.moments(mask)
        if moments["m00"] <= 0:
            return None
        return float(moments["m10"] / moments["m00"])

    def detect(self, frame: np.ndarray) -> GoalsDto:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        yellow_mask = cv2.inRange(hsv, HSV_GOAL_YELLOW_LO, HSV_GOAL_YELLOW_HI)
        blue_mask = cv2.inRange(hsv, HSV_GOAL_BLUE_LO, HSV_GOAL_BLUE_HI)

        yellow_pixels = int(cv2.countNonZero(yellow_mask))
        blue_pixels = int(cv2.countNonZero(blue_mask))

        yellow_cx = self._centroid_cx(yellow_mask, yellow_pixels)
        blue_cx = self._centroid_cx(blue_mask, blue_pixels)

        return GoalsDto(
            yellow=yellow_pixels >= GOAL_MIN_PIXELS,
            yellow_cx=yellow_cx,
            blue=blue_pixels >= GOAL_MIN_PIXELS,
            blue_cx=blue_cx,
        )