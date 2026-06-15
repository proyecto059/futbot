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
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert 0.0 < wheel_turn(cmd.v_left, cmd.v_right) < 20.0


def test_moderately_right_ball_still_gets_physical_turn_floor():
    cmd = build_controller().compute(
        ball_cx=200.0,
        ball_r=43.0,
        goal_cx=None,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
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


def test_close_centered_ball_with_blue_goal_right_biases_push_right():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=75.0,
        goal_cx=230.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


def test_close_centered_ball_with_yellow_goal_left_biases_push_left():
    cmd = build_controller().compute(
        ball_cx=160.0,
        ball_r=75.0,
        goal_cx=90.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_close_ball_without_goal_pushes_only_when_aligned():
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

    assert centered.mode == "PUSH"
    assert off_center.mode == "CHASE"


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

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0


def test_close_right_ball_with_goal_far_left_keeps_arcing_before_push():
    cmd = build_controller().compute(
        ball_cx=250.0,
        ball_r=60.0,
        goal_cx=60.0,
        line_detected=False,
    )

    assert cmd.mode == "CHASE"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) > 0


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
        goal_cx=177.0,
        line_detected=False,
    )

    assert cmd.mode == "PUSH"
    assert wheel_forward(cmd.v_left, cmd.v_right) > 0
    assert wheel_turn(cmd.v_left, cmd.v_right) < 0
