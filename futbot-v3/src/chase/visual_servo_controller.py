from __future__ import annotations


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

        traction_turn_limit = max(0.0, v_fwd - self.min_wheel_forward)
        turn_limit = min(turn_limit, traction_turn_limit)
        turn = max(-turn_limit, min(turn_limit, turn))

        v_left = v_fwd + turn
        v_right = -(v_fwd - turn)

        return v_left, v_right
