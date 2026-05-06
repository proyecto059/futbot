import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chase.visual_servo_controller import VisualServoController


def build_controller():
    return VisualServoController(
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
