import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chase.visual_servo_controller import (
    VisualServoController,
    BallPredictor,
    effective_goal_radius,
    Kalman1D,
    TurnHysteresis,
    is_confirmed_line,
    is_confirmed_ball_streak,
    is_trackable_ball,
    should_allow_initial_track,
    should_allow_push_commit,
    should_accept_goal_edge_ball,
    should_attack_through_line,
    should_commit_push,
    should_hold_without_ball_near_line,
    should_hold_track_on_miss,
    should_push_ball,
)


def build_controller(**overrides):
    defaults = dict(
        center_x=160.0,
        f_eff=5500.0,
        r_desired=60.0,
        kp_theta=60.0,
        kp_dist=70.0,
        v_min=65.0,
        v_max=110.0,
        base_forward=65.0,
        theta_deadband=0.06,
        turn_ratio_max=0.55,
    )
    defaults.update(overrides)
    return VisualServoController(**defaults)


# --- Legacy controller tests (must keep passing) ---


def test_forward_command_uses_negative_vr_for_centered_ball():
    controller = build_controller()
    v_left, v_right = controller.compute(cx=160.0, r=30.0, dt=0.01)
    assert v_left > 0
    assert v_right < 0


def test_vr_remains_negative_with_large_angle_and_close_ball():
    controller = build_controller()
    v_left, v_right = controller.compute(cx=0.0, r=120.0, dt=0.01)
    assert v_right <= 0


def test_ball_left_turns_left_while_advancing():
    controller = build_controller()
    v_left, v_right = controller.compute(cx=40.0, r=40.0, dt=0.01)
    assert v_left > 0
    assert v_right < 0
    assert v_left < -v_right


def test_ball_right_turns_right_while_advancing():
    controller = build_controller()
    v_left, v_right = controller.compute(cx=280.0, r=40.0, dt=0.01)
    assert v_left > 0
    assert v_right < 0
    assert v_left > -v_right


def test_forward_speed_reduces_when_ball_is_far_off_center():
    controller = build_controller()

    v_left_center, v_right_center = controller.compute(cx=160.0, r=40.0, dt=0.01)
    v_center = (v_left_center - v_right_center) * 0.5

    v_left_side, v_right_side = controller.compute(cx=295.0, r=40.0, dt=0.01)
    v_side = (v_left_side - v_right_side) * 0.5

    assert v_side < v_center


def test_turn_strength_is_stronger_for_larger_theta_error():
    controller = build_controller()

    v_left_small, v_right_small = controller.compute(cx=180.0, r=40.0, dt=0.01)
    w_small = (v_left_small + v_right_small) * 0.5

    v_left_big, v_right_big = controller.compute(cx=295.0, r=40.0, dt=0.01)
    w_big = (v_left_big + v_right_big) * 0.5

    assert abs(w_big) > abs(w_small)


def test_signed_wheels_decompose_forward_and_turn_right():
    v_left = 100.0
    v_right = -60.0

    forward = (v_left - v_right) * 0.5
    turn = (v_left + v_right) * 0.5

    assert forward == 80.0
    assert turn == 20.0


def test_controller_turns_right_for_ball_on_right_with_forward_motion():
    controller = build_controller()

    v_left, v_right = controller.compute(cx=220.0, r=42.0, dt=0.05)
    forward = (v_left - v_right) * 0.5
    turn = (v_left + v_right) * 0.5

    assert forward > 0.0
    assert turn > 0.0


def test_turn_to_forward_ratio_increases_for_large_theta_error():
    controller = build_controller()

    v_left_small, v_right_small = controller.compute(cx=180.0, r=40.0, dt=0.01)
    v_small = (v_left_small - v_right_small) * 0.5
    w_small = abs((v_left_small + v_right_small) * 0.5)

    v_left_big, v_right_big = controller.compute(cx=295.0, r=40.0, dt=0.01)
    v_big = (v_left_big - v_right_big) * 0.5
    w_big = abs((v_left_big + v_right_big) * 0.5)

    assert (w_big / v_big) > (w_small / v_small)


def test_lateral_tracking_keeps_min_forward_on_both_wheels():
    controller = build_controller()

    v_left, v_right = controller.compute(cx=274.0, r=56.0, dt=0.01)

    assert v_left >= 12.0
    assert -v_right >= 12.0


# --- Proximity governor tests ---


def test_proximity_governor_reduces_turn_near_ball():
    controller = build_controller(
        proximity_turn_scale=0.45,
        proximity_r_threshold=50.0,
    )

    vL_far, vR_far = controller.compute(cx=40.0, r=20.0, dt=0.01)
    w_far = abs((vL_far + vR_far) * 0.5)

    vL_near, vR_near = controller.compute(cx=40.0, r=80.0, dt=0.01)
    w_near = abs((vL_near + vR_near) * 0.5)

    assert w_near < w_far


def test_proximity_governor_no_effect_when_ball_far():
    controller = build_controller(
        proximity_turn_scale=0.45,
        proximity_r_threshold=50.0,
    )

    vL_base, vR_base = build_controller().compute(cx=40.0, r=20.0, dt=0.01)
    w_base = abs((vL_base + vR_base) * 0.5)

    vL_gov, vR_gov = controller.compute(cx=40.0, r=20.0, dt=0.01)
    w_gov = abs((vL_gov + vR_gov) * 0.5)

    assert abs(w_gov - w_base) < 1.0


def test_proximity_does_not_break_forward_sign():
    controller = build_controller(
        proximity_turn_scale=0.45,
        proximity_r_threshold=50.0,
    )
    vL, vR = controller.compute(cx=40.0, r=90.0, dt=0.01)
    assert vL > 0
    assert vR < 0


# --- BallPredictor tests ---


def test_should_not_push_when_ball_is_close_but_not_aligned():
    assert should_push_ball(radius=70.0, theta=0.13, streak=3) is False


def test_should_not_push_before_ball_is_really_close():
    assert should_push_ball(radius=51.0, theta=0.02, streak=3) is False


def test_should_push_when_ball_is_close_and_aligned():
    assert should_push_ball(radius=70.0, theta=0.02, streak=3) is True


def test_trackable_ball_accepts_small_valid_hsv_ball():
    ball = {"source": "hsv", "r": 9.5}

    assert is_trackable_ball(ball) is True


def test_trackable_ball_rejects_tiny_or_non_hsv_ball():
    assert is_trackable_ball({"source": "hsv", "r": 4.0}) is False
    assert is_trackable_ball({"source": "yolo", "r": 14.0}) is False
    assert is_trackable_ball(None) is False


def test_ball_streak_requires_multiple_frames_for_confirmation():
    assert is_confirmed_ball_streak(1, min_frames=3) is False
    assert is_confirmed_ball_streak(2, min_frames=3) is False
    assert is_confirmed_ball_streak(3, min_frames=3) is True


def test_initial_track_rejects_sudden_large_far_false_positive():
    ball = {"source": "hsv", "r": 66.0}

    assert should_allow_initial_track(ball, streak=5, min_streak=3, max_initial_radius=45.0) is False


def test_initial_track_accepts_consistent_plausible_ball():
    ball = {"source": "hsv", "r": 18.0}

    assert should_allow_initial_track(ball, streak=3, min_streak=3, max_initial_radius=45.0) is True


def test_push_commit_requires_stronger_confirmation():
    assert should_allow_push_commit(streak=3, min_streak=5) is False
    assert should_allow_push_commit(streak=5, min_streak=5) is True


def test_goal_edge_ball_accepts_small_hsv_ball_aligned_with_goal():
    ball = {"source": "hsv", "cx": 290, "r": 5.6}

    assert should_accept_goal_edge_ball(ball, goal_cx=246.0) is True


def test_goal_edge_ball_rejects_small_noise_without_goal_or_alignment():
    ball = {"source": "hsv", "cx": 80, "r": 5.6}

    assert should_accept_goal_edge_ball(ball, goal_cx=None) is False
    assert should_accept_goal_edge_ball(ball, goal_cx=246.0) is False
    assert should_accept_goal_edge_ball({"source": "yolo", "cx": 246, "r": 5.6}, goal_cx=246.0) is False


def test_hold_track_on_short_ball_miss():
    assert should_hold_track_on_miss(1, max_miss_frames=8) is True
    assert should_hold_track_on_miss(8, max_miss_frames=8) is True


def test_stop_holding_track_after_long_ball_miss():
    assert should_hold_track_on_miss(9, max_miss_frames=8) is False


def test_line_is_confirmed_only_after_required_streak():
    assert is_confirmed_line(1, min_streak=2) is False
    assert is_confirmed_line(2, min_streak=2) is True


def test_attack_through_line_when_trackable_ball_is_aligned_with_goal():
    ball = {"source": "hsv", "cx": 197, "r": 16.0}

    assert should_attack_through_line(ball, goal_cx=194, line_detected=True) is True


def test_do_not_attack_through_line_without_goal_or_alignment():
    ball = {"source": "hsv", "cx": 80, "r": 16.0}

    assert should_attack_through_line(ball, goal_cx=None, line_detected=True) is False
    assert should_attack_through_line(ball, goal_cx=240, line_detected=True) is False
    assert should_attack_through_line(ball, goal_cx=80, line_detected=False) is False


def test_line_detection_without_ball_allows_avoidance_motion():
    assert should_hold_without_ball_near_line(False, line_detected=True, line_cooldown=0) is False
    assert should_hold_without_ball_near_line(True, line_detected=True, line_cooldown=10) is False
    assert should_hold_without_ball_near_line(False, line_detected=False, line_cooldown=0) is False


def test_line_cooldown_allows_safe_search_motion():
    assert should_hold_without_ball_near_line(False, line_detected=False, line_cooldown=10) is False


def test_effective_goal_radius_uses_raw_radius_when_smoothing_lags():
    assert effective_goal_radius(raw_radius=46.0, filtered_radius=43.1) == 46.0


def test_commit_push_stays_active_inside_window_only():
    assert should_commit_push(10.2, push_until=10.8) is True
    assert should_commit_push(10.8, push_until=10.8) is False


def test_kalman_first_update_uses_measurement_without_zero_bias():
    k = Kalman1D(q=2.6, r=1.0)

    assert k.update(157.0) == 157.0


def test_kalman_second_update_smooths_from_first_measurement():
    k = Kalman1D(q=2.6, r=1.0)
    k.update(157.0)

    updated = k.update(177.0)

    assert 157.0 < updated < 177.0


def test_predictor_returns_measurement_after_update():
    p = BallPredictor()
    cx, r = p.update(100.0, 30.0, 0.0)
    assert cx == 100.0
    assert r == 30.0


def test_predictor_extrapolates_ahead():
    p = BallPredictor(max_horizon_s=0.2, blend=1.0)
    t0 = 0.0
    p.update(100.0, 30.0, t0)
    p.update(120.0, 30.0, t0 + 0.1)

    cx_pred, r_pred = p.predict(0.1)
    assert cx_pred > 120.0


def test_predictor_clamps_horizon():
    p = BallPredictor(max_horizon_s=0.1, blend=1.0)
    p.update(100.0, 30.0, 0.0)
    p.update(150.0, 30.0, 0.1)

    cx_short, _ = p.predict(0.05)
    cx_long, _ = p.predict(5.0)

    assert cx_long > cx_short


def test_predictor_velocity_smoothing():
    p = BallPredictor(max_horizon_s=0.2, blend=0.5)
    p.update(100.0, 30.0, 0.0)
    p.update(120.0, 30.0, 0.1)
    p.update(100.0, 30.0, 0.2)

    cx_pred, _ = p.predict(0.1)
    assert 94.0 < cx_pred < 106.0


def test_predictor_uninitialized_predicts_identity():
    p = BallPredictor()
    cx, r = p.predict(0.1)
    assert cx == 0.0
    assert r == 0.0


# --- TurnHysteresis tests ---


def test_hysteresis_passes_through_when_no_prior_sign():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=3)
    result = h.filter(0.20)
    assert abs(result - 0.20) < 1e-9


def test_hysteresis_does_not_enter_below_threshold():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=3)
    result = h.filter(0.05)
    assert result == 0.05
    assert h.active_sign == 0


def test_hysteresis_enters_sign_above_threshold():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=2)
    h.filter(0.20)
    assert h.active_sign == 1
    h.filter(-0.20)
    h.filter(-0.20)
    h.filter(-0.20)
    assert h.active_sign == -1


def test_hysteresis_sticky_prevents_immediate_flip():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
    h.filter(0.20)
    assert h.active_sign == 1

    result = h.filter(-0.15)
    assert result > 0
    assert h.active_sign == 1


def test_hysteresis_allows_flip_after_sticky_expires():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=2)
    h.filter(0.20)

    h.filter(-0.15)
    h.filter(-0.15)
    h.filter(-0.20)
    assert h.active_sign == -1


def test_hysteresis_exits_when_below_exit_threshold_after_sticky():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=2)
    h.filter(0.20)
    assert h.active_sign == 1

    h.filter(-0.02)
    h.filter(-0.02)
    h.filter(-0.02)
    assert h.active_sign == 0


def test_hysteresis_preserves_magnitude_in_sticky():
    h = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
    h.filter(0.20)

    result = h.filter(-0.15)
    assert abs(result) == 0.15
