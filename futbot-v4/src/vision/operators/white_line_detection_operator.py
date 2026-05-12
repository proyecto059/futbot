"""Detección de línea blanca (borde del campo) en el frame.

Usado por la lógica AVOID_MAP del FSM: cuando el robot ve mucho blanco abajo,
está por salirse del campo y debe girar. En la Raspberry actual la cámara ve la
línea antes de que llegue al cuarto inferior, así que se analiza el frame entero
para priorizar seguridad sobre detección tardía.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.dto.line_dto import LineDto
from vision.utils.vision_constants import (
    HSV_WHITE_HI,
    HSV_WHITE_LO,
    LINE_DETECT_MIN_RATIO,
    LINE_DETECT_MIN_PIXELS,
)


class WhiteLineDetectionOperator:
    """Stateless: cuenta pixeles blancos + centroide X."""

    def detect(self, frame: np.ndarray) -> LineDto:
        h, _w = frame.shape[:2]
        y0 = h // 3
        roi = frame[y0:, :, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, HSV_WHITE_LO, HSV_WHITE_HI)
        k = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
        pixels = int(cv2.countNonZero(mask))
        ratio = pixels / float(mask.shape[0] * mask.shape[1])

        if pixels < LINE_DETECT_MIN_PIXELS or ratio < LINE_DETECT_MIN_RATIO:
            return LineDto(detected=False, cx=None, pixels=pixels)

        moments = cv2.moments(mask)
        if moments["m00"] <= 0:
            return LineDto(detected=False, cx=None, pixels=pixels)

        cx = float(moments["m10"] / moments["m00"])
        return LineDto(detected=True, cx=cx, pixels=pixels)
