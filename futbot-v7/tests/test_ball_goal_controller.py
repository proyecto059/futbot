import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chase.ball_goal_controller import BallGoalController


def build_controller(**overrides):
    kwargs = dict(frame_width=320.0)
    kwargs.update(overrides)
    return BallGoalController(**kwargs)


def wheel_forward(v_left, v_right):
    return (v_left - v_right) * 0.5


def wheel_turn(v_left, v_right):
    return (v_left + v_right) * 0.5


def assert_no_forward_push(command):
    assert abs(wheel_forward(command.v_left, command.v_right)) <= 1.0


def test_line_detected_returns_line_escape_mode():
    cmd = build_controller().compute(
        ball_cx=180.0,
        ball_r=45.0,
        goal_cx=160.0,
        line_detected=True,
    )

    assert cmd.mode == "LINE_ESCAPE"
    assert cmd.v_left < 0
    assert cmd.v_right > 0


def test_far_ball_right_returns_forward_arc_right():
    cmd = build_controller().compute(
        ball_cx=230.0,
        ball_r=35.0,
        goal_cx=160.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


def test_far_ball_left_returns_forward_arc_left():
    cmd = build_controller().compute(
        ball_cx=90.0,
        ball_r=35.0,
        goal_cx=160.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_centered_far_ball_goes_forward():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=35.0,
        goal_cx=220.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert abs(wheel_turn(cmd.v_left, cmd.v_right)) < 1.0


def test_far_ball_is_faster_than_near_ball():
    controller = build_controller()

    far = controller.compute(
        ball_cx=160.0,
        ball_r=12.0,
        goal_cx=None,
        line_detected=False,
    )
    near = controller.compute(
        ball_cx=160.0,
        ball_r=52.0,
        goal_cx=None,
        line_detected=False,
    )

    assert far.mode == "CHASE"
    assert near.mode == "CHASE"
    assert wheel_forward(far.v_left, far.v_right) > wheel_forward(near.v_left, near.v_right)


def test_far_off_center_ball_keeps_forward_arc_not_stop_turn():
    cmd = build_controller().compute(
        ball_cx=300.0,
        ball_r=12.0,
        goal_cx=160.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) >= 45.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_slightly_right_ball_uses_gentle_forward_arc_right():
    cmd = build_controller().compute(
        ball_cx=170.0,
        ball_r=43.0,
        goal_cx=None,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_moderately_right_ball_still_gets_physical_turn_floor():
    cmd = build_controller().compute(
        ball_cx=200.0,
        ball_r=43.0,
        goal_cx=None,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) >= 41.9


def test_extreme_left_ball_keeps_both_wheels_driving_forward():
    cmd = build_controller().compute(
        ball_cx=30.0,
        ball_r=22.0,
        goal_cx=160.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0
    assert cmd.v_left >= 20.0
    assert cmd.v_right <= -20.0


def test_close_centered_ball_with_blue_goal_right_orbits_left_before_push():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=75.0,
        goal_cx=230.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_saved_capture_align_arc_follows_route_curve_lookahead():
    cmd = build_controller().compute(
        ball_cx=96.0,
        ball_cy=85.0,
        ball_r=39.0,
        goal_cx=14.8,
        goal_cy=72.8,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_saved_capture_small_ball_uses_route_instead_of_chase():
    cmd = build_controller().compute(
        ball_cx=96.0,
        ball_cy=85.0,
        ball_r=13.3,
        goal_cx=14.8,
        goal_cy=72.8,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert cmd.reason == "route"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_current_blue_goal_capture_route_turns_toward_left_behind_point():
    cmd = build_controller().compute(
        ball_cx=46.0,
        ball_cy=111.0,
        ball_r=12.0,
        goal_cx=146.3,
        goal_cy=69.8,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert cmd.reason == "route"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_align_arc_without_y_geometry_stays_conservative_pivot():
    cmd = build_controller().compute(
        ball_cx=96.0,
        ball_r=39.0,
        goal_cx=14.8,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_close_centered_ball_with_yellow_goal_left_orbits_right_before_push():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=75.0,
        goal_cx=90.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


def test_close_ball_without_goal_chases_instead_of_pushing():
    centered = build_controller().compute(
        ball_cx=162.0,
        ball_r=75.0,
        goal_cx=None,
        line_detected=False,
    )
    off_center = build_controller().compute(
        ball_cx=210.0,
        ball_r=75.0,
        goal_cx=None,
        line_detected=False,
    )

    assert centered.mode == "CHASE"
    assert off_center.mode == "CHASE"
    assert wheel_forward(centered.v_left, centered.v_right) > 0.0
    assert wheel_forward(off_center.v_left, off_center.v_right) > 0.0


def test_close_off_center_ball_with_blue_goal_enters_goal_push():
    cmd = build_controller().compute(
        ball_cx=235.0,
        ball_r=60.0,
        goal_cx=260.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


def test_goal_aligned_ball_pushes_before_line_occlusion_radius():
    cmd = build_controller().compute(
        ball_cx=194.0,
        ball_r=48.0,
        goal_cx=189.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) >= 120.0


def test_log_aligned_blue_goal_keeps_chasing_when_ball_is_far_lateral():
    cmd = build_controller().compute(
        ball_cx=265.6,
        ball_r=32.4,
        goal_cx=280.0,
        line_detected=False,
    )

    assert cmd.mode != "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_off_center_aligned_ball_does_not_push_before_robot_is_facing_it():
    cmd = build_controller().compute(
        ball_cx=266.4,
        ball_cy=89.0,
        ball_r=34.2,
        goal_cx=296.0,
        goal_cy=60.0,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode != "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_visible_ball_without_goal_keeps_chasing_instead_of_spinning_in_place():
    cmd = build_controller().compute(
        ball_cx=230.0,
        ball_r=18.0,
        goal_cx=None,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_log_close_blue_goal_keeps_chasing_with_far_lateral_ball():
    cmd = build_controller().compute(
        ball_cx=273.0,
        ball_cy=120.0,
        ball_r=33.0,
        goal_cx=313.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode != "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_route_align_arc_turn_is_capped_to_reduce_spin():
    cmd = build_controller().compute(
        ball_cx=46.0,
        ball_cy=111.0,
        ball_r=12.0,
        goal_cx=146.3,
        goal_cy=69.8,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert -30.0 <= wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_route_align_arc_keeps_turning_right_when_ball_and_blue_goal_are_right():
    cmd = build_controller().compute(
        ball_cx=194.1,
        ball_cy=89.0,
        ball_r=23.1,
        goal_cx=273.0,
        goal_cy=60.0,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_smaller_aligned_ball_with_route_geometry_keeps_aligning_until_behind():
    cmd = build_controller().compute(
        ball_cx=240.0,
        ball_cy=120.0,
        ball_r=24.0,
        goal_cx=270.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert cmd.reason == "route"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0


def test_aligned_ball_with_route_geometry_pushes_when_near_behind_point():
    cmd = build_controller().compute(
        ball_cx=180.0,
        ball_cy=170.0,
        ball_r=32.4,
        goal_cx=200.0,
        goal_cy=100.0,
        frame_height=240.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0


def test_continue_push_follows_ball_after_contact_instead_of_repositioning():
    cmd = build_controller().compute(
        ball_cx=168.0,
        ball_cy=112.0,
        ball_r=16.3,
        goal_cx=287.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
        continue_push=True,
    )

    assert cmd.mode == "PUSH"
    assert cmd.reason == "dribble"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_continue_push_keeps_following_when_goal_temporarily_missing():
    cmd = build_controller().compute(
        ball_cx=64.0,
        ball_cy=112.0,
        ball_r=21.0,
        goal_cx=None,
        goal_cy=None,
        frame_height=240.0,
        line_detected=False,
        continue_push=True,
    )

    assert cmd.mode == "PUSH"
    assert cmd.reason == "dribble"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_continue_push_prioritizes_ball_contact_when_goal_is_far_opposite():
    cmd = build_controller().compute(
        ball_cx=64.0,
        ball_cy=112.0,
        ball_r=21.0,
        goal_cx=288.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
        continue_push=True,
    )

    assert cmd.mode == "PUSH"
    assert cmd.reason == "dribble"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0.0


def test_continue_push_does_not_snap_left_when_ball_is_slightly_right():
    cmd = build_controller().compute(
        ball_cx=176.0,
        ball_cy=112.0,
        ball_r=23.0,
        goal_cx=31.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
        continue_push=True,
    )

    assert cmd.mode == "PUSH"
    assert cmd.reason == "dribble"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0.0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0.0


def test_continue_push_ignores_tiny_ball_after_contact():
    cmd = build_controller().compute(
        ball_cx=168.0,
        ball_cy=112.0,
        ball_r=9.0,
        goal_cx=287.0,
        goal_cy=75.0,
        frame_height=240.0,
        line_detected=False,
        continue_push=True,
    )

    assert cmd.mode == "ALIGN_ARC"


def test_close_off_center_ball_with_yellow_goal_enters_goal_push():
    cmd = build_controller().compute(
        ball_cx=85.0,
        ball_r=60.0,
        goal_cx=60.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_close_left_ball_with_goal_far_right_keeps_arcing_before_push():
    cmd = build_controller().compute(
        ball_cx=70.0,
        ball_r=60.0,
        goal_cx=260.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_close_right_ball_with_goal_far_left_keeps_arcing_before_push():
    cmd = build_controller().compute(
        ball_cx=250.0,
        ball_r=60.0,
        goal_cx=60.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


def test_medium_close_right_ball_with_goal_far_left_orbits_before_push():
    cmd = build_controller().compute(
        ball_cx=290.0,
        ball_r=39.0,
        goal_cx=31.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) >= 40.0


def test_small_unaligned_ball_with_visible_goal_starts_positioning_before_pass_by():
    cmd = build_controller().compute(
        ball_cx=225.0,
        ball_r=17.0,
        goal_cx=60.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) >= 40.0


def test_medium_close_left_ball_with_goal_far_right_orbits_before_push():
    cmd = build_controller().compute(
        ball_cx=30.0,
        ball_r=39.0,
        goal_cx=289.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) <= -40.0


def test_medium_close_center_ball_with_goal_far_right_orbits_before_push():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=39.0,
        goal_cx=280.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) <= -40.0


def test_medium_close_slightly_left_ball_with_goal_left_orbits_away_from_goal():
    cmd = build_controller().compute(
        ball_cx=149.0,
        ball_r=43.0,
        goal_cx=31.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) >= 40.0


def test_close_ball_with_wide_goal_offset_orbits_instead_of_pushing_forward():
    cmd = build_controller().compute(
        ball_cx=205.0,
        ball_r=48.0,
        goal_cx=287.0,
        line_detected=False,
    )

    assert cmd.mode == "ALIGN_ARC"
    assert_no_forward_push(cmd)
    assert wheel_turn(cmd.v_left, cmd.v_right) <= -40.0


def test_close_ball_aligned_with_goal_still_pushes():
    cmd = build_controller().compute(
        ball_cx=210.0,
        ball_r=60.0,
        goal_cx=220.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0


def test_push_turns_left_when_goal_is_left_of_ball():
    cmd = build_controller().compute(
        ball_cx=236.0,
        ball_r=45.0,
        goal_cx=205.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0
