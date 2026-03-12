import cv2
import numpy as np
from config import TRACKER_TYPE, FRAME_WIDTH, FRAME_HEIGHT


def _make_tracker():
    if TRACKER_TYPE == "MOSSE":
        return cv2.legacy.TrackerMOSSE_create()
    return cv2.legacy.TrackerKCF_create()


class BallTracker:
    """
    Wraps OpenCV tracker. Used between AI inference frames.
    Call init() when we have a confident detection.
    Call update() on every frame for fast position updates.
    """

    def __init__(self):
        self._tracker = None
        self._active = False

    def init(self, frame: np.ndarray, cx: int, cy: int, radius: int):
        r = max(radius, 10)
        x = max(0, cx - r)
        y = max(0, cy - r)
        w = min(2 * r, FRAME_WIDTH - x)
        h = min(2 * r, FRAME_HEIGHT - y)
        self._tracker = _make_tracker()
        self._tracker.init(frame, (x, y, w, h))
        self._active = True

    def update(self, frame: np.ndarray) -> tuple[int, int] | None:
        """Returns (cx, cy) or None if tracking lost."""
        if not self._active or self._tracker is None:
            return None
        ok, bbox = self._tracker.update(frame)
        if not ok:
            self._active = False
            return None
        x, y, w, h = [int(v) for v in bbox]
        return x + w // 2, y + h // 2

    def reset(self):
        self._active = False
        self._tracker = None
