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


def is_confirmed_ball_streak(streak: int, min_frames: int = 3) -> bool:
    return int(streak) >= int(min_frames)


def update_confirmation_streak(streak: int, detected: bool) -> int:
    if detected:
        return int(streak) + 2
    return max(0, int(streak) - 1)


def should_allow_initial_track(
    ball: dict | None,
    streak: int,
    min_streak: int = 3,
    max_initial_radius: float = 45.0,
) -> bool:
    if ball is None:
        return False
    if not is_confirmed_ball_streak(streak, min_streak):
        return False
    return float(ball.get("r", 0.0)) <= float(max_initial_radius)


def should_allow_push_commit(streak: int, min_streak: int = 5) -> bool:
    return is_confirmed_ball_streak(streak, min_streak)


def should_accept_goal_edge_ball(
    ball: dict | None,
    goal_cx: float | None,
    min_radius: float = 8.0,
    max_ball_goal_dx: float = 80.0,
) -> bool:
    if ball is None or goal_cx is None:
        return False
    if ball.get("source") != "hsv":
        return False
    if float(ball.get("r", 0.0)) < min_radius:
        return False
    return abs(float(ball.get("cx", 0.0)) - float(goal_cx)) <= max_ball_goal_dx


def should_accept_goal_in_attack_context(
    goal_cx: float | None,
    goal_bbox: list[int] | tuple[int, int, int, int] | None,
    frame_width: float,
    min_edge_width_ratio: float = 0.07,
) -> bool:
    if goal_cx is None or goal_bbox is None:
        return False
    x, _y, w, _h = [float(v) for v in goal_bbox]
    touches_edge = x <= 0.0 or x + w >= float(frame_width)
    if touches_edge and w < float(frame_width) * float(min_edge_width_ratio):
        return False
    return True


def should_accept_ball_in_attack_context(
    ball: dict | None,
    target_goal_visible: bool,
    opponent_goal_visible: bool,
) -> bool:
    if ball is None:
        return False
    return bool(target_goal_visible) or not bool(opponent_goal_visible)


def should_accept_tracked_ball_measurement(
    ball: dict | None,
    last_cx: float,
    last_seen_t: float,
    now: float,
    frame_width: float,
    last_r: float | None = None,
    allowed_sources: tuple[str, ...] = ("hsv", "yolo"),
    max_jump_ratio: float = 0.18,
    max_jump_per_s: float = 260.0,
    max_recent_age_s: float = 0.70,
    weak_lock_radius: float = 14.0,
    weak_lock_max_age_s: float = 0.35,
    allow_large_jump: bool = False,
    large_jump_min_radius: float = 14.0,
) -> bool:
    if ball is None:
        return False
    if ball.get("source") not in allowed_sources:
        return False
    if float(last_cx) <= 0.0 or float(last_seen_t) <= 0.0:
        return True

    age = max(0.0, float(now) - float(last_seen_t))
    if age > float(max_recent_age_s):
        return True
    if (
        last_r is not None
        and float(last_r) < float(weak_lock_radius)
        and age <= float(weak_lock_max_age_s)
    ):
        return float(ball.get("r", 0.0)) >= float(weak_lock_radius) * 0.85
    if bool(allow_large_jump) and float(ball.get("r", 0.0)) >= float(large_jump_min_radius):
        return True

    max_jump = float(frame_width) * float(max_jump_ratio) + float(max_jump_per_s) * age
    return abs(float(ball.get("cx", 0.0)) - float(last_cx)) <= max_jump


def should_reset_track_after_jump_rejections(
    rejection_streak: int,
    max_rejections: int = 2,
) -> bool:
    return int(rejection_streak) >= int(max_rejections)


def should_goal_guided_coast(
    last_ball_seen_t: float,
    last_ball_r: float,
    goal_cx: float | None,
    goal_seen_t: float,
    now: float,
    line_detected: bool,
    max_ball_age_s: float = 0.7,
    max_goal_age_s: float = 1.2,
    min_ball_radius: float = 10.0,
) -> bool:
    if bool(line_detected):
        return False
    if goal_cx is None:
        return False
    if float(last_ball_seen_t) <= 0.0 or float(goal_seen_t) <= 0.0:
        return False
    if float(now) - float(last_ball_seen_t) > float(max_ball_age_s):
        return False
    if float(now) - float(goal_seen_t) > float(max_goal_age_s):
        return False
    return float(last_ball_r) >= float(min_ball_radius)


def should_hold_track_on_miss(miss_streak: int, max_miss_frames: int = 8) -> bool:
    return 0 < miss_streak <= max_miss_frames


def is_confirmed_line(line_streak: int, min_streak: int = 2) -> bool:
    return line_streak >= min_streak


def should_attack_through_line(
    ball: dict | None,
    goal_cx: float | None,
    line_detected: bool,
    min_radius: float = 8.0,
    max_ball_goal_dx: float = 100.0,
    allow_dribble_prediction: bool = False,
) -> bool:
    if not line_detected:
        return False
    if allow_dribble_prediction:
        return True
    if goal_cx is None:
        return False
    if not is_trackable_ball(ball, min_radius=min_radius):
        return False
    return abs(float(ball.get("cx", 0.0)) - float(goal_cx)) <= max_ball_goal_dx


def should_hold_without_ball_near_line(
    ball_visible: bool,
    line_detected: bool,
    line_cooldown: int,
    allow_dribble_prediction: bool = False,
    goal_cx: float | None = None,
    hold_ball_without_goal: bool = False,
) -> bool:
    del line_detected
    if allow_dribble_prediction:
        return False
    if int(line_cooldown) <= 0:
        return False
    if not ball_visible:
        return True
    return bool(hold_ball_without_goal) and goal_cx is None


def effective_goal_radius(raw_radius: float, filtered_radius: float) -> float:
    return max(float(raw_radius), float(filtered_radius))


def should_commit_push(now: float, push_until: float) -> bool:
    return float(now) < float(push_until)


def should_continue_dribble_push(
    ball_visible: bool,
    ball: dict | None,
    goal_cx: float | None,
    now: float,
    dribble_until: float,
    min_radius: float = 14.0,
) -> bool:
    del goal_cx
    if not ball_visible or ball is None:
        return False
    if float(now) >= float(dribble_until):
        return False
    return float(ball.get("r", 0.0)) >= float(min_radius)


def should_continue_dribble_prediction(
    goal_cx: float | None,
    now: float,
    dribble_until: float,
    last_seen_t: float,
    last_valid_r: float,
    min_radius: float = 14.0,
    max_age_s: float = 0.45,
) -> bool:
    del goal_cx
    if float(now) >= float(dribble_until):
        return False
    if float(last_seen_t) <= 0.0:
        return False
    if float(now) - float(last_seen_t) > float(max_age_s):
        return False
    return float(last_valid_r) >= float(min_radius)


def update_goal_memory(
    current_cx: float | None,
    last_cx: float | None,
    last_ts: float,
    now: float,
    frame_width: float,
    max_jump_ratio: float = 0.35,
    max_jump_per_s: float = 240.0,
    max_age_s: float = 2.0,
) -> tuple[float | None, float, bool]:
    if current_cx is None:
        if last_cx is not None and float(now) - float(last_ts) <= max_age_s:
            return last_cx, last_ts, False
        return None, last_ts, False

    current = float(current_cx)
    if last_cx is None or last_ts <= 0.0:
        return current, float(now), True

    age = max(0.0, float(now) - float(last_ts))
    if age > max_age_s:
        return current, float(now), True

    frame_center = float(frame_width) * 0.5
    left_zone = float(frame_width) * 0.35
    right_zone = float(frame_width) * 0.65
    last = float(last_cx)
    fresh_opposite_side_flip = (
        (current <= left_zone and last >= right_zone)
        or (current >= right_zone and last <= left_zone)
        or ((current - frame_center) * (last - frame_center) < 0.0 and abs(current - last) > frame_center)
    )
    if fresh_opposite_side_flip:
        return last_cx, last_ts, False

    max_jump = float(frame_width) * float(max_jump_ratio) + float(max_jump_per_s) * age
    if abs(current - float(last_cx)) > max_jump:
        return last_cx, last_ts, False
    return current, float(now), True


def update_goal_flip_candidate(
    current_cx: float | None,
    remembered_cx: float | None,
    pending_cx: float | None,
    pending_count: int,
    pending_ts: float,
    now: float,
    frame_width: float,
    remembered_ts: float = 0.0,
    confirm_frames: int = 3,
    tolerance_px: float = 45.0,
    max_pending_age_s: float = 0.7,
    edge_margin_ratio: float = 0.15,
    min_remembered_age_s: float = 2.0,
) -> tuple[float | None, int, float, bool]:
    if current_cx is None or remembered_cx is None:
        return None, 0, 0.0, False
    if float(remembered_ts) > 0.0 and float(now) - float(remembered_ts) < float(min_remembered_age_s):
        return None, 0, 0.0, False

    current = float(current_cx)
    remembered = float(remembered_cx)
    edge_margin = float(frame_width) * float(edge_margin_ratio)
    if current < edge_margin or current > float(frame_width) - edge_margin:
        return None, 0, 0.0, False

    center = float(frame_width) * 0.5
    opposite_side = (current - center) * (remembered - center) < 0.0
    if not opposite_side or abs(current - remembered) <= center:
        return None, 0, 0.0, False

    pending_is_recent = float(now) - float(pending_ts) <= float(max_pending_age_s)
    if (
        pending_cx is not None
        and pending_is_recent
        and abs(current - float(pending_cx)) <= float(tolerance_px)
    ):
        count = int(pending_count) + 1
        candidate = float(pending_cx)
    else:
        count = 1
        candidate = current

    accepted = count >= int(confirm_frames)
    return candidate, count, float(now), accepted


def update_goal_y_memory(
    current_cy: float | None,
    last_cy: float | None,
    remembered_cx: float | None,
    goal_accepted: bool,
) -> float | None:
    if remembered_cx is None:
        return None
    if current_cy is not None and goal_accepted:
        return float(current_cy)
    return last_cy


def should_use_goal_memory_for_attack(
    target_goal_visible: bool,
    opponent_goal_visible: bool,
    goal_conflict: bool = False,
) -> bool:
    if bool(goal_conflict):
        return False
    return bool(target_goal_visible) or not bool(opponent_goal_visible)


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
