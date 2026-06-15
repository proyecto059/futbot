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
                and w < int(GOAL_EDGE_WIDTH * 0.85)
                and w <= max(20, h * 2)
            ):
                cv2.drawContours(filtered, [contour], -1, 255, thickness=cv2.FILLED)
        return filtered

    @staticmethod
    def _edge_primary_components_mask(mask: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filtered = np.zeros_like(mask)
        frame_w = mask.shape[1]
        for contour in contours:
            area = cv2.contourArea(contour)
            x, _y, w, h = cv2.boundingRect(contour)
            touches_side = x <= 0 or (x + w) >= frame_w
            if touches_side and area >= 12 and h <= GOAL_EDGE_MAX_COMPONENT_HEIGHT:
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
    def _centroid_cy(mask: np.ndarray, pixels: int) -> float | None:
        if pixels < GOAL_MIN_PIXELS:
            return None
        moments = cv2.moments(mask)
        if moments["m00"] <= 0:
            return None
        return float(moments["m01"] / moments["m00"])

    @staticmethod
    def _bbox(mask: np.ndarray, pixels: int) -> list[int] | None:
        if pixels < GOAL_MIN_PIXELS:
            return None
        points = cv2.findNonZero(mask)
        if points is None:
            return None
        x, y, w, h = cv2.boundingRect(points)
        return [int(x), int(y), int(w), int(h)]

    @staticmethod
    def _dominant_component(
        mask: np.ndarray,
        min_pixels: int = GOAL_MIN_PIXELS,
        allow_top_clipped: bool = False,
    ) -> tuple[int, float | None, float | None, list[int] | None]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0, None, None, None
        frame_h = mask.shape[0]
        min_cy = float(frame_h) * 0.15
        max_cy = float(frame_h) * 0.80
        candidates = []
        for contour in contours:
            component = np.zeros_like(mask)
            cv2.drawContours(component, [contour], -1, 255, thickness=cv2.FILLED)
            pixels = int(cv2.countNonZero(component))
            if pixels < min_pixels:
                continue
            moments = cv2.moments(component)
            if moments["m00"] <= 0:
                continue
            cy = float(moments["m01"] / moments["m00"])
            x, y, w, h = cv2.boundingRect(contour)
            edge_margin = max(3, int(float(mask.shape[1]) * 0.012))
            touches_side = x <= edge_margin or (x + w) >= mask.shape[1] - edge_margin
            top_clipped_goal = (
                allow_top_clipped
                and touches_side
                and y <= max(8, int(float(frame_h) * 0.12))
                and pixels >= GOAL_MIN_COMPONENT_AREA
                and w >= 28
                and h >= 18
            )
            if (cy < min_cy and not top_clipped_goal) or cy > max_cy:
                continue
            candidates.append((pixels, contour, moments, cy))
        if not candidates:
            return 0, None, None, None
        pixels, contour, moments, cy = max(candidates, key=lambda item: item[0])
        x, y, w, h = cv2.boundingRect(contour)
        return (
            pixels,
            float(moments["m10"] / moments["m00"]),
            cy,
            [int(x), int(y), int(w), int(h)],
        )

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
        clean_primary_blue_mask = self._clean_mask(blue_mask)
        primary_blue_mask = self._large_components_mask(clean_primary_blue_mask)
        primary_edge_blue_mask = self._edge_primary_components_mask(blue_mask)
        dark_edge_blue_mask = self._edge_dark_components_mask(
            self._clean_mask(blue_dark_edge_mask)
        )

        yellow_pixels, yellow_cx, yellow_cy, yellow_bbox = self._dominant_component(yellow_mask)
        blue_pixels, blue_cx, blue_cy, blue_bbox = self._dominant_component(
            primary_blue_mask,
            allow_top_clipped=True,
        )
        blue_detected = blue_pixels >= GOAL_MIN_PIXELS
        if blue_pixels < GOAL_MIN_PIXELS:
            blue_pixels, blue_cx, blue_cy, blue_bbox = self._dominant_component(
                primary_edge_blue_mask,
                min_pixels=20,
            )
            blue_detected = blue_pixels >= 20
        if not blue_detected:
            blue_pixels, blue_cx, blue_cy, blue_bbox = self._dominant_component(
                dark_edge_blue_mask
            )
            blue_detected = blue_pixels >= GOAL_MIN_PIXELS

        return GoalsDto(
            yellow=yellow_pixels >= GOAL_MIN_PIXELS,
            yellow_cx=yellow_cx,
            yellow_cy=yellow_cy,
            yellow_bbox=yellow_bbox,
            yellow_pixels=yellow_pixels,
            blue=blue_detected,
            blue_cx=blue_cx,
            blue_cy=blue_cy,
            blue_bbox=blue_bbox,
            blue_pixels=blue_pixels,
        )
