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
    # Bright frame — mean ~230, above CLAHE_BRIGHTNESS_THRESHOLD=220
    bright_frame = np.full((240, 320, 3), 230, dtype=np.uint8)
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


# ── Circularity filter + multi-distance detection tests ────────────────────

def test_rejects_elongated_orange_blob():
    """Blob naranja alargado (tipo teclado) debe ser rechazado por circularidad."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    # Rectangle 100×15 px — circularity ≈ 0.36, well below MIN_CIRCULARITY=0.65
    cv2.rectangle(frame, (110, 113), (210, 128), (0, 100, 255), -1)
    assert detect_ball(frame) is None


def test_detects_small_distant_ball():
    """Pelota pequeña (r=8, simula pelota lejana) debe ser detectada."""
    frame = make_orange_frame(160, 120, r=8)
    result = detect_ball(frame)
    assert result is not None
    cx, cy, radius = result
    assert abs(cx - 160) < 15
    assert abs(cy - 120) < 15


def test_rejects_detection_near_frame_edge():
    """Detección cerca del borde izquierdo/derecho debe ser rechazada (artefacto de dilatación)."""
    # Ball drawn at x=5 — center lands near left edge, rejected by BORDER_REJECT_PX
    frame = make_orange_frame(5, 120, r=15)
    assert detect_ball(frame) is None


def test_detects_ball_near_bottom_edge():
    """Pelota cerca del borde inferior debe detectarse (no es artefacto de dilatación)."""
    frame = make_orange_frame(160, 228, r=10)
    assert detect_ball(frame) is not None


def test_rejects_low_saturation_orange_blob():
    """Blob naranja de baja saturación (S=70) debe ser rechazado — es fondo, no pelota."""
    # HSV (10, 70, 180) — tono cálido pero muy desaturado, como cortina o tela
    frame = cv2.cvtColor(
        np.full((240, 320, 3), [10, 70, 180], dtype=np.uint8), cv2.COLOR_HSV2BGR
    )
    assert detect_ball(frame) is None
