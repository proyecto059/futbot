import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.operators.frame_capture_operator import FrameCaptureOperator
from vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from vision.operators.white_line_detection_operator import WhiteLineDetectionOperator


def bgr_from_hsv(hue, sat=240, val=180):
    pixel = np.array([[[hue, sat, val]]], dtype=np.uint8)
    return tuple(int(v) for v in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0])


def test_frame_capture_default_preserves_camera_left_right():
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    frame[:, 0] = (255, 255, 255)

    normalized = FrameCaptureOperator._normalize_frame(frame)

    assert np.all(normalized[:, 0] == (255, 255, 255))
    assert np.count_nonzero(normalized[:, -1]) == 0


def test_frame_capture_can_flip_when_requested():
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    frame[:, 0] = (255, 255, 255)

    normalized = FrameCaptureOperator._normalize_frame(frame, flip_horizontal=True)

    assert np.all(normalized[:, -1] == (255, 255, 255))
    assert np.count_nonzero(normalized[:, 0]) == 0


def test_hsv_ball_ignores_goal_blob_and_uses_lower_orange_ball():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    cv2.circle(frame, (170, 50), 43, bgr_from_hsv(6, 180, 150), -1)
    cv2.circle(frame, (53, 97), 8, bgr_from_hsv(53, 245, 174), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 45 <= ball.cx <= 61
    assert 89 <= ball.cy <= 105


def test_hsv_ball_accepts_lighting_shifted_orange_ball():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    cv2.circle(frame, (170, 56), 42, bgr_from_hsv(6, 180, 150), -1)
    cv2.circle(frame, (52, 105), 8, bgr_from_hsv(61, 245, 174), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 44 <= ball.cx <= 60
    assert 97 <= ball.cy <= 113


def test_hsv_ball_rejects_large_goal_blob_touching_top_roi():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    cv2.circle(frame, (99, 81), 45, bgr_from_hsv(6, 180, 150), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is None


def test_white_line_detects_bottom_white_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[205:225, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is True
    assert 140 <= line.cx <= 180


def test_white_line_ignores_top_white_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[20:40, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False


def test_white_line_detects_visible_middle_white_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[95:115, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is True
    assert 140 <= line.cx <= 180


def test_goal_detection_uses_large_blue_component_not_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[60:130, 60:110] = (255, 0, 0)
    frame[160:170, 270:310] = (255, 0, 0)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert 75 <= goals.blue_cx <= 95


def test_goal_detection_keeps_blue_goal_clipped_by_left_edge():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[76:94, 0:12] = (255, 0, 0)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert 0 <= goals.blue_cx <= 12


def test_goal_detection_keeps_dark_blue_goal_clipped_by_left_edge():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[76:94, 0:12] = bgr_from_hsv(81, 164, 90)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert 0 <= goals.blue_cx <= 12


def test_goal_detection_ignores_very_dark_edge_shadow():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[96:121, 256:320] = bgr_from_hsv(87, 177, 90)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is False


def test_goal_detection_uses_large_yellow_component_not_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[60:130, 210:260] = (0, 255, 255)
    frame[160:170, 10:50] = (0, 255, 255)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.yellow is True
    assert 225 <= goals.yellow_cx <= 245
