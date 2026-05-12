from __future__ import annotations

from dataclasses import dataclass


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
        far_speed: float = 95.0,
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
        goal_push_radius: float = 45.0,
        near_radius: float = 55.0,
        line_retreat_speed: float = 145.0,
        min_wheel_forward: float = 20.0,
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
        self.near_radius = float(near_radius)
        self.line_retreat_speed = float(line_retreat_speed)
        self.min_wheel_forward = float(min_wheel_forward)

    def compute(
        self,
        ball_cx: float,
        ball_r: float,
        goal_cx: float | None,
        line_detected: bool,
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
        close_ratio = self._clamp((float(ball_r) - self.near_radius) / 25.0, 0.0, 1.0)

        if ball_r >= self.goal_push_radius and goal_cx is not None:
            turn = (
                ball_theta * self.ball_turn_gain * 0.45
                + goal_theta * self.goal_turn_gain * 0.75
            )
            turn = self._limit_turn(turn)
            return self._command(self.goal_push_speed, turn, "PUSH", "goal")

        if ball_r >= self.push_radius and abs(ball_theta) <= self.deadband * 1.8:
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

        speed_base = self.near_speed if close_ratio > 0.0 else self.far_speed
        speed = speed_base * (1.0 - 0.45 * min(1.0, abs(ball_theta)))
        speed = max(42.0, speed)
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

    def _command(self, speed: float, turn: float, mode: str, reason: str) -> BallGoalCommand:
        if speed > self.min_wheel_forward:
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
