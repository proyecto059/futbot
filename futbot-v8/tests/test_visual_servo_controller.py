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
    should_accept_tracked_ball_measurement,
    should_accept_ball_in_attack_context,
    should_use_goal_memory_for_attack,
    update_confirmation_streak,
    update_goal_memory,
    update_goal_flip_candidate,
    should_accept_goal_edge_ball,
    should_accept_goal_in_attack_context,
    should_attack_through_line,
    should_controlled_attack_through_line,
    should_commit_push,
    should_hold_without_ball_near_line,
    should_hold_track_on_miss,
    should_goal_guided_coast,
    should_reset_track_after_jump_rejections,
    should_push_ball,
    should_continue_dribble_push,
    should_continue_dribble_prediction,
    update_goal_y_memory,
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


def test_confirmation_streak_tolerates_single_interleaved_miss():
    streak = 0
    for detected in (True, False, True, False, True):
        streak = update_confirmation_streak(streak, detected)

    assert is_confirmed_ball_streak(streak, min_frames=3) is True


def test_confirmation_streak_decays_on_repeated_misses():
    streak = 3
    streak = update_confirmation_streak(streak, False)
    streak = update_confirmation_streak(streak, False)
    streak = update_confirmation_streak(streak, False)

    assert streak == 0


def test_initial_track_rejects_sudden_large_far_false_positive():
    ball = {"source": "hsv", "r": 66.0}

    assert should_allow_initial_track(ball, streak=5, min_streak=3, max_initial_radius=45.0) is False


def test_initial_track_accepts_consistent_plausible_ball():
    ball = {"source": "hsv", "r": 18.0}

    assert should_allow_initial_track(ball, streak=3, min_streak=3, max_initial_radius=45.0) is True


def test_push_commit_requires_stronger_confirmation():
    assert should_allow_push_commit(streak=3, min_streak=5) is False
    assert should_allow_push_commit(streak=5, min_streak=5) is True


def test_goal_edge_ball_accepts_confirmed_hsv_ball_aligned_with_goal():
    ball = {"source": "hsv", "cx": 290, "r": 8.6}

    assert should_accept_goal_edge_ball(ball, goal_cx=246.0) is True


def test_goal_edge_ball_rejects_small_noise_without_goal_or_alignment():
    ball = {"source": "hsv", "cx": 80, "r": 8.6}

    assert should_accept_goal_edge_ball(ball, goal_cx=None) is False
    assert should_accept_goal_edge_ball(ball, goal_cx=246.0) is False
    assert should_accept_goal_edge_ball({"source": "yolo", "cx": 246, "r": 5.6}, goal_cx=246.0) is False


def test_goal_edge_ball_rejects_tiny_hsv_noise_even_when_aligned():
    ball = {"source": "hsv", "cx": 246, "r": 5.6}

    assert should_accept_goal_edge_ball(ball, goal_cx=246.0) is False


def test_goal_context_rejects_tiny_edge_goal_for_attack_targeting():
    assert should_accept_goal_in_attack_context(
        goal_cx=5.0,
        goal_bbox=[0, 60, 12, 24],
        frame_width=320.0,
    ) is False


def test_goal_context_accepts_wide_clipped_goal_for_attack_targeting():
    assert should_accept_goal_in_attack_context(
        goal_cx=279.0,
        goal_bbox=[226, 28, 94, 33],
        frame_width=320.0,
    ) is True


def test_goal_context_accepts_current_clipped_blue_goal_for_attack_targeting():
    assert should_accept_goal_in_attack_context(
        goal_cx=311.0,
        goal_bbox=[295, 36, 25, 28],
        frame_width=320.0,
    ) is True


def test_trackable_ball_accepts_current_small_far_ball_when_configured():
    ball = {"source": "hsv", "cx": 26, "cy": 82, "r": 5.7}

    assert is_trackable_ball(ball, min_radius=5.5) is True


def test_ball_context_rejects_hsv_ball_when_only_opponent_goal_is_visible():
    ball = {"source": "hsv", "cx": 170.0, "r": 12.0}

    assert should_accept_ball_in_attack_context(
        ball,
        target_goal_visible=False,
        opponent_goal_visible=True,
    ) is False


def test_ball_context_accepts_ball_when_target_goal_is_visible_or_no_goal_seen():
    ball = {"source": "hsv", "cx": 170.0, "r": 12.0}

    assert should_accept_ball_in_attack_context(
        ball,
        target_goal_visible=True,
        opponent_goal_visible=True,
    ) is True
    assert should_accept_ball_in_attack_context(
        ball,
        target_goal_visible=False,
        opponent_goal_visible=False,
    ) is True


def test_tracked_ball_measurement_rejects_recent_large_center_jump():
    ball = {"source": "hsv", "cx": 280.0, "r": 11.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=98.0,
        last_seen_t=10.0,
        now=10.05,
        frame_width=320.0,
    ) is False


def test_tracked_ball_measurement_accepts_jump_after_weak_small_lock():
    ball = {"source": "hsv", "cx": 94.0, "r": 13.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=292.0,
        last_r=10.0,
        last_seen_t=10.0,
        now=10.18,
        frame_width=320.0,
    ) is True


def test_tracked_ball_measurement_rejects_weak_to_weak_large_jump():
    ball = {"source": "hsv", "cx": 29.0, "r": 8.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=261.0,
        last_r=8.3,
        last_seen_t=10.0,
        now=10.14,
        frame_width=320.0,
    ) is False


def test_tracked_ball_measurement_accepts_moderate_weak_to_weak_motion():
    ball = {"source": "hsv", "cx": 218.0, "r": 9.3}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=195.0,
        last_r=12.8,
        last_seen_t=10.0,
        now=10.11,
        frame_width=320.0,
    ) is True


def test_tracked_ball_measurement_still_rejects_jump_after_confident_lock():
    ball = {"source": "hsv", "cx": 94.0, "r": 13.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=292.0,
        last_r=18.0,
        last_seen_t=10.0,
        now=10.18,
        frame_width=320.0,
    ) is False


def test_tracked_ball_measurement_accepts_large_jump_during_post_push_reacquire():
    ball = {"source": "hsv", "cx": 234.0, "r": 23.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=86.0,
        last_r=26.0,
        last_seen_t=10.0,
        now=10.30,
        frame_width=320.0,
        allow_large_jump=True,
        large_jump_min_radius=14.0,
    ) is True


def test_tracked_ball_measurement_accepts_plausible_recent_motion():
    ball = {"source": "hsv", "cx": 132.0, "r": 16.0}

    assert should_accept_tracked_ball_measurement(
        ball,
        last_cx=98.0,
        last_seen_t=10.0,
        now=10.05,
        frame_width=320.0,
    ) is True


def test_hold_track_on_short_ball_miss():
    assert should_hold_track_on_miss(1, max_miss_frames=8) is True
    assert should_hold_track_on_miss(8, max_miss_frames=8) is True


def test_stop_holding_track_after_long_ball_miss():
    assert should_hold_track_on_miss(9, max_miss_frames=8) is False


def test_reset_track_after_repeated_jump_rejections():
    assert should_reset_track_after_jump_rejections(1) is False
    assert should_reset_track_after_jump_rejections(2) is True


def test_goal_guided_coast_uses_recent_ball_and_goal_memory():
    assert should_goal_guided_coast(
        last_ball_seen_t=10.0,
        last_ball_r=18.0,
        goal_cx=303.0,
        goal_seen_t=9.8,
        now=10.35,
        line_detected=False,
    ) is True


def test_goal_guided_coast_requires_safe_recent_context():
    assert should_goal_guided_coast(
        last_ball_seen_t=10.0,
        last_ball_r=18.0,
        goal_cx=303.0,
        goal_seen_t=9.8,
        now=11.0,
        line_detected=False,
        max_ball_age_s=0.7,
    ) is False
    assert should_goal_guided_coast(
        last_ball_seen_t=10.0,
        last_ball_r=18.0,
        goal_cx=None,
        goal_seen_t=9.8,
        now=10.2,
        line_detected=False,
    ) is False
    assert should_goal_guided_coast(
        last_ball_seen_t=10.0,
        last_ball_r=18.0,
        goal_cx=303.0,
        goal_seen_t=9.8,
        now=10.2,
        line_detected=True,
    ) is False


def test_line_is_confirmed_only_after_required_streak():
    assert is_confirmed_line(1, min_streak=2) is False
    assert is_confirmed_line(2, min_streak=2) is True


def test_attack_through_line_when_trackable_ball_is_aligned_with_goal():
    ball = {"source": "hsv", "cx": 197, "r": 16.0}

    assert should_attack_through_line(ball, goal_cx=194, line_detected=True) is True


def test_attack_through_line_when_ball_is_near_target_goal_path():
    ball = {"source": "hsv", "cx": 174, "r": 16.0}

    assert should_attack_through_line(ball, goal_cx=267, line_detected=True) is True


def test_do_not_attack_through_line_without_goal_or_alignment():
    ball = {"source": "hsv", "cx": 80, "r": 16.0}

    assert should_attack_through_line(ball, goal_cx=None, line_detected=True) is False
    assert should_attack_through_line(ball, goal_cx=240, line_detected=True) is False
    assert should_attack_through_line(ball, goal_cx=80, line_detected=False) is False


def test_controlled_attack_through_line_uses_recent_aligned_ball_memory():
    assert should_controlled_attack_through_line(
        ball=None,
        goal_cx=283.0,
        line_detected=True,
        now=10.20,
        last_ball_cx=253.0,
        last_ball_r=22.8,
        last_seen_t=10.05,
    ) is True


def test_controlled_attack_through_line_rejects_stale_or_unaligned_memory():
    assert should_controlled_attack_through_line(
        ball=None,
        goal_cx=283.0,
        line_detected=True,
        now=10.80,
        last_ball_cx=253.0,
        last_ball_r=22.8,
        last_seen_t=10.05,
    ) is False
    assert should_controlled_attack_through_line(
        ball=None,
        goal_cx=80.0,
        line_detected=True,
        now=10.20,
        last_ball_cx=253.0,
        last_ball_r=22.8,
        last_seen_t=10.05,
    ) is False
    assert should_controlled_attack_through_line(
        ball=None,
        goal_cx=283.0,
        line_detected=False,
        now=10.20,
        last_ball_cx=253.0,
        last_ball_r=22.8,
        last_seen_t=10.05,
    ) is False


def test_line_detection_without_ball_allows_avoidance_motion():
    assert should_hold_without_ball_near_line(False, line_detected=True, line_cooldown=0) is False
    assert should_hold_without_ball_near_line(True, line_detected=True, line_cooldown=10) is False
    assert should_hold_without_ball_near_line(False, line_detected=False, line_cooldown=0) is False


def test_line_cooldown_allows_safe_search_motion():
    assert should_hold_without_ball_near_line(False, line_detected=False, line_cooldown=10) is True


def test_line_cooldown_holds_visible_ball_when_attack_goal_is_missing():
    assert should_hold_without_ball_near_line(
        True,
        line_detected=False,
        line_cooldown=10,
        goal_cx=None,
        hold_ball_without_goal=True,
    ) is True
    assert should_hold_without_ball_near_line(
        True,
        line_detected=False,
        line_cooldown=10,
        goal_cx=278.0,
        hold_ball_without_goal=True,
    ) is False


def test_effective_goal_radius_uses_raw_radius_when_smoothing_lags():
    assert effective_goal_radius(raw_radius=46.0, filtered_radius=43.1) == 46.0


def test_commit_push_stays_active_inside_window_only():
    assert should_commit_push(10.2, push_until=10.8) is True
    assert should_commit_push(10.8, push_until=10.8) is False


def test_continue_dribble_push_requires_recent_push_visible_ball():
    ball = {"source": "hsv", "cx": 168, "r": 16.3}

    assert should_continue_dribble_push(
        ball_visible=True,
        ball=ball,
        goal_cx=287.0,
        now=10.2,
        dribble_until=11.0,
    ) is True
    assert should_continue_dribble_push(
        ball_visible=True,
        ball=ball,
        goal_cx=287.0,
        now=11.0,
        dribble_until=11.0,
    ) is False
    assert should_continue_dribble_push(
        ball_visible=False,
        ball=ball,
        goal_cx=287.0,
        now=10.2,
        dribble_until=11.0,
    ) is False
    assert should_continue_dribble_push(
        ball_visible=True,
        ball={"source": "hsv", "cx": 168, "r": 9.0},
        goal_cx=287.0,
        now=10.2,
        dribble_until=11.0,
    ) is False
    assert should_continue_dribble_push(
        ball_visible=True,
        ball=ball,
        goal_cx=None,
        now=10.2,
        dribble_until=11.0,
    ) is True


def test_continue_dribble_prediction_uses_recent_ball_memory_after_push():
    assert should_continue_dribble_prediction(
        goal_cx=287.0,
        now=10.25,
        dribble_until=11.0,
        last_seen_t=10.0,
        last_valid_r=18.0,
    ) is True
    assert should_continue_dribble_prediction(
        goal_cx=287.0,
        now=10.55,
        dribble_until=11.0,
        last_seen_t=10.0,
        last_valid_r=18.0,
        max_age_s=0.45,
    ) is False
    assert should_continue_dribble_prediction(
        goal_cx=287.0,
        now=10.25,
        dribble_until=11.0,
        last_seen_t=10.0,
        last_valid_r=9.0,
    ) is False
    assert should_continue_dribble_prediction(
        goal_cx=None,
        now=10.25,
        dribble_until=11.0,
        last_seen_t=10.0,
        last_valid_r=18.0,
    ) is True


def test_post_push_prediction_suppresses_line_hold_without_visible_ball():
    assert should_hold_without_ball_near_line(
        False,
        line_detected=False,
        line_cooldown=10,
        allow_dribble_prediction=True,
    ) is False


def test_post_push_prediction_attacks_through_line_without_current_ball():
    assert should_attack_through_line(
        None,
        goal_cx=None,
        line_detected=True,
        allow_dribble_prediction=True,
    ) is True


def test_goal_memory_rejects_impossible_short_term_center_jump():
    goal_cx, goal_ts, accepted = update_goal_memory(
        current_cx=31.0,
        last_cx=287.0,
        last_ts=10.0,
        now=10.05,
        frame_width=320.0,
    )

    assert goal_cx == 287.0
    assert goal_ts == 10.0
    assert accepted is False


def test_goal_memory_rejects_fresh_opposite_side_flip():
    goal_cx, goal_ts, accepted = update_goal_memory(
        current_cx=31.0,
        last_cx=288.0,
        last_ts=10.0,
        now=11.5,
        frame_width=320.0,
    )

    assert goal_cx == 288.0
    assert goal_ts == 10.0
    assert accepted is False


def test_goal_flip_candidate_accepts_persistent_opposite_side_goal():
    pending_cx = None
    pending_count = 0
    pending_ts = 0.0

    for now in (10.00, 10.10, 10.20):
        pending_cx, pending_count, pending_ts, accepted = update_goal_flip_candidate(
            current_cx=250.0,
            remembered_cx=70.0,
            pending_cx=pending_cx,
            pending_count=pending_count,
            pending_ts=pending_ts,
            now=now,
            frame_width=320.0,
            confirm_frames=3,
        )

    assert accepted is True
    assert pending_cx == 250.0
    assert pending_count == 3
    assert pending_ts == 10.20


def test_goal_flip_candidate_rejects_observed_left_edge_noise():
    pending_cx = None
    pending_count = 0
    pending_ts = 0.0

    for now in (10.00, 10.10, 10.20):
        pending_cx, pending_count, pending_ts, accepted = update_goal_flip_candidate(
            current_cx=40.0,
            remembered_cx=314.0,
            pending_cx=pending_cx,
            pending_count=pending_count,
            pending_ts=pending_ts,
            now=now,
            frame_width=320.0,
            confirm_frames=3,
        )

    assert accepted is False
    assert pending_cx is None
    assert pending_count == 0
    assert pending_ts == 0.0


def test_goal_flip_candidate_rejects_opposite_side_noise_while_memory_is_fresh():
    pending_cx = None
    pending_count = 0
    pending_ts = 0.0

    for now in (10.00, 10.10, 10.20):
        pending_cx, pending_count, pending_ts, accepted = update_goal_flip_candidate(
            current_cx=64.0,
            remembered_cx=306.0,
            remembered_ts=9.80,
            pending_cx=pending_cx,
            pending_count=pending_count,
            pending_ts=pending_ts,
            now=now,
            frame_width=320.0,
            confirm_frames=3,
        )

    assert accepted is False
    assert pending_cx is None
    assert pending_count == 0
    assert pending_ts == 0.0


def test_goal_flip_candidate_rejects_persistent_edge_noise():
    pending_cx = None
    pending_count = 0
    pending_ts = 0.0

    for now in (10.00, 10.10, 10.20):
        pending_cx, pending_count, pending_ts, accepted = update_goal_flip_candidate(
            current_cx=9.0,
            remembered_cx=316.0,
            pending_cx=pending_cx,
            pending_count=pending_count,
            pending_ts=pending_ts,
            now=now,
            frame_width=320.0,
            confirm_frames=3,
        )

    assert accepted is False
    assert pending_cx is None
    assert pending_count == 0
    assert pending_ts == 0.0


def test_goal_flip_candidate_ignores_single_opposite_side_noise():
    pending_cx, pending_count, pending_ts, accepted = update_goal_flip_candidate(
        current_cx=250.0,
        remembered_cx=70.0,
        pending_cx=None,
        pending_count=0,
        pending_ts=0.0,
        now=10.0,
        frame_width=320.0,
        confirm_frames=3,
    )

    assert accepted is False
    assert pending_cx == 250.0
    assert pending_count == 1
    assert pending_ts == 10.0


def test_goal_memory_accepts_smooth_center_motion():
    goal_cx, goal_ts, accepted = update_goal_memory(
        current_cx=260.0,
        last_cx=287.0,
        last_ts=10.0,
        now=10.05,
        frame_width=320.0,
    )

    assert goal_cx == 260.0
    assert goal_ts == 10.05
    assert accepted is True


def test_goal_memory_expires_when_goal_is_lost_too_long():
    goal_cx, goal_ts, accepted = update_goal_memory(
        current_cx=None,
        last_cx=287.0,
        last_ts=10.0,
        now=12.1,
        frame_width=320.0,
        max_age_s=2.0,
    )

    assert goal_cx is None
    assert goal_ts == 10.0
    assert accepted is False


def test_goal_y_memory_updates_when_goal_center_is_accepted():
    assert update_goal_y_memory(
        current_cy=72.8,
        last_cy=80.0,
        remembered_cx=260.0,
        goal_accepted=True,
    ) == 72.8


def test_goal_y_memory_keeps_previous_y_when_center_jump_is_rejected():
    assert update_goal_y_memory(
        current_cy=72.8,
        last_cy=80.0,
        remembered_cx=287.0,
        goal_accepted=False,
    ) == 80.0


def test_goal_y_memory_clears_when_goal_memory_expires():
    assert update_goal_y_memory(
        current_cy=72.8,
        last_cy=80.0,
        remembered_cx=None,
        goal_accepted=False,
    ) is None


def test_goal_memory_is_suppressed_when_only_opponent_goal_is_visible():
    assert should_use_goal_memory_for_attack(
        target_goal_visible=False,
        opponent_goal_visible=True,
    ) is False


def test_goal_memory_is_usable_when_target_visible_or_no_opponent_seen():
    assert should_use_goal_memory_for_attack(
        target_goal_visible=True,
        opponent_goal_visible=True,
    ) is True
    assert should_use_goal_memory_for_attack(
        target_goal_visible=False,
        opponent_goal_visible=False,
    ) is True


def test_goal_memory_is_suppressed_during_opposite_side_conflict():
    assert should_use_goal_memory_for_attack(
        target_goal_visible=True,
        opponent_goal_visible=False,
        goal_conflict=True,
    ) is False


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
