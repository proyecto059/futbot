import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chase.attack_geometry import (
    behind_ball_point,
    is_ball_inside_goal,
    is_push_ready,
    is_robot_near_behind_point,
    route_curve_points,
    scored_goal_color,
    scored_goal_color_after_push,
)


def test_ball_inside_goal_when_center_is_inside_bbox():
    ball = {"cx": 125, "cy": 80, "r": 8}
    bbox = [100, 50, 80, 70]

    assert is_ball_inside_goal(ball, bbox) is True


def test_ball_inside_goal_allows_radius_overlap_margin():
    ball = {"cx": 95, "cy": 80, "r": 8}
    bbox = [100, 50, 80, 70]

    assert is_ball_inside_goal(ball, bbox) is True


def test_ball_outside_goal_when_no_overlap():
    ball = {"cx": 60, "cy": 80, "r": 8}
    bbox = [100, 50, 80, 70]

    assert is_ball_inside_goal(ball, bbox) is False


def test_push_ready_requires_close_aligned_ball_and_goal():
    ball = {"cx": 180, "cy": 150, "r": 48}

    assert is_push_ready(ball, goal_cx=200, min_radius=45, max_dx=55) is True
    assert is_push_ready(ball, goal_cx=280, min_radius=45, max_dx=55) is False
    assert is_push_ready({"cx": 180, "cy": 150, "r": 30}, goal_cx=200, min_radius=45, max_dx=55) is False


def test_scored_goal_color_only_checks_target_goal():
    ball = {"cx": 55, "cy": 80, "r": 8}
    goals = {
        "blue": True,
        "blue_bbox": [200, 50, 80, 70],
        "yellow": True,
        "yellow_bbox": [40, 50, 80, 70],
    }

    assert scored_goal_color(ball, goals, target_key="blue") is None
    assert scored_goal_color(ball, goals, target_key="yellow") == "yellow"


def test_scored_goal_color_rejects_edge_radius_overlap_without_center_inside_goal():
    ball = {"cx": 246, "cy": 95, "r": 38}
    goals = {
        "blue": True,
        "blue_bbox": [256, 91, 64, 8],
        "yellow": False,
        "yellow_bbox": None,
    }

    assert scored_goal_color(ball, goals, target_key="blue") is None


def test_scored_goal_requires_active_push_context():
    ball = {"cx": 55, "cy": 80, "r": 8}
    goals = {
        "blue": True,
        "blue_bbox": [40, 50, 80, 70],
    }

    assert scored_goal_color_after_push(
        ball,
        goals,
        target_key="blue",
        push_until=9.9,
        now=10.0,
    ) is None


def test_scored_goal_accepts_active_push_context():
    ball = {"cx": 55, "cy": 80, "r": 8}
    goals = {
        "blue": True,
        "blue_bbox": [40, 50, 80, 70],
    }

    assert scored_goal_color_after_push(
        ball,
        goals,
        target_key="blue",
        push_until=10.1,
        now=10.0,
    ) == "blue"


def test_behind_ball_point_uses_saved_capture_geometry():
    behind_x, behind_y = behind_ball_point(
        ball_cx=96.0,
        ball_cy=85.0,
        goal_cx=14.8,
        goal_cy=72.8,
        distance=45.0,
    )

    assert 139.0 <= behind_x <= 142.0
    assert 91.0 <= behind_y <= 94.0


def test_robot_near_behind_point_uses_pixel_tolerance():
    assert is_robot_near_behind_point(
        robot_cx=160.0,
        robot_cy=120.0,
        behind_x=140.0,
        behind_y=92.0,
        tolerance=35.0,
    ) is True
    assert is_robot_near_behind_point(
        robot_cx=40.0,
        robot_cy=120.0,
        behind_x=140.0,
        behind_y=92.0,
        tolerance=35.0,
    ) is False


def test_route_curve_bows_left_toward_behind_point_for_saved_capture():
    points = route_curve_points(
        start=(160.0, 239.0),
        end=(140.0, 92.0),
        bend=55.0,
        samples=9,
    )

    assert points[0] == (160.0, 239.0)
    assert points[-1] == (140.0, 92.0)
    mid_x, mid_y = points[len(points) // 2]
    assert mid_x < 150.0
    assert 150.0 <= mid_y <= 180.0


def test_route_curve_bows_left_for_current_blue_goal_capture_geometry():
    behind_x, behind_y = behind_ball_point(
        ball_cx=46.0,
        ball_cy=111.0,
        goal_cx=146.3,
        goal_cy=69.8,
    )
    points = route_curve_points(
        start=(160.0, 239.0),
        end=(behind_x, behind_y),
        bend=55.0,
        samples=9,
    )

    mid_x, _mid_y = points[len(points) // 2]
    assert behind_x < 10.0
    assert mid_x < 110.0
