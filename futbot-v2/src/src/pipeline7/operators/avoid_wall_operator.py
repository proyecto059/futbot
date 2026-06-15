import cv2
import numpy as np
import time


STOP_DUR_MS = 100


class AvoidWallOperator:
    """Deteccion de muros negros por vision y maniobra de evasion en 2 fases."""

    def __init__(
        self,
        black_threshold: int = 30,
        coverage_ratio: float = 0.35,
        reverse_duration: float = 0.5,
        turn_duration: float = 1.0,
    ) -> None:
        self.black_threshold = black_threshold
        self.coverage_ratio = coverage_ratio
        self.reverse_duration = reverse_duration
        self.turn_duration = turn_duration
        self._escaping = False
        self._escape_start_ts = 0.0

    def check_and_avoid(self, frame):
        now = time.monotonic()

        if self._escaping:
            elapsed = now - self._escape_start_ts
            if elapsed < self.reverse_duration:
                return -150.0, -150.0, STOP_DUR_MS
            elif elapsed < (self.reverse_duration + self.turn_duration):
                return 50.0, -50.0, STOP_DUR_MS
            else:
                self._escaping = False

        if frame is None:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        roi = gray[0 : int(h * 0.25), int(w * 0.2) : int(w * 0.8)]

        black_mask = cv2.inRange(roi, 0, self.black_threshold)

        total_pixels = roi.shape[0] * roi.shape[1]
        black_pixels = np.sum(black_mask > 0)
        ratio = black_pixels / total_pixels


        if ratio > self.coverage_ratio:
            self._escaping = True
            self._escape_start_ts = now
            return -150.0, -100.0, STOP_DUR_MS

        return None
