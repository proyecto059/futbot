import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.operators.frame_capture_operator import FrameCaptureOperator
from vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from vision.operators.white_line_detection_operator import WhiteLineDetectionOperator
from vision.utils.vision_constants import CAMERA_HEIGHT, CAMERA_WIDTH


def bgr_from_hsv(hue, sat=240, val=180):
    pixel = np.array([[[hue, sat, val]]], dtype=np.uint8)
    return tuple(int(v) for v in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0])


def test_frame_capture_default_preserves_camera_left_right():
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    frame[:, 0] = (255, 255, 255)

    normalized = FrameCaptureOperator._normalize_frame(frame)

    assert np.all(normalized[:, 0] == (255, 255, 255))
    assert np.count_nonzero(normalized[:, -1]) == 0


def test_camera_defaults_use_sharper_imx219_mode():
    assert CAMERA_WIDTH == 320
    assert CAMERA_HEIGHT == 240


def test_yolo_inference_groups_yoloe_ball_and_robot_classes():
    from vision.operators.yolo_inference_operator import YoloInferenceOperator

    class Backend:
        name = "fake"
        image_size = 320

        def run(self, _frame):
            return np.array(
                [
                    [10, 20, 30, 40, 0.90, 2],
                    [100, 110, 140, 150, 0.80, 7],
                ],
                dtype=np.float32,
            )

    operator = YoloInferenceOperator(Backend())
    operator._run_once(np.zeros((240, 320, 3), dtype=np.uint8), 0.0)

    raw = operator.get_latest_output()
    assert raw["ball_bbox"] is not None
    assert len(raw["robot_bboxes"]) == 1


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


def test_hsv_ball_rejects_large_bottom_clipped_false_positive():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 190)
    cv2.circle(frame, (201, 228), 30, bgr_from_hsv(49, 94, 189), -1)

    detector = HsvBallDetectionOperator()
    detector.hue_center = 58.0
    detector.miss_streak = 1
    detector.last_seen_ts = 0.0
    ball = detector.detect(frame, now_ts=0.5)

    assert ball is None


def test_hsv_ball_prefers_desaturated_tan_ball_over_lower_false_positive():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    cv2.circle(frame, (96, 86), 13, bgr_from_hsv(70, 120, 150), -1)
    cv2.circle(frame, (113, 190), 13, bgr_from_hsv(52, 102, 158), -1)
    frame[190:223, 115:231] = bgr_from_hsv(44, 79, 185)

    detector = HsvBallDetectionOperator()
    detector.hue_center = 62.0
    detector.miss_streak = 1
    detector.last_seen_ts = 0.0
    ball = detector.detect(frame, now_ts=0.5)

    assert ball is not None
    assert 86 <= ball.cx <= 106
    assert 76 <= ball.cy <= 96


def test_hsv_ball_does_not_treat_green_field_as_tan_ball():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)

    detector = HsvBallDetectionOperator()
    detector.hue_center = 62.0
    detector.miss_streak = 1
    detector.last_seen_ts = 0.0
    ball = detector.detect(frame, now_ts=0.5)

    assert ball is None


def test_hsv_ball_detects_desaturated_tan_ball_without_relaxed_state():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    cv2.circle(frame, (96, 86), 13, bgr_from_hsv(70, 120, 150), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 86 <= ball.cx <= 106
    assert 76 <= ball.cy <= 96


def test_hsv_ball_detects_far_small_ball_above_old_top_cutoff():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    cv2.circle(frame, (178, 70), 6, bgr_from_hsv(55, 190, 180), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 170 <= ball.cx <= 186
    assert 64 <= ball.cy <= 76


def test_hsv_ball_rejects_small_left_edge_speck():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    cv2.circle(frame, (26, 82), 6, bgr_from_hsv(55, 190, 180), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is None


def test_hsv_ball_prefers_large_orange_ball_over_tiny_tan_speck():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    cv2.circle(frame, (156, 68), 4, bgr_from_hsv(73, 120, 150), -1)
    cv2.circle(frame, (295, 112), 16, bgr_from_hsv(14, 180, 166), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 285 <= ball.cx <= 305
    assert 102 <= ball.cy <= 122


def test_hsv_ball_rejects_large_goal_blob_touching_top_roi():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    cv2.circle(frame, (99, 81), 45, bgr_from_hsv(6, 180, 150), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is None


def test_hsv_ball_prefers_top_saturated_orange_over_large_floor_blob():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(76, 247, 162)
    cv2.circle(frame, (166, 41), 8, bgr_from_hsv(11, 247, 183), -1)
    cv2.circle(frame, (279, 161), 41, bgr_from_hsv(52, 116, 176), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 156 <= ball.cx <= 176
    assert 33 <= ball.cy <= 49


def test_hsv_ball_uses_real_orange_ball_in_latest_raspi_frame():
    image_path = PROJECT_ROOT / "output/latest_raspi_photo/raw_000.jpg"
    if not image_path.exists():
        pytest.skip("latest Raspberry Pi debug frame is not available")
    frame = cv2.imread(str(image_path))

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 156 <= ball.cx <= 176
    assert 33 <= ball.cy <= 49


def test_hsv_ball_uses_real_orange_ball_in_remote_validation_frame():
    image_path = PROJECT_ROOT / "output/vision_color_fix_validation_remote/raw_000.jpg"
    if not image_path.exists():
        pytest.skip("remote validation debug frame is not available")
    frame = cv2.imread(str(image_path))

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 141 <= ball.cx <= 162
    assert 28 <= ball.cy <= 46


def test_hsv_ball_uses_real_orange_ball_when_late_frame_line_blob_is_large():
    image_path = PROJECT_ROOT / "output/vision_color_fix_validation_final_remote/raw_022.jpg"
    if not image_path.exists():
        pytest.skip("final remote validation debug frame is not available")
    frame = cv2.imread(str(image_path))

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 146 <= ball.cx <= 160
    assert 32 <= ball.cy <= 46


def test_hsv_ball_rejects_post_trial_tan_field_speck_without_orange_ball():
    image_path = PROJECT_ROOT / "output/post_trial_vision_static_remote/raw_002.jpg"
    if not image_path.exists():
        pytest.skip("post-trial static debug frame is not available")
    frame = cv2.imread(str(image_path))

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is None


def test_hsv_ball_rejects_small_false_positive_in_upper_high_res_frame():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 240, 220)
    cv2.circle(frame, (149, 106), 14, bgr_from_hsv(4, 110, 66), -1)
    cv2.circle(frame, (125, 176), 18, bgr_from_hsv(56, 145, 171), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is not None
    assert 105 <= ball.cx <= 145
    assert 155 <= ball.cy <= 195


def test_hsv_ball_rejects_upper_high_res_false_positive_without_real_ball():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 240, 220)
    cv2.circle(frame, (149, 106), 14, bgr_from_hsv(4, 110, 66), -1)

    ball = HsvBallDetectionOperator().detect(frame, now_ts=0.0)

    assert ball is None


def test_goal_detection_rejects_top_yellow_reflection():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[8:61, 319:360] = bgr_from_hsv(26, 72, 149)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.yellow is False
    assert goals.yellow_bbox is None


def test_goal_detection_keeps_top_clipped_dark_blue_and_rejects_yellow_floor_blob():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(76, 247, 162)
    frame[7:42, 215:320] = bgr_from_hsv(120, 241, 71)
    frame[144:187, 238:320] = bgr_from_hsv(26, 118, 191)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[0] >= 210
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 260
    assert goals.yellow is False
    assert goals.yellow_bbox is None


def test_goal_detection_uses_marked_upper_right_blue_goal_over_lower_field_patch():
    image_path = PROJECT_ROOT / "output/post_tracking_gate_static_validation_remote/raw_000.jpg"
    if not image_path.exists():
        pytest.skip("post-tracking static debug frame is not available")
    frame = cv2.imread(str(image_path))

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[0] >= 270
    assert goals.blue_bbox[1] <= 25
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 290
    assert goals.blue_cy is not None
    assert goals.blue_cy <= 45


def test_goal_detection_accepts_upper_blue_goal_near_right_edge():
    image_path = PROJECT_ROOT / "output/vision_color_fix_validation_final2_remote/raw_000.jpg"
    if not image_path.exists():
        pytest.skip("final validation debug frame is not available")
    frame = cv2.imread(str(image_path))

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[1] <= 25
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 250
    assert goals.blue_cy is not None
    assert goals.blue_cy <= 45


def test_goal_detection_accepts_narrow_cleaned_upper_blue_goal_near_right_edge():
    image_path = PROJECT_ROOT / "output/post_marked_goal_fix_static_validation_remote/raw_000.jpg"
    if not image_path.exists():
        pytest.skip("post-marked-goal debug frame is not available")
    frame = cv2.imread(str(image_path))

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[1] <= 25
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 295
    assert goals.blue_cy is not None
    assert goals.blue_cy <= 45


def test_white_line_detects_bottom_white_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[205:225, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is True
    assert 140 <= line.cx <= 180
    assert line.cy is not None
    assert line.cy >= 200


def test_white_line_ignores_top_white_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[20:40, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False


def test_white_line_ignores_visible_middle_white_band_until_close():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[95:115, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False


def test_white_line_reports_but_ignores_lower_far_band_until_close():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[165:185, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False
    assert line.pixels > 0
    assert line.cy is not None
    assert 165 <= line.cy <= 185


def test_white_line_ignores_almost_close_band_until_bottom_zone():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[185:200, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False
    assert line.pixels > 0
    assert line.cy is not None
    assert 185 <= line.cy <= 200


def test_white_line_ignores_cy_around_205_until_danger_zone():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[198:212, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False
    assert line.pixels > 0
    assert line.cy is not None
    assert 198 <= line.cy <= 212


def test_white_line_detects_huge_band_near_wall_before_bottom_zone():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[190:215, 0:320] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is True
    assert line.pixels > 7000
    assert line.cy is not None
    assert 198 <= line.cy <= 210


def test_goal_detection_uses_large_blue_component_not_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[60:130, 60:110] = (255, 0, 0)
    frame[160:170, 270:310] = (255, 0, 0)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert 75 <= goals.blue_cx <= 95
    assert goals.blue_cy is not None
    assert 90 <= goals.blue_cy <= 105
    assert goals.blue_bbox == [60, 60, 50, 70]
    assert goals.blue_pixels > 0


def test_goal_detection_bbox_uses_dominant_blue_component_not_union():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[60:130, 20:80] = (255, 0, 0)
    frame[70:100, 220:260] = (255, 0, 0)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert 45 <= goals.blue_cx <= 55
    assert goals.blue_bbox == [20, 60, 60, 70]


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


def test_goal_detection_rejects_full_width_blue_band_and_keeps_edge_goal():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[51:94, 64:320] = bgr_from_hsv(82, 142, 70)
    frame[52:93, 0:64] = bgr_from_hsv(119, 255, 105)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[0] == 0
    assert goals.blue_bbox[2] <= 70
    assert 20 <= goals.blue_cx <= 45


def test_goal_detection_prefers_primary_blue_goal_over_dark_field_edge():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 245, 180)
    frame[61:71, 0:64] = bgr_from_hsv(81, 246, 120)
    frame[51:80, 300:320] = bgr_from_hsv(118, 234, 85)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[0] >= 295
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 305


def test_goal_detection_keeps_tiny_primary_blue_edge_goal_over_dark_edge_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 245, 180)
    frame[57:82, 0:320] = bgr_from_hsv(81, 246, 120)
    frame[72:77, 311:320] = bgr_from_hsv(118, 234, 85)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is True
    assert goals.blue_bbox is not None
    assert goals.blue_bbox[0] >= 310
    assert goals.blue_cx is not None
    assert goals.blue_cx >= 314


def test_goal_detection_ignores_very_dark_edge_shadow():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[96:121, 256:320] = bgr_from_hsv(87, 177, 90)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is False


def test_goal_detection_rejects_dark_band_filling_edge_width():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[59:69, 0:64] = bgr_from_hsv(81, 246, 120)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is False


def test_goal_detection_rejects_partial_horizontal_dark_edge_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[59:69, 0:42] = bgr_from_hsv(81, 246, 120)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.blue is False


def test_goal_detection_uses_large_yellow_component_not_noise():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[60:130, 210:260] = (0, 255, 255)
    frame[160:170, 10:50] = (0, 255, 255)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.yellow is True
    assert 225 <= goals.yellow_cx <= 245
    assert goals.yellow_cy is not None
    assert 90 <= goals.yellow_cy <= 105
    assert goals.yellow_bbox == [210, 60, 50, 70]
    assert goals.yellow_pixels > 0


def test_goal_detection_rejects_bottom_yellow_floor_reflection():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(82, 255, 195)
    frame[190:234, 115:320] = bgr_from_hsv(44, 79, 185)

    goals = GoalColorDetectionOperator().detect(frame)

    assert goals.yellow is False
    assert goals.yellow_bbox is None
