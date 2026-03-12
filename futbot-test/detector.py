# futbot-test/detector.py
import cv2
import numpy as np
from config import (
    HSV_LOWER, HSV_UPPER, MIN_CONTOUR_AREA, MIN_BALL_RADIUS,
    MORPH_OPEN_SIZE, MORPH_DILATE_SIZE, ROI_SIZE, ROI_PADDING,
    FRAME_WIDTH, FRAME_HEIGHT,
    KALMAN_PROCESS_NOISE, KALMAN_MEASUREMENT_NOISE,
)

_kernel_open = cv2.getStructuringElement(
    cv2.MORPH_ELLIPSE, (MORPH_OPEN_SIZE, MORPH_OPEN_SIZE)
)
_kernel_dilate = cv2.getStructuringElement(
    cv2.MORPH_ELLIPSE, (MORPH_DILATE_SIZE, MORPH_DILATE_SIZE)
)


def detect_ball(frame: np.ndarray) -> tuple[int, int, int] | None:
    """
    Detect orange ball using HSV thresholding.
    Returns (cx, cy, radius) or None if not found.
    ~1-2ms on RPi3.
    """
    blurred = cv2.GaussianBlur(frame, (11, 11), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _kernel_open)
    mask = cv2.dilate(mask, _kernel_dilate)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = MIN_CONTOUR_AREA

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < best_area:
            continue
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        if radius < MIN_BALL_RADIUS:
            continue
        best = (int(x), int(y), int(radius))
        best_area = area

    return best


def extract_roi(
    frame: np.ndarray,
    cx: int,
    cy: int,
    radius: int,
) -> np.ndarray:
    """
    Extract ROI around ball center, clamped to frame boundaries.
    Returns ROI resized to (ROI_SIZE, ROI_SIZE, 3). No extra copy.
    """
    half = radius + ROI_PADDING
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(FRAME_WIDTH, cx + half)
    y2 = min(FRAME_HEIGHT, cy + half)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        roi = frame  # fallback: full frame
    return cv2.resize(roi, (ROI_SIZE, ROI_SIZE))


class BallKalman:
    """
    2D Kalman filter tracking (x, y, vx, vy).
    Uses cv2.KalmanFilter for speed on RPi3.
    """

    def __init__(self):
        self._kf = cv2.KalmanFilter(4, 2)
        self._kf.measurementMatrix = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0]], np.float32
        )
        self._kf.transitionMatrix = np.array(
            [[1, 0, 1, 0],
             [0, 1, 0, 1],
             [0, 0, 1, 0],
             [0, 0, 0, 1]], np.float32
        )
        self._kf.processNoiseCov = np.eye(4, dtype=np.float32) * KALMAN_PROCESS_NOISE
        self._kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * KALMAN_MEASUREMENT_NOISE
        self._initialized = False

    def update(self, x: float, y: float) -> tuple[float, float]:
        measurement = np.array([[x], [y]], dtype=np.float32)
        if not self._initialized:
            self._kf.statePre = np.array([[x], [y], [0], [0]], dtype=np.float32)
            self._initialized = True
        corrected = self._kf.correct(measurement)
        return float(corrected[0, 0]), float(corrected[1, 0])

    def predict(self) -> tuple[float, float]:
        if not self._initialized:
            return 0.0, 0.0
        predicted = self._kf.predict()
        return float(predicted[0, 0]), float(predicted[1, 0])
