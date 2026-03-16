# futbot-test/tests/test_detector.py
import numpy as np
import cv2
import pytest
from detector import detect_ball, extract_roi
from unittest.mock import patch
import detector

def make_orange_frame(cx, cy, r=15):
    """Create a synthetic frame with an orange circle."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # Draw orange circle (HSV orange = BGR roughly (0, 100, 255))
    cv2.circle(frame, (cx, cy), r, (0, 100, 255), -1)
    return frame

def test_detects_orange_ball():
    frame = make_orange_frame(160, 120, r=20)
    result = detect_ball(frame)
    assert result is not None
    x, y, radius = result
    assert abs(x - 160) < 10
    assert abs(y - 120) < 10
    assert radius > 5

def test_returns_none_when_no_ball():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    result = detect_ball(frame)
    assert result is None

def test_extract_roi_returns_correct_size():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    roi = extract_roi(frame, cx=160, cy=120, radius=20)
    assert roi.shape == (96, 96, 3)

def test_extract_roi_clamps_to_frame_boundaries():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # Ball near edge — should not raise
    roi = extract_roi(frame, cx=5, cy=5, radius=20)
    assert roi.shape == (96, 96, 3)

# Kalman tests — add after implementing BallKalman
from detector import BallKalman

def test_kalman_predicts_stationary_ball():
    kf = BallKalman()
    kf.update(100, 100)
    kf.update(100, 100)
    px, py = kf.predict()
    assert abs(px - 100) < 5
    assert abs(py - 100) < 5

def test_kalman_smooths_noisy_measurements():
    kf = BallKalman()
    for _ in range(10):
        kf.update(100, 100)
    # after 10 consistent updates, prediction should stay near truth
    px, py = kf.predict()
    assert abs(px - 100) < 15
    assert abs(py - 100) < 15


# ── CLAHE preprocessing tests ──────────────────────────────────────────────

def test_apply_clahe_increases_brightness_of_dark_frame():
    """_apply_clahe should raise mean brightness of a dark frame.

    Uses BGR (0, 50, 100) — channels differ so the LAB L histogram is
    non-flat and CLAHE can actually redistribute it. A fully gray frame
    (e.g. (30,30,30)) also works, but a uniform single-channel frame would not.
    """
    from detector import _apply_clahe
    # Dark orange-tinted frame: mean ~50, non-flat LAB L histogram
    dark_frame = np.full((240, 320, 3), (0, 50, 100), dtype=np.uint8)
    mean_before = float(np.mean(dark_frame))
    result = _apply_clahe(dark_frame)
    mean_after = float(np.mean(result))
    assert mean_after > mean_before


def test_detect_ball_applies_clahe_when_frame_is_dark():
    """detect_ball should call _apply_clahe when mean(frame) < threshold."""
    # Solid dark frame — mean ~30, well below CLAHE_BRIGHTNESS_THRESHOLD=130
    dark_frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
        detector.detect_ball(dark_frame)
        mock_clahe.assert_called_once()


def test_detect_ball_skips_clahe_when_frame_is_bright():
    """detect_ball should NOT call _apply_clahe when mean(frame) >= threshold."""
    # Bright frame — mean ~200, above CLAHE_BRIGHTNESS_THRESHOLD=130
    bright_frame = np.full((240, 320, 3), 200, dtype=np.uint8)
    with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
        detector.detect_ball(bright_frame)
        mock_clahe.assert_not_called()


def test_detect_ball_respects_clahe_enabled_flag():
    """When CLAHE_ENABLED=False, _apply_clahe must never be called."""
    dark_frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    with patch.object(detector, 'CLAHE_ENABLED', False):
        with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
            detector.detect_ball(dark_frame)
            mock_clahe.assert_not_called()
