import cv2
import numpy as np
from config import TRACKER_TYPE, FRAME_WIDTH, FRAME_HEIGHT


_TRACKER_AVAILABLE: bool | None = None  # lazily detected


def _make_tracker():
    """Returns a tracker instance or None if opencv-contrib is not installed."""
    global _TRACKER_AVAILABLE
    try:
        if TRACKER_TYPE == "MOSSE":
            t = cv2.legacy.TrackerMOSSE_create()
        else:
            t = cv2.legacy.TrackerKCF_create()
        if _TRACKER_AVAILABLE is None:
            _TRACKER_AVAILABLE = True
        return t
    except AttributeError:
        if _TRACKER_AVAILABLE is None:
            _TRACKER_AVAILABLE = False
            print("[tracker] cv2.legacy not available (opencv-contrib required) — tracker disabled, using Kalman only")
        return None


class BallTracker:
    """
    Wraps OpenCV tracker. Used between AI inference frames.
    Call init() when we have a confident detection.
    Call update() on every frame for fast position updates.
    Falls back to no-op if opencv-contrib is not installed.
    """

    def __init__(self):
        self._tracker = None
        self._active = False

    def init(self, frame: np.ndarray, cx: int, cy: int, radius: int):
        t = _make_tracker()
        if t is None:
            return
        r = max(radius, 10)
        x = max(0, cx - r)
        y = max(0, cy - r)
        w = min(2 * r, FRAME_WIDTH - x)
        h = min(2 * r, FRAME_HEIGHT - y)
        self._tracker = t
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
