from __future__ import annotations

from dataclasses import dataclass

from chase.attack_geometry import behind_ball_point, is_robot_near_behind_point, route_curve_points


@dataclass(frozen=True)
class BallGoalCommand:
    v_left: float
    v_right: float
    mode: str
    reason: str


class BallGoalController:
    def __init__(
        self,
        frame_width: float,
        far_speed: float = 120.0,
        near_speed: float = 70.0,
        push_speed: float = 165.0,
        goal_push_speed: float = 135.0,
        min_turn: float = 42.0,
        max_turn: float = 65.0,
        min_turn_theta: float = 0.25,
        ball_turn_gain: float = 72.0,
        goal_turn_gain: float = 42.0,
        deadband: float = 0.02,
        push_radius: float = 70.0,
        goal_push_radius: float = 30.0,
        align_arc_radius: float = 38.0,
        early_align_arc_radius: float = 16.0,
        align_arc_speed: float = 0.0,
        align_arc_route_min_radius: float = 8.0,
        align_arc_route_speed: float = 55.0,
        align_arc_route_bend: float = 55.0,
        align_arc_route_lookahead: float = 0.28,
        align_arc_route_max_turn: float = 30.0,
        dribble_push_min_radius: float = 14.0,
        dribble_push_speed: float = 115.0,
        push_behind_tolerance: float = 42.0,
        push_alignment_dx: float = 50.0,
        push_max_ball_theta: float = 0.50,
        near_radius: float = 55.0,
        line_retreat_speed: float = 145.0,
        min_wheel_forward: float = 20.0,
        frame_height: float = 240.0,
    ) -> None:
        self.frame_width = float(frame_width)
        self.center_x = self.frame_width / 2.0
        self.far_speed = float(far_speed)
        self.near_speed = float(near_speed)
        self.push_speed = float(push_speed)
        self.goal_push_speed = float(goal_push_speed)
        self.min_turn = float(min_turn)
        self.max_turn = float(max_turn)
        self.min_turn_theta = float(min_turn_theta)
        self.ball_turn_gain = float(ball_turn_gain)
        self.goal_turn_gain = float(goal_turn_gain)
        self.deadband = float(deadband)
        self.push_radius = float(push_radius)
        self.goal_push_radius = float(goal_push_radius)
        self.align_arc_radius = float(align_arc_radius)
        self.early_align_arc_radius = float(early_align_arc_radius)
        self.align_arc_speed = float(align_arc_speed)
        self.align_arc_route_min_radius = float(align_arc_route_min_radius)
        self.align_arc_route_speed = float(align_arc_route_speed)
        self.align_arc_route_bend = float(align_arc_route_bend)
        self.align_arc_route_lookahead = float(align_arc_route_lookahead)
        self.align_arc_route_max_turn = float(align_arc_route_max_turn)
        self.dribble_push_min_radius = float(dribble_push_min_radius)
        self.dribble_push_speed = float(dribble_push_speed)
        self.push_behind_tolerance = float(push_behind_tolerance)
        self.push_alignment_dx = float(push_alignment_dx)
        self.push_max_ball_theta = float(push_max_ball_theta)
        self.near_radius = float(near_radius)
        self.line_retreat_speed = float(line_retreat_speed)
        self.min_wheel_forward = float(min_wheel_forward)
        self.frame_height = float(frame_height)

    def compute(
        self,
        ball_cx: float,
        ball_r: float,
        goal_cx: float | None,
        line_detected: bool,
        *,
        ball_cy: float | None = None,
        goal_cy: float | None = None,
        frame_height: float | None = None,
        continue_push: bool = False,
    ) -> BallGoalCommand:
        if line_detected:
            return BallGoalCommand(
                v_left=-self.line_retreat_speed,
                v_right=self.line_retreat_speed,
                mode="LINE_ESCAPE",
                reason="line",
            )

        ball_theta = self._theta(ball_cx)
        goal_theta = self._theta(goal_cx) if goal_cx is not None else 0.0
        radius = float(ball_r)
        close_ratio = self._clamp((radius - 18.0) / max(1.0, self.near_radius - 18.0), 0.0, 1.0)

        if continue_push and radius >= self.dribble_push_min_radius:
            if goal_cx is None:
                turn = ball_theta * self.ball_turn_gain * 0.25
            else:
                goal_delta_theta = self._clamp(
                    (float(goal_cx) - float(ball_cx)) / self.center_x,
                    -1.0,
                    1.0,
                )
                if ball_theta * goal_delta_theta < 0.0 and abs(ball_theta) >= 0.08:
                    turn = ball_theta * self.ball_turn_gain * 0.55
                else:
                    turn = (
                        ball_theta * self.ball_turn_gain * 0.20
                        + goal_delta_theta * self.goal_turn_gain * 0.90
                    )
            turn = self._limit_turn(turn)
            return self._command(self.dribble_push_speed, turn, "PUSH", "dribble")

        if goal_cx is None:
            turn = ball_theta * self.ball_turn_gain
            if abs(ball_theta) >= self.deadband:
                turn = self._with_min_turn(turn, ball_theta)
            else:
                turn = 0.0
            turn = self._limit_turn(turn)
            speed_base = self.far_speed - (self.far_speed - self.near_speed) * close_ratio
            speed = speed_base * (1.0 - 0.45 * min(1.0, abs(ball_theta)))
            speed = max(42.0, speed)
            return self._command(speed, turn, "CHASE", "goal_missing")

        ball_goal_dx = abs(float(ball_cx) - float(goal_cx)) if goal_cx is not None else None
        goal_aligned = ball_goal_dx is not None and ball_goal_dx <= self.push_alignment_dx
        frame_h = self.frame_height if frame_height is None else float(frame_height)
        route_geometry_available = ball_cy is not None and goal_cy is not None

        push_positioned = True
        if route_geometry_available and goal_cx is not None:
            behind_x, behind_y = behind_ball_point(
                ball_cx=ball_cx,
                ball_cy=ball_cy,
                goal_cx=float(goal_cx),
                goal_cy=goal_cy,
            )
            push_positioned = is_robot_near_behind_point(
                robot_cx=self.center_x,
                robot_cy=max(0.0, frame_h - 1.0),
                behind_x=behind_x,
                behind_y=behind_y,
                tolerance=self.push_behind_tolerance,
            )
            if radius >= self.goal_push_radius and goal_aligned:
                push_positioned = True

        if (
            ball_r >= self.goal_push_radius
            and goal_aligned
            and push_positioned
            and abs(ball_theta) <= self.push_max_ball_theta
        ):
            goal_delta_theta = self._clamp(
                (float(goal_cx) - float(ball_cx)) / self.center_x,
                -1.0,
                1.0,
            )
            turn = (
                ball_theta * self.ball_turn_gain * 0.15
                + goal_delta_theta * self.goal_turn_gain * 0.95
            )
            turn = self._limit_turn(turn)
            return self._command(self.goal_push_speed, turn, "PUSH", "goal")

        if (
            ball_r >= self.push_radius
            and abs(ball_theta) <= self.deadband * 1.8
            and (goal_cx is None or goal_aligned)
            and push_positioned
        ):
            turn = goal_theta * self.goal_turn_gain if goal_cx is not None else 0.0
            turn = self._limit_turn(turn)
            return self._command(self.push_speed, turn, "PUSH", "goal" if goal_cx is not None else "aligned")

        blended_theta = (1.0 - close_ratio) * ball_theta + close_ratio * (
            0.65 * ball_theta + 0.35 * goal_theta
        )
        turn = blended_theta * self.ball_turn_gain
        if abs(ball_theta) >= self.deadband:
            turn = self._with_min_turn(turn, ball_theta)
        else:
            turn = 0.0
        turn = self._limit_turn(turn)

        speed_base = self.far_speed - (self.far_speed - self.near_speed) * close_ratio
        speed = speed_base * (1.0 - 0.45 * min(1.0, abs(ball_theta)))
        speed = max(42.0, speed)
        early_align_arc = (
            goal_cx is not None
            and not goal_aligned
            and radius >= self.early_align_arc_radius
            and ball_goal_dx is not None
            and ball_goal_dx >= 95.0
            and ball_theta * goal_theta < 0.0
        )
        route_align_arc = (
            goal_cx is not None
            and not goal_aligned
            and ball_cy is not None
            and goal_cy is not None
            and radius >= self.align_arc_route_min_radius
        )
        route_positioning_arc = (
            goal_cx is not None
            and goal_aligned
            and route_geometry_available
            and not push_positioned
            and radius >= self.align_arc_route_min_radius
        )
        align_arc = (
            goal_cx is not None
            and (
                (
                    not goal_aligned
                    and (radius >= self.align_arc_radius or early_align_arc or route_align_arc)
                )
                or route_positioning_arc
            )
        )
        if align_arc:
            if route_geometry_available:
                behind = behind_ball_point(
                    ball_cx=ball_cx,
                    ball_cy=ball_cy,
                    goal_cx=float(goal_cx),
                    goal_cy=goal_cy,
                )
                route = route_curve_points(
                    start=(self.center_x, max(0.0, frame_h - 1.0)),
                    end=behind,
                    bend=self.align_arc_route_bend,
                )
                lookahead_index = max(
                    1,
                    min(
                        len(route) - 1,
                        int(round((len(route) - 1) * self.align_arc_route_lookahead)),
                    ),
                )
                lookahead_x = route[lookahead_index][0]
                align_theta = self._theta(lookahead_x)
                turn = align_theta * self.ball_turn_gain
                if abs(align_theta) >= self.deadband:
                    turn = self._with_min_turn(turn, align_theta)
                else:
                    turn = 0.0
                turn = self._limit_turn(turn)
                if ball_theta * goal_theta > 0.0 and turn * ball_theta < 0.0:
                    turn = ball_theta * self.ball_turn_gain
                    if abs(ball_theta) >= self.deadband:
                        turn = self._with_min_turn(turn, ball_theta)
                    else:
                        turn = 0.0
                    turn = self._limit_turn(turn)
                turn = self._clamp(
                    turn,
                    -self.align_arc_route_max_turn,
                    self.align_arc_route_max_turn,
                )
                return self._command(
                    min(speed, self.align_arc_route_speed),
                    turn,
                    "ALIGN_ARC",
                    "route",
                    keep_forward=True,
                )

            goal_delta_theta = self._clamp(
                (float(goal_cx) - float(ball_cx)) / self.center_x,
                -1.0,
                1.0,
            )
            align_theta = -goal_delta_theta
            turn = align_theta * self.ball_turn_gain
            if abs(align_theta) >= self.deadband:
                turn = self._with_min_turn(turn, align_theta)
            else:
                turn = 0.0
            turn = self._limit_turn(turn)
            speed = min(speed, self.align_arc_speed)
            return self._command(speed, turn, "ALIGN_ARC", "ball", keep_forward=False)
        return self._command(speed, turn, "CHASE", "ball")

    def _theta(self, cx: float | None) -> float:
        if cx is None or self.center_x <= 0.0:
            return 0.0
        return self._clamp((float(cx) - self.center_x) / self.center_x, -1.0, 1.0)

    def _with_min_turn(self, turn: float, theta: float) -> float:
        sign = 1.0 if theta > 0.0 else -1.0
        turn_floor = self.min_turn * self._clamp(
            abs(theta) / self.min_turn_theta,
            0.0,
            1.0,
        )
        return sign * max(abs(turn), turn_floor)

    def _limit_turn(self, turn: float) -> float:
        return self._clamp(turn, -self.max_turn, self.max_turn)

    def _command(
        self,
        speed: float,
        turn: float,
        mode: str,
        reason: str,
        keep_forward: bool = True,
    ) -> BallGoalCommand:
        if keep_forward and speed > self.min_wheel_forward:
            turn = self._clamp(
                turn,
                -(speed - self.min_wheel_forward),
                speed - self.min_wheel_forward,
            )
        return BallGoalCommand(
            v_left=float(speed + turn),
            v_right=float(-(speed - turn)),
            mode=mode,
            reason=reason,
        )

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))
