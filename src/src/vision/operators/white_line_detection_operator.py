"""Detección de línea blanca (borde del campo) en la ROI inferior del frame.

Usado por la lógica AVOID_MAP del FSM: cuando el robot ve mucho blanco abajo,
está por salirse del campo y debe girar. Se limita a la cuarta parte inferior
del frame para ignorar líneas lejanas / techo.
"""

from __future__ import annotations

import cv2
import numpy as np

from vision.dto.line_dto import LineDto
from vision.utils.vision_constants import (
    HSV_WHITE_HI,
    HSV_WHITE_LO,
    LINE_DETECT_MIN_PIXELS,
)


class WhiteLineDetectionOperator:
    """Stateless: cuenta pixeles blancos en la ROI inferior + centroide X."""

    def detect(self, frame: np.ndarray) -> LineDto:
        h, _w = frame.shape[:2]
        # ROI = cuarto inferior del frame (lo más cercano al robot)
        roi = frame[3 * h // 4 :, :, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, HSV_WHITE_LO, HSV_WHITE_HI)
        pixels = int(cv2.countNonZero(mask))

        if pixels < LINE_DETECT_MIN_PIXELS:
            return LineDto(detected=False, cx=None, pixels=pixels)

        moments = cv2.moments(mask)
        if moments["m00"] <= 0:
            return LineDto(detected=False, cx=None, pixels=pixels)

        cx = float(moments["m10"] / moments["m00"])
        return LineDto(detected=True, cx=cx, pixels=pixels)