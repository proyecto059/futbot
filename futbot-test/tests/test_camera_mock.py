import threading
import numpy as np
from unittest.mock import patch, MagicMock
from camera import CameraThread

def test_camera_thread_stores_frame():
    fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, fake_frame)

    with patch("camera.cv2.VideoCapture", return_value=mock_cap):
        cam = CameraThread("http://fake-url/stream")
        cam.start()
        import time; time.sleep(0.05)
        frame = cam.get_frame()
        cam.stop()

    assert frame is not None
    assert frame.shape == (240, 320, 3)
