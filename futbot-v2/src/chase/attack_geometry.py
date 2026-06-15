from __future__ import annotations

import math


def behind_ball_point(
    ball_cx: float,
    ball_cy: float,
    goal_cx: float,
    goal_cy: float,
    distance: float = 45.0,
) -> tuple[float, float]:
    dx = float(ball_cx) - float(goal_cx)
    dy = float(ball_cy) - float(goal_cy)
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return float(ball_cx), float(ball_cy)
    scale = float(distance) / length
    return float(ball_cx) + dx * scale, float(ball_cy) + dy * scale


def is_robot_near_behind_point(
    robot_cx: float,
    robot_cy: float,
    behind_x: float,
    behind_y: float,
    tolerance: float = 24.0,
) -> bool:
    return math.hypot(float(robot_cx) - float(behind_x), float(robot_cy) - float(behind_y)) <= float(tolerance)


def route_curve_points(
    start: tuple[float, float],
    end: tuple[float, float],
    bend: float = 55.0,
    samples: int = 18,
) -> list[tuple[float, float]]:
    start_x, start_y = float(start[0]), float(start[1])
    end_x, end_y = float(end[0]), float(end[1])
    count = max(2, int(samples))
    side = -1.0 if end_x <= start_x else 1.0
    control_x = start_x + side * float(bend)
    control_y = (start_y + end_y) * 0.5
    points = []
    for idx in range(count):
        t = idx / float(count - 1)
        inv = 1.0 - t
        x = inv * inv * start_x + 2.0 * inv * t * control_x + t * t * end_x
        y = inv * inv * start_y + 2.0 * inv * t * control_y + t * t * end_y
        points.append((x, y))
    return points


def is_ball_inside_goal(
    ball: dict | None,
    goal_bbox: list[int] | tuple[int, int, int, int] | None,
    x_margin_ratio: float = 1.0,
    y_margin_ratio: float = 1.0,
) -> bool:
    if not ball or not goal_bbox:
        return False
    x, y, w, h = [float(v) for v in goal_bbox]
    cx = float(ball.get("cx", 0.0))
    cy = float(ball.get("cy", 0.0))
    r = max(0.0, float(ball.get("r", 0.0)))
    x_margin = r * float(x_margin_ratio)
    y_margin = r * float(y_margin_ratio)
    return (x - x_margin) <= cx <= (x + w + x_margin) and (
        y - y_margin
    ) <= cy <= (y + h + y_margin)


def is_push_ready(
    ball: dict | None,
    goal_cx: float | None,
    min_radius: float = 45.0,
    max_dx: float = 85.0,
) -> bool:
    if not ball or goal_cx is None:
        return False
    if float(ball.get("r", 0.0)) < float(min_radius):
        return False
    return abs(float(ball.get("cx", 0.0)) - float(goal_cx)) <= float(max_dx)


def scored_goal_color(ball: dict | None, goals: dict, target_key: str) -> str | None:
    if target_key not in {"blue", "yellow"}:
        return None
    if not goals.get(target_key, False):
        return None
    if is_ball_inside_goal(
        ball,
        goals.get(f"{target_key}_bbox"),
        x_margin_ratio=0.0,
        y_margin_ratio=1.0,
    ):
        return target_key
    return None


def scored_goal_color_after_push(
    ball: dict | None,
    goals: dict,
    target_key: str,
    push_until: float,
    now: float,
) -> str | None:
    if float(push_until) < float(now):
        return None
    return scored_goal_color(ball, goals, target_key)
