import threading
import cv2
import numpy as np
from config import CAMERA_URL, USE_LOCAL_CAM, LOCAL_CAM_ID, FRAME_WIDTH, FRAME_HEIGHT


class CameraThread:
    """
    Reads MJPEG frames in a background thread.
    Callers use get_frame() for the latest frame.
    Never blocks the vision pipeline.

    Source selection (set env vars before running):
      USE_LOCAL_CAM=true   → local webcam (LOCAL_CAM_ID, default 0)
      USE_LOCAL_CAM=false  → MJPEG stream at CAMERA_URL (default)
    """

    def __init__(self):
        self._source = LOCAL_CAM_ID if USE_LOCAL_CAM else CAMERA_URL
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._new_frame = threading.Event()
        self._running = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        label = f"local cam #{LOCAL_CAM_ID}" if USE_LOCAL_CAM else CAMERA_URL
        print(f"[camera] source: {label}")
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False
        self._new_frame.set()  # unblock any waiting caller
        self._thread.join(timeout=2.0)

    def wait_for_frame(self, timeout: float = 1.0) -> bool:
        """Block until a new frame arrives. Returns False on timeout."""
        got = self._new_frame.wait(timeout=timeout)
        self._new_frame.clear()
        return got

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _run(self):
        cap = cv2.VideoCapture(self._source)
        while self._running:
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                with self._lock:
                    self._frame = frame
                self._new_frame.set()
        cap.release()
