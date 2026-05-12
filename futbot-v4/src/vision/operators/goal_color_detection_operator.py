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
    GOAL_EDGE_MIN_COMPONENT_AREA,
    GOAL_EDGE_MAX_COMPONENT_HEIGHT,
    GOAL_EDGE_WIDTH,
    GOAL_MIN_COMPONENT_AREA,
    GOAL_MIN_PIXELS,
    HSV_GOAL_BLUE_DARK_HI,
    HSV_GOAL_BLUE_DARK_LO,
    HSV_GOAL_BLUE_HI,
    HSV_GOAL_BLUE_LO,
    HSV_GOAL_YELLOW_HI,
    HSV_GOAL_YELLOW_LO,
)


class GoalColorDetectionOperator:
    """Stateless: calcula presencia + centroide X de cada arco en cada frame."""

    @staticmethod
    def _clean_mask(mask: np.ndarray) -> np.ndarray:
        k = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    @staticmethod
    def _large_components_mask(mask: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filtered = np.zeros_like(mask)
        frame_w = mask.shape[1]
        for contour in contours:
            area = cv2.contourArea(contour)
            x, _y, w, _h = cv2.boundingRect(contour)
            touches_side = x <= 0 or (x + w) >= frame_w
            min_area = GOAL_EDGE_MIN_COMPONENT_AREA if touches_side else GOAL_MIN_COMPONENT_AREA
            if area >= min_area:
                cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
        return filtered

    @staticmethod
    def _edge_dark_components_mask(mask: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filtered = np.zeros_like(mask)
        frame_w = mask.shape[1]
        for contour in contours:
            area = cv2.contourArea(contour)
            x, _y, w, h = cv2.boundingRect(contour)
            touches_side = x <= 0 or (x + w) >= frame_w
            if (
                touches_side
                and area >= GOAL_EDGE_MIN_COMPONENT_AREA
                and h <= GOAL_EDGE_MAX_COMPONENT_HEIGHT
            ):
                cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
        return filtered

    @staticmethod
    def _centroid_cx(mask: np.ndarray, pixels: int) -> float | None:
        """Centroide X de la máscara si hay suficientes pixeles, si no None."""
        if pixels < GOAL_MIN_PIXELS:
            return None
        moments = cv2.moments(mask)
        if moments["m00"] <= 0:
            return None
        return float(moments["m10"] / moments["m00"])

    @staticmethod
    def _edge_only_mask(mask: np.ndarray) -> np.ndarray:
        edge = np.zeros_like(mask)
        w = mask.shape[1]
        edge_width = min(GOAL_EDGE_WIDTH, w)
        edge[:, :edge_width] = mask[:, :edge_width]
        edge[:, max(0, w - edge_width):] = mask[:, max(0, w - edge_width):]
        return edge

    def detect(self, frame: np.ndarray) -> GoalsDto:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        yellow_mask = cv2.inRange(hsv, HSV_GOAL_YELLOW_LO, HSV_GOAL_YELLOW_HI)
        blue_mask = cv2.inRange(hsv, HSV_GOAL_BLUE_LO, HSV_GOAL_BLUE_HI)
        blue_dark_edge_mask = self._edge_only_mask(
            cv2.inRange(hsv, HSV_GOAL_BLUE_DARK_LO, HSV_GOAL_BLUE_DARK_HI)
        )
        yellow_mask = self._large_components_mask(self._clean_mask(yellow_mask))
        blue_mask = cv2.bitwise_or(
            self._large_components_mask(self._clean_mask(blue_mask)),
            self._edge_dark_components_mask(self._clean_mask(blue_dark_edge_mask)),
        )

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
