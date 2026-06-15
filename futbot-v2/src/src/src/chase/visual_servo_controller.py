from __future__ import annotations

import math
import time


class BallPredictor:
    def __init__(self, max_horizon_s: float = 0.18, blend: float = 0.6) -> None:
        self._cx = 0.0
        self._r = 0.0
        self._vx = 0.0
        self._vr = 0.0
        self._last_t: float = 0.0
        self._initialized = False
        self._max_horizon = max_horizon_s
        self._blend = blend

    def update(self, cx: float, r: float, t: float) -> tuple[float, float]:
        if not self._initialized:
            self._cx = cx
            self._r = r
            self._last_t = t
            self._initialized = True
            return cx, r

        dt = t - self._last_t
        if dt < 1e-6:
            return self._cx, self._r

        raw_vx = (cx - self._cx) / dt
        raw_vr = (r - self._r) / dt
        self._vx = self._blend * raw_vx + (1.0 - self._blend) * self._vx
        self._vr = self._blend * raw_vr + (1.0 - self._blend) * self._vr
        self._cx = cx
        self._r = r
        self._last_t = t
        return cx, r

    def predict(self, horizon_s: float) -> tuple[float, float]:
        if not self._initialized:
            return self._cx, self._r
        h = min(horizon_s, self._max_horizon)
        return self._cx + self._vx * h, self._r + self._vr * h

    def velocity(self) -> tuple[float, float]:
        return self._vx, self._vr


class Kalman1D:
    def __init__(self, q: float = 0.5, r: float = 4.0) -> None:
        self.q = q
        self.r = r
        self.x = 0.0
        self.p = 1.0
        self._initialized = False

    def update(self, measurement: float) -> float:
        if not self._initialized:
            self.x = measurement
            self._initialized = True
            return self.x

        self.p += self.q
        k = self.p / (self.p + self.r)
        self.x += k * (measurement - self.x)
        self.p *= 1.0 - k
        return self.x


def should_push_ball(
    radius: float,
    theta: float,
    streak: int,
    kick_radius: float = 65.0,
    align_threshold: float = 0.08,
) -> bool:
    return streak >= 3 and radius >= kick_radius and abs(theta) < align_threshold


def is_trackable_ball(
    ball: dict | None,
    min_radius: float = 8.0,
    allowed_sources: tuple[str, ...] = ("hsv",),
) -> bool:
    if ball is None:
        return False
    return ball.get("source") in allowed_sources and float(ball.get("r", 0.0)) >= min_radius


def should_accept_goal_edge_ball(
    ball: dict | None,
    goal_cx: float | None,
    min_radius: float = 5.0,
    max_ball_goal_dx: float = 80.0,
) -> bool:
    if ball is None or goal_cx is None:
        return False
    if ball.get("source") != "hsv":
        return False
    if float(ball.get("r", 0.0)) < min_radius:
        return False
    return abs(float(ball.get("cx", 0.0)) - float(goal_cx)) <= max_ball_goal_dx


def should_hold_track_on_miss(miss_streak: int, max_miss_frames: int = 8) -> bool:
    return 0 < miss_streak <= max_miss_frames


def is_confirmed_line(line_streak: int, min_streak: int = 2) -> bool:
    return line_streak >= min_streak


def should_attack_through_line(
    ball: dict | None,
    goal_cx: float | None,
    line_detected: bool,
    min_radius: float = 8.0,
    max_ball_goal_dx: float = 80.0,
) -> bool:
    if not line_detected or goal_cx is None:
        return False
    if not is_trackable_ball(ball, min_radius=min_radius):
        return False
    return abs(float(ball.get("cx", 0.0)) - float(goal_cx)) <= max_ball_goal_dx


def should_hold_without_ball_near_line(
    ball_visible: bool,
    line_detected: bool,
    line_cooldown: int,
) -> bool:
    return not ball_visible and (line_detected or line_cooldown > 0)


def effective_goal_radius(raw_radius: float, filtered_radius: float) -> float:
    return max(float(raw_radius), float(filtered_radius))


def should_commit_push(now: float, push_until: float) -> bool:
    return float(now) < float(push_until)


class TurnHysteresis:
    def __init__(
        self,
        enter_threshold: float = 0.10,
        exit_threshold: float = 0.04,
        sticky_frames: int = 4,
    ) -> None:
        self._enter = enter_threshold
        self._exit = exit_threshold
        self._sticky = sticky_frames
        self._sign: int = 0
        self._sticky_count = 0

    def filter(self, theta: float) -> float:
        sign_theta = 1 if theta > 0 else -1 if theta < 0 else 0
        abs_theta = abs(theta)

        if self._sign == 0:
            if abs_theta >= self._enter:
                self._sign = sign_theta
                self._sticky_count = 0
        elif sign_theta == self._sign:
            self._sticky_count = 0
        elif sign_theta != 0 and sign_theta != self._sign:
            if abs_theta >= self._enter and self._sticky_count >= self._sticky:
                self._sign = sign_theta
                self._sticky_count = 0
            elif abs_theta < self._exit and self._sticky_count >= self._sticky:
                self._sign = 0
                self._sticky_count = 0
            else:
                self._sticky_count += 1

        if self._sign != 0 and sign_theta != 0 and sign_theta != self._sign:
            return self._sign * abs_theta
        return theta

    @property
    def active_sign(self) -> int:
        return self._sign


class VisualServoController:
    def __init__(
        self,
        center_x: float,
        f_eff: float = 5500.0,
        r_desired: float = 60.0,
        kp_theta: float = 60.0,
        kp_dist: float = 70.0,
        v_min: float = 65.0,
        v_max: float = 110.0,
        base_forward: float = 65.0,
        theta_deadband: float = 0.06,
        turn_ratio_max: float = 0.55,
        turn_ratio_boost_gain: float = 0.35,
        turn_ratio_hard_max: float = 0.92,
        min_alignment_speed_ratio: float = 0.30,
        alignment_slowdown_gain: float = 0.85,
        min_wheel_forward: float = 12.0,
        proximity_turn_scale: float = 0.5,
        proximity_r_threshold: float = 50.0,
    ) -> None:
        self.center_x = center_x
        self.f_eff = f_eff
        self.r_desired = r_desired
        self.kp_theta = kp_theta
        self.kp_dist = kp_dist
        self.v_min = v_min
        self.v_max = v_max
        self.base_forward = base_forward
        self.theta_deadband = theta_deadband
        self.turn_ratio_max = turn_ratio_max
        self.turn_ratio_boost_gain = turn_ratio_boost_gain
        self.turn_ratio_hard_max = turn_ratio_hard_max
        self.min_alignment_speed_ratio = min_alignment_speed_ratio
        self.alignment_slowdown_gain = alignment_slowdown_gain
        self.min_wheel_forward = min_wheel_forward
        self.proximity_turn_scale = proximity_turn_scale
        self.proximity_r_threshold = proximity_r_threshold

    def compute(self, cx: float, r: float, dt: float) -> tuple[float, float]:
        del dt

        theta_error = (cx - self.center_x) / self.center_x

        z_current = self.f_eff / r if r > 0 else float("inf")
        z_desired = self.f_eff / self.r_desired if self.r_desired > 0 else float("inf")
        if z_current == float("inf"):
            dist_error = 0.0
        else:
            dist_error = (z_current - z_desired) / z_desired

        dist_error = max(-0.8, min(2.0, dist_error))

        v_nominal = self.base_forward + self.kp_dist * dist_error
        v_nominal = max(self.v_min, min(self.v_max, v_nominal))

        theta_abs = abs(theta_error)
        alignment_ratio = 1.0 - self.alignment_slowdown_gain * theta_abs
        alignment_ratio = max(self.min_alignment_speed_ratio, min(1.0, alignment_ratio))
        v_fwd = max(self.v_min * alignment_ratio, v_nominal * alignment_ratio)

        if abs(theta_error) < self.theta_deadband:
            turn = 0.0
        else:
            turn = self.kp_theta * theta_error

        turn_ratio = self.turn_ratio_max + self.turn_ratio_boost_gain * theta_abs
        turn_ratio = max(0.0, min(self.turn_ratio_hard_max, turn_ratio))
        turn_limit = turn_ratio * v_fwd

        if r >= self.proximity_r_threshold:
            proximity_factor = self.proximity_r_threshold / r
            turn_limit *= 1.0 - proximity_factor * (1.0 - self.proximity_turn_scale)

        traction_turn_limit = max(0.0, v_fwd - self.min_wheel_forward)
        turn_limit = min(turn_limit, traction_turn_limit)
        turn = max(-turn_limit, min(turn_limit, turn))

        v_left = v_fwd + turn
        v_right = -(v_fwd - turn)

        return v_left, v_right