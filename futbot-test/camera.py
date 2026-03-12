import threading
import cv2
import numpy as np
from config import CAMERA_URL


class CameraThread:
    """
    Reads MJPEG frames in a background thread.
    Callers use get_frame() for the latest frame.
    Never blocks the vision pipeline.
    """

    def __init__(self, url: str = CAMERA_URL):
        self._url = url
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False
        self._thread.join(timeout=2.0)

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _run(self):
        cap = cv2.VideoCapture(self._url)
        while self._running:
            ret, frame = cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
        cap.release()
