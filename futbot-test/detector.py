# futbot-test/detector.py
import cv2
import numpy as np
from config import (
    HSV_LOWER, HSV_UPPER, MIN_CONTOUR_AREA, MIN_BALL_RADIUS,
    MORPH_OPEN_SIZE, MORPH_DILATE_SIZE, ROI_SIZE, ROI_PADDING,
    FRAME_WIDTH, FRAME_HEIGHT,
    KALMAN_PROCESS_NOISE, KALMAN_MEASUREMENT_NOISE,
    CLAHE_ENABLED, CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, CLAHE_BRIGHTNESS_THRESHOLD,
    MIN_CIRCULARITY,
    BORDER_REJECT_PX,
    PARTIAL_CIRCULARITY_MIN, PARTIAL_ELLIPSE_RATIO,
    SEED_LOWER, SEED_UPPER, SEED_MIN_PIXELS, SEED_MAX_AREA,
    ACCUM_DECAY, ACCUM_THRESHOLD, ACCUM_MIN_AREA,
    DETECT_ROI_SIZE,
)

_kernel_open = cv2.getStructuringElement(
    cv2.MORPH_ELLIPSE, (MORPH_OPEN_SIZE, MORPH_OPEN_SIZE)
)
_kernel_dilate = cv2.getStructuringElement(
    cv2.MORPH_ELLIPSE, (MORPH_DILATE_SIZE, MORPH_DILATE_SIZE)
)

# CLAHE object — created once at module load, reused every frame
# tileGridSize takes a (int, int) tuple — CLAHE_TILE_GRID is a scalar, expand here
_clahe = cv2.createCLAHE(
    clipLimit=CLAHE_CLIP_LIMIT,
    tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID),
)


def _apply_clahe(frame: np.ndarray) -> np.ndarray:
    """Normalize illumination via CLAHE on L channel of LAB color space."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _preprocess_frame(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Apply CLAHE if needed, blur, convert to HSV. Returns (processed, hsv)."""
    if CLAHE_ENABLED and np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD:
        frame = _apply_clahe(frame)
    blurred = cv2.GaussianBlur(frame, (11, 11), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    return frame, hsv


def _hsv_pass(
    hsv: np.ndarray,
    lower,
    upper,
    min_circ: float,
) -> tuple[int, int, int] | None:
    """Main HSV detection pass with configurable thresholds."""
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _kernel_open)
    mask = cv2.dilate(mask, _kernel_dilate)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_CONTOUR_AREA:
            continue

        # Circularity: reject elongated/irregular blobs (keyboards, clothing, etc.)
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        if circularity < min_circ:
            continue

        (x, y), radius = cv2.minEnclosingCircle(cnt)
        if radius < MIN_BALL_RADIUS:
            continue

        # Reject detections near frame edges (dilation edge artifacts)
        if x < BORDER_REJECT_PX or x > FRAME_WIDTH - BORDER_REJECT_PX:
            continue

        if area > best_area:
            best = (int(x), int(y), int(radius))
            best_area = area

    return best


def _partial_contour_pass(hsv: np.ndarray) -> tuple[int, int, int] | None:
    """Detect partially visible ball (arc/semicircle) via ellipse fitting."""
    mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, _kernel_open)
    mask = cv2.dilate(mask, _kernel_dilate)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < MIN_CONTOUR_AREA:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        # Only candidates with circularity in partial range
        if not (PARTIAL_CIRCULARITY_MIN <= circularity < MIN_CIRCULARITY):
            continue
        if len(cnt) < 5:  # fitEllipse requires ≥5 points
            continue
        try:
            ellipse = cv2.fitEllipse(cnt)
        except cv2.error:
            continue
        (ex, ey), (ma, mi), _ = ellipse
        if ma == 0:
            continue
        # fitEllipse returns axes in arbitrary order — always use min/max
        ratio = min(ma, mi) / max(ma, mi)  # 1.0 = perfect circle
        if ratio < PARTIAL_ELLIPSE_RATIO:
            continue
        radius = int(max(ma, mi) / 2)
        if radius < MIN_BALL_RADIUS:
            continue
        ex, ey = int(ex), int(ey)
        if ex < BORDER_REJECT_PX or ex > FRAME_WIDTH - BORDER_REJECT_PX:
            continue
        return (ex, ey, radius)
    return None


def _seed_pass(hsv: np.ndarray) -> tuple[int, int, int] | None:
    """Detect tiny ball (8-15px) via high-purity color seed."""
    seed_mask = cv2.inRange(hsv, SEED_LOWER, SEED_UPPER)
    # Minimal erosion to clean 1px noise
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    seed_mask = cv2.erode(seed_mask, kernel_small, iterations=1)
    contours, _ = cv2.findContours(seed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < SEED_MIN_PIXELS or area > SEED_MAX_AREA:
            continue
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        x, y = int(x), int(y)
        if x < BORDER_REJECT_PX or x > FRAME_WIDTH - BORDER_REJECT_PX:
            continue
        if area > best_area:
            best = (x, y, max(int(radius), MIN_BALL_RADIUS))
            best_area = area
    return best


def _detect_in_frame(frame: np.ndarray) -> tuple[int, int, int] | None:
    """Core detection logic — runs all passes on the given frame."""
    processed, hsv = _preprocess_frame(frame)
    result = _hsv_pass(hsv, HSV_LOWER, HSV_UPPER, MIN_CIRCULARITY)
    if result:
        return result
    result = _partial_contour_pass(hsv)
    if result:
        return result
    return _seed_pass(hsv)


def detect_ball(
    frame: np.ndarray,
    roi_center: tuple[int, int] | None = None,
) -> tuple[int, int, int] | None:
    """
    Detect orange ball using multilayer HSV pipeline.

    roi_center: (cx, cy) of last known position. If provided, searches ROI first,
    falling back to full frame if ROI search fails.
    Returns (cx, cy, radius) or None if not found.
    ~1-2ms on RPi3.
    """
    if roi_center is not None:
        rx, ry = roi_center
        half = DETECT_ROI_SIZE // 2
        x1 = max(0, rx - half)
        y1 = max(0, ry - half)
        x2 = min(FRAME_WIDTH, rx + half)
        y2 = min(FRAME_HEIGHT, ry + half)
        roi_frame = frame[y1:y2, x1:x2]
        result = _detect_in_frame(roi_frame)
        if result is not None:
            rx_det, ry_det, rad = result
            return (rx_det + x1, ry_det + y1, rad)
    return _detect_in_frame(frame)


class BallAccumulator:
    """
    Accumulates temporal evidence for very small balls (4-5 px).
    Each frame contributes to a heat map; decay forgets old observations.
    """

    def __init__(self):
        self._acc = np.zeros((FRAME_HEIGHT, FRAME_WIDTH), dtype=np.float32)

    def update(self, seed_mask: np.ndarray) -> tuple[int, int, int] | None:
        """
        seed_mask: binary uint8 (output of cv2.inRange with SEED_LOWER/UPPER).
        Returns (cx, cy, radius) of hottest blob, or None.
        """
        self._acc *= ACCUM_DECAY
        self._acc += (seed_mask > 0).astype(np.float32)
        hot = (self._acc > ACCUM_THRESHOLD).astype(np.uint8)
        if not hot.any():
            return None
        contours, _ = cv2.findContours(hot, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_val = 0.0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < ACCUM_MIN_AREA:
                continue
            (x, y), radius = cv2.minEnclosingCircle(cnt)
            x, y = int(x), int(y)
            if x < BORDER_REJECT_PX or x > FRAME_WIDTH - BORDER_REJECT_PX:
                continue
            val = float(np.max(self._acc[max(0, y - 3):y + 4, max(0, x - 3):x + 4]))
            if val > best_val:
                best = (x, y, max(int(radius), MIN_BALL_RADIUS))
                best_val = val
        return best

    def reset(self):
        self._acc[:] = 0


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
            # Initialize both statePost (used by predict) and statePre
            initial = np.array([[x], [y], [0], [0]], dtype=np.float32)
            self._kf.statePost = initial.copy()
            self._kf.statePre = initial.copy()
            self._kf.errorCovPost = np.eye(4, dtype=np.float32)
            self._initialized = True
        self._kf.predict()  # advance state estimate before correction
        corrected = self._kf.correct(measurement)
        return float(corrected[0, 0]), float(corrected[1, 0])

    def predict(self) -> tuple[float, float]:
        if not self._initialized:
            return 0.0, 0.0
        predicted = self._kf.predict()
        return float(predicted[0, 0]), float(predicted[1, 0])

    def reset(self):
        """Discard current state — next update() re-initializes from scratch."""
        self._initialized = False
