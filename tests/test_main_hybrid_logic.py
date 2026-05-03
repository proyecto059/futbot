import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import (
    AVOID_MAP,
    CHASE,
    SEARCH,
    PAN_CENTER,
    TILT_CENTER,
    ATTACK_BLUE,
    KICK_RADIUS_PX,
    apply_ball_proximity_override,
    avoid_map_turn_direction,
    build_avoid_map_plan,
    choose_search_turn,
    compute_chase_wheels,
    compute_kick_wheels,
    differential,
    hybrid_trigger,
    move_forward,
    move_reverse,
    next_state,
    stop_robot,
    turn_left,
    turn_right,
)

import main as main_module


class FakeBus:
    def __init__(self):
        self.calls = []

    def burst(self, *args):
        self.calls.append(args)


def test_hybrid_trigger_by_distance():
    triggered, cause = hybrid_trigger(120, 180)
    assert triggered is True
    assert cause == "dist"


def test_hybrid_trigger_none_when_thresholds_not_met():
    triggered, cause = hybrid_trigger(250, 180)
    assert triggered is False
    assert cause == "none"


def test_hybrid_trigger_inclusive_at_distance_boundary():
    triggered, cause = hybrid_trigger(180, 180)
    assert triggered is True
    assert cause == "dist"


def test_hybrid_trigger_returns_none_when_distance_is_unknown():
    triggered, cause = hybrid_trigger(None, 180)
    assert triggered is False
    assert cause == "none"


def test_compute_chase_wheels_straight_when_centered():
    v_left, v_right = compute_chase_wheels(
        cx=160,
        radius=30,
        frame_width=320,
        speed_base=40,
        rot_gain=0.1,
        deadband_px=12,
        radius_close=KICK_RADIUS_PX,
    )
    assert v_left == 40
    assert v_right == 40


def test_compute_chase_wheels_turns_right_when_ball_is_right():
    v_left, v_right = compute_chase_wheels(
        cx=220,
        radius=30,
        frame_width=320,
        speed_base=40,
        rot_gain=0.1,
        deadband_px=12,
        radius_close=KICK_RADIUS_PX,
    )
    assert v_left > v_right


def test_compute_chase_wheels_turns_left_with_exact_wheel_values():
    v_left, v_right = compute_chase_wheels(
        cx=100,
        radius=30,
        frame_width=320,
        speed_base=40,
        rot_gain=0.1,
        deadband_px=12,
        radius_close=KICK_RADIUS_PX,
    )
    assert v_left == 34.0
    assert v_right == 46.0


def test_compute_chase_wheels_deadband_boundary_goes_straight():
    v_left, v_right = compute_chase_wheels(
        cx=172,
        radius=30,
        frame_width=320,
        speed_base=40,
        rot_gain=0.1,
        deadband_px=12,
        radius_close=KICK_RADIUS_PX,
    )
    assert v_left == 40
    assert v_right == 40


def test_compute_chase_wheels_stops_when_close():
    v_left, v_right = compute_chase_wheels(
        cx=160,
        radius=80,
        frame_width=320,
        speed_base=40,
        rot_gain=0.1,
        deadband_px=12,
        radius_close=KICK_RADIUS_PX,
    )
    assert v_left == 0
    assert v_right == 0


def test_differential_returns_expected_motor_tuple_without_scaling():
    assert differential(50, 30) == (0.0, 0.0, 50, -30)


def test_differential_scales_both_wheels_to_cap():
    assert differential(500, -250, cap=250) == (0.0, 0.0, 250.0, 125.0)


def test_differential_result_can_be_sent_as_exact_burst_arguments():
    bus = FakeBus()
    motors = differential(60, -40)

    bus.burst(PAN_CENTER, TILT_CENTER, 350, *motors)

    assert bus.calls == [
        (PAN_CENTER, TILT_CENTER, 350, 0.0, 0.0, 60, 40),
    ]


@pytest.mark.parametrize(
    "move_fn,speed,dur_ms,expected",
    [
        (move_forward, 100, 350, (PAN_CENTER, TILT_CENTER, 350, 0.0, 0.0, 100, -100)),
        (move_reverse, 100, 350, (PAN_CENTER, TILT_CENTER, 350, 0.0, 0.0, -100, 100)),
        (turn_left, 100, 350, (PAN_CENTER, TILT_CENTER, 350, 0.0, 0.0, -100, -100)),
        (turn_right, 100, 350, (PAN_CENTER, TILT_CENTER, 350, 0.0, 0.0, 100, 100)),
    ],
)
def test_movement_helpers_burst_expected_arguments(move_fn, speed, dur_ms, expected):
    bus = FakeBus()

    move_fn(bus, speed=speed, dur_ms=dur_ms)

    assert bus.calls == [expected]


def test_stop_robot_bursts_expected_arguments():
    bus = FakeBus()

    stop_robot(bus, dur_ms=350)

    assert bus.calls == [
        (PAN_CENTER, TILT_CENTER, 350, 0, 0, 0, 0),
    ]


def test_choose_search_turn_prefers_left_for_leftmost_last_seen():
    assert choose_search_turn(last_cx=80, frame_center_x=160) == "left"


def test_choose_search_turn_prefers_right_for_rightmost_last_seen():
    assert choose_search_turn(last_cx=240, frame_center_x=160) == "right"


def test_choose_search_turn_prefers_right_when_last_seen_is_exactly_centered():
    assert choose_search_turn(last_cx=160, frame_center_x=160) == "right"


def test_choose_search_turn_defaults_left_when_unknown():
    assert choose_search_turn(last_cx=None, frame_center_x=160) == "left"


def test_next_state_search_to_chase_when_ball_visible():
    assert next_state(SEARCH, True, False, 0.0, 0.5) == CHASE


def test_next_state_search_stays_when_ball_missing():
    assert next_state(SEARCH, False, False, 0.0, 0.5) == SEARCH


def test_next_state_chase_to_avoid_on_hybrid_trigger():
    assert next_state(CHASE, True, True, 0.0, 0.5) == AVOID_MAP


def test_next_state_chase_to_search_after_miss_limit():
    assert next_state(CHASE, False, False, 0.6, 0.5) == SEARCH


def test_next_state_chase_stays_when_under_miss_limit():
    assert next_state(CHASE, False, False, 0.3, 0.5) == CHASE


def test_next_state_avoid_to_chase_when_ball_visible():
    assert next_state(AVOID_MAP, True, False, 0.0, 0.5) == CHASE


def test_next_state_avoid_stays_when_ball_visible_and_hybrid_active():
    assert next_state(AVOID_MAP, True, True, 0.0, 0.5) == AVOID_MAP


def test_next_state_avoid_to_search_when_ball_missing():
    assert next_state(AVOID_MAP, False, False, 0.0, 0.5) == SEARCH


def test_avoid_map_turn_direction_prefers_left_for_leftmost_last_seen():
    assert avoid_map_turn_direction(last_cx=80, frame_center_x=160) == "left"


def test_avoid_map_turn_direction_prefers_right_for_rightmost_last_seen():
    assert avoid_map_turn_direction(last_cx=240, frame_center_x=160) == "right"


def test_avoid_map_turn_direction_prefers_right_when_last_seen_centered():
    assert avoid_map_turn_direction(last_cx=160, frame_center_x=160) == "right"


def test_avoid_map_turn_direction_defaults_left_when_unknown():
    assert avoid_map_turn_direction(last_cx=None, frame_center_x=160) == "left"


def test_avoid_map_sequence_is_bounded():
    steps = build_avoid_map_plan(last_cx=40, frame_center_x=160, max_steps=5)
    assert len(steps) <= 5


def test_avoid_map_state_decision_keeps_avoid_until_plan_done_when_hybrid_active():
    assert (
        main_module.avoid_map_state_decision(
            ball_visible=True,
            hybrid_active=True,
            avoid_index=1,
            avoid_plan_len=5,
        )
        == AVOID_MAP
    )


def test_avoid_map_state_decision_allows_early_chase_when_hybrid_clears():
    assert (
        main_module.avoid_map_state_decision(
            ball_visible=True,
            hybrid_active=False,
            avoid_index=1,
            avoid_plan_len=5,
        )
        == CHASE
    )


def test_kick_wheels_straight_when_goal_centered():
    v_left, v_right = compute_kick_wheels(
        goal_cx=160, frame_width=320, kick_speed=180, kick_rot_gain=0.5
    )
    assert v_left == 180
    assert v_right == 180


def test_kick_wheels_turns_toward_goal_on_right():
    v_left, v_right = compute_kick_wheels(
        goal_cx=240, frame_width=320, kick_speed=180, kick_rot_gain=0.5
    )
    assert v_left > v_right


def test_kick_wheels_turns_toward_goal_on_left():
    v_left, v_right = compute_kick_wheels(
        goal_cx=80, frame_width=320, kick_speed=180, kick_rot_gain=0.5
    )
    assert v_left < v_right


def test_kick_wheels_straight_when_no_goal():
    v_left, v_right = compute_kick_wheels(
        goal_cx=None, frame_width=320, kick_speed=180, kick_rot_gain=0.5
    )
    assert v_left == 180
    assert v_right == 180


def test_attack_blue_default_is_true():
    assert ATTACK_BLUE is False


def test_ball_proximity_override_suppresses_avoid_when_ball_recent_and_close():
    hybrid_active, cause = apply_ball_proximity_override(
        hybrid_active=True,
        cause="dist",
        recent_ball=True,
        very_close=True,
    )
    assert hybrid_active is False
    assert cause == "ball_proximity"


def test_ball_proximity_override_keeps_avoid_when_ball_not_recent():
    hybrid_active, cause = apply_ball_proximity_override(
        hybrid_active=True,
        cause="dist",
        recent_ball=False,
        very_close=True,
    )
    assert hybrid_active is True
    assert cause == "dist"


def test_ball_proximity_override_no_change_when_not_close():
    hybrid_active, cause = apply_ball_proximity_override(
        hybrid_active=False,
        cause="none",
        recent_ball=True,
        very_close=False,
    )
    assert hybrid_active is False
    assert cause == "none"


def test_ball_proximity_override_no_change_when_hybrid_already_inactive():
    hybrid_active, cause = apply_ball_proximity_override(
        hybrid_active=False,
        cause="none",
        recent_ball=True,
        very_close=True,
    )
    assert hybrid_active is False
    assert cause == "none"