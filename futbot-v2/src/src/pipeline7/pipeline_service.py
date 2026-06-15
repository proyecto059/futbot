import logging
import os
import time

from vision import HybridVisionService
from motors import MotorService
from chase.ball_goal_controller import BallGoalController
from chase.attack_geometry import scored_goal_color_after_push
from chase.visual_servo_controller import (
    BallPredictor,
    Kalman1D,
    TurnHysteresis,
    effective_goal_radius,
    is_confirmed_ball_streak,
    is_confirmed_line,
    is_trackable_ball,
    should_accept_ball_in_attack_context,
    should_accept_goal_edge_ball,
    should_accept_goal_in_attack_context,
    should_allow_initial_track,
    should_allow_push_commit,
    should_accept_tracked_ball_measurement,
    should_attack_through_line,
    should_commit_push,
    should_continue_dribble_prediction,
    should_continue_dribble_push,
    should_hold_without_ball_near_line,
    should_hold_track_on_miss,
    should_goal_guided_coast,
    should_reset_track_after_jump_rejections,
    should_use_goal_memory_for_attack,
    update_goal_flip_candidate,
    update_goal_memory,
    update_goal_y_memory,
    update_confirmation_streak,
)
from chase.search_operator import SearchOperator
from src.pipeline7.operators.avoid_wall_operator import AvoidWallOperator

log = logging.getLogger("turbopi.pipeline7")

TRACK = "TRACK"
PREDICT = "PREDICT"
LOCAL_REACQUIRE = "LOCAL_REACQUIRE"
FIELD_SEARCH = "FIELD_SEARCH"
WARMUP = "WARMUP"
CELEBRATE_360 = "CELEBRATE_360"
STOPPED = "STOPPED"


class Pipeline7Service:
    def __init__(self, vision: HybridVisionService, motors: MotorService) -> None:
        self._vision = vision
        self._motors = motors

        self._running = False
        self._state = WARMUP

        self._attack_blue = os.environ.get("ATTACK_BLUE", "1").strip().lower() not in {"0", "false", "no"}

        self._warmup_timeout = float(os.environ.get("WARMUP_TIMEOUT", "5.0"))
        self._local_reacquire_ms = int(os.environ.get("LOCAL_REACQUIRE_MS", "650"))
        self._local_memory_sec = float(os.environ.get("LOCAL_MEMORY_SEC", "1.4"))
        self._field_search_move_ms = int(os.environ.get("FIELD_SEARCH_MOVE_MS", "750"))
        self._field_search_pause_ms = int(os.environ.get("FIELD_SEARCH_PAUSE_MS", "180"))
        self._ball_visible_min_radius = float(os.environ.get("BALL_VISIBLE_MIN_RADIUS", "5.5"))
        self._ball_confirm_frames = int(os.environ.get("BALL_CONFIRM_FRAMES", "3"))
        self._push_confirm_frames = int(os.environ.get("PUSH_CONFIRM_FRAMES", "5"))
        self._search_max_initial_ball_radius = float(os.environ.get("SEARCH_MAX_INITIAL_BALL_RADIUS", "45.0"))
        self._goal_edge_ball_min_radius = float(os.environ.get("GOAL_EDGE_BALL_MIN_RADIUS", "8.0"))
        self._track_miss_hold_frames = int(os.environ.get("TRACK_MISS_HOLD_FRAMES", "8"))
        self._track_miss_hold_speed_scale = float(os.environ.get("TRACK_MISS_HOLD_SPEED_SCALE", "0.75"))
        self._track_miss_hold_turn_scale = float(os.environ.get("TRACK_MISS_HOLD_TURN_SCALE", "0.55"))
        self._push_commit_ms = int(os.environ.get("PUSH_COMMIT_MS", "600"))
        self._dribble_after_push_ms = int(os.environ.get("DRIBBLE_AFTER_PUSH_MS", "1200"))
        self._dribble_min_radius = float(os.environ.get("DRIBBLE_MIN_RADIUS", "14.0"))
        self._dribble_predict_max_age = float(os.environ.get("DRIBBLE_PREDICT_MAX_AGE", "0.45"))
        self._goal_coast_max_ball_age = float(os.environ.get("GOAL_COAST_MAX_BALL_AGE", "0.8"))
        self._goal_coast_max_goal_age = float(os.environ.get("GOAL_COAST_MAX_GOAL_AGE", "1.2"))
        self._goal_coast_min_ball_radius = float(os.environ.get("GOAL_COAST_MIN_BALL_RADIUS", "10.0"))
        self._goal_coast_max_speed = float(os.environ.get("GOAL_COAST_MAX_SPEED", "70.0"))
        self._goal_coast_max_turn = float(os.environ.get("GOAL_COAST_MAX_TURN", "30.0"))
        self._goal_confirm_frames = int(os.environ.get("GOAL_CONFIRM_FRAMES", "5"))
        self._spin_360_ms = int(os.environ.get("SPIN_360_MS", "4000"))
        self._spin_360_speed = float(os.environ.get("SPIN_360_SPEED", "120"))
        self._line_streak_min = 2
        self._line_retreat_speed = 150
        self._line_retreat_ms = 400
        self._line_turn_ms = 300
        self._line_cooldown_frames = 60
        self._predict_timeout_s = 0.50
        self._predict_turn_abs_limit = 55.0
        self._cache_turn_scale = 0.30
        self._cache_speed_scale = 0.80
        self._prediction_speed_scale = 0.70
        self._prediction_turn_scale = 0.50

        frame_w = self._vision.frame_width
        self._half = frame_w / 2.0
        self._controller = BallGoalController(frame_width=frame_w)
        self._kalman_cx = Kalman1D(q=2.6, r=1.0)
        self._kalman_r = Kalman1D(q=0.9, r=1.5)
        self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
        self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
        self._search = SearchOperator()
        self._avoid_wall_op = AvoidWallOperator()
        self._reset_state()

    def _reset_state(self) -> None:
        self._last_v_left = 0.0
        self._last_v_right = 0.0
        self._last_turn = 0.0
        self._prev_hys_sign = 0
        self._miss_streak = 0
        self._jump_reject_streak = 0
        self._tick = 0
        self._tick_start = 0.0
        self._fps_start = time.monotonic()
        self._fps_count = 0
        self._warmup_start = time.monotonic()
        self._loss_start_t = 0.0
        self._last_valid_w = 0.0
        self._last_valid_v = 0.0
        self._last_valid_cx = 0.0
        self._last_valid_r = 0.0
        self._last_seen_t = 0.0
        self._search_phase_start = 0.0
        self._search_step_index = 0
        self._search_burst_sent = False
        self._search_phase = "move"
        self._line_streak = 0
        self._line_cooldown = 0
        self._line_phase = ""
        self._line_phase_start = 0.0
        self._last_line_cx = None
        self._kick_streak = 0
        self._last_kick_r = 0.0
        self._ball_streak = 0
        self._last_goal_cx = None
        self._last_goal_cy = None
        self._last_goal_ts = 0.0
        self._pending_goal_flip_cx = None
        self._pending_goal_flip_count = 0
        self._pending_goal_flip_ts = 0.0
        self._push_until = 0.0
        self._dribble_until = 0.0
        self._last_push_v_left = 0.0
        self._last_push_v_right = 0.0
        self._goal_scored_streak = 0
        self._goal_scored_color = None
        self._celebrate_start = 0.0

    def _drive(self, vL: float, vR: float, dur_ms: int) -> None:
        self._motors.drive(vL, vR, dur_ms)

    def tick(self) -> None:
        now = time.monotonic()
        snap = self._vision.tick()

        # Capa de seguridad: evasion de muros negros
        frame = self._vision.last_frame()
        evasion = self._avoid_wall_op.check_and_avoid(frame)
        if evasion is not None:
            vL, vR, dur_ms = evasion
            self._motors.drive(vL, vR, dur_ms)
            if self._tick % 5 == 0:
                log.info("event=avoid_wall_activated action=evading")
            self._tick += 1
            return

        ball = snap.get("ball")

        if ball is None:
            source = "none"
            cx = None
            r = None
        else:
            source = ball.get("source", "hsv")
            cx = ball["cx"]
            r = ball["r"]

        target_key = "blue" if self._attack_blue else "yellow"
        opponent_key = "yellow" if self._attack_blue else "blue"
        goals_now = snap.get("goals", {})
        target_goal_visible = bool(goals_now.get(target_key, False))
        opponent_goal_visible = bool(goals_now.get(opponent_key, False))
        target_goal_cx_raw = goals_now.get("{}_cx".format(target_key))
        target_goal_cy_raw = goals_now.get("{}_cy".format(target_key))
        target_goal_bbox_raw = goals_now.get("{}_bbox".format(target_key))
        if not should_accept_goal_in_attack_context(
            target_goal_cx_raw,
            target_goal_bbox_raw,
            self._vision.frame_width,
        ):
            target_goal_visible = False
            target_goal_cx_raw = None
            target_goal_cy_raw = None
        remembered_goal_cx, remembered_goal_ts, goal_accepted = update_goal_memory(
            target_goal_cx_raw,
            self._last_goal_cx,
            self._last_goal_ts,
            now,
            self._vision.frame_width,
        )
        goal_conflict = False
        if target_goal_cx_raw is None or goal_accepted:
            self._pending_goal_flip_cx = None
            self._pending_goal_flip_count = 0
            self._pending_goal_flip_ts = 0.0
        elif not goal_accepted:
            goal_conflict = True
            (
                self._pending_goal_flip_cx,
                self._pending_goal_flip_count,
                self._pending_goal_flip_ts,
                goal_flip_accepted,
            ) = update_goal_flip_candidate(
                target_goal_cx_raw,
                remembered_goal_cx,
                self._pending_goal_flip_cx,
                self._pending_goal_flip_count,
                self._pending_goal_flip_ts,
                now,
                self._vision.frame_width,
                remembered_ts=remembered_goal_ts,
            )
            if goal_flip_accepted:
                remembered_goal_cx = float(target_goal_cx_raw)
                remembered_goal_ts = now
                goal_accepted = True
                goal_conflict = False
                self._pending_goal_flip_cx = None
                self._pending_goal_flip_count = 0
                self._pending_goal_flip_ts = 0.0
                log.info("GOAL flip accepted raw=%.0f", float(target_goal_cx_raw))
        if (
            target_goal_cx_raw is not None
            and remembered_goal_cx is not None
            and not goal_accepted
            and self._tick % 10 == 0
        ):
            log.info("GOAL jump rejected raw=%.0f keep=%.0f", float(target_goal_cx_raw), float(remembered_goal_cx))
        self._last_goal_cx = remembered_goal_cx
        self._last_goal_ts = remembered_goal_ts
        self._last_goal_cy = update_goal_y_memory(
            target_goal_cy_raw,
            self._last_goal_cy,
            remembered_goal_cx,
            goal_accepted,
        )
        use_goal_memory = should_use_goal_memory_for_attack(
            target_goal_visible,
            opponent_goal_visible,
            goal_conflict=goal_conflict,
        )
        target_goal_cx_now = self._last_goal_cx if use_goal_memory else None
        target_goal_cy_now = self._last_goal_cy if use_goal_memory else None

        if self._state not in (CELEBRATE_360, STOPPED):
            scored_color_now = scored_goal_color_after_push(
                ball,
                goals_now,
                target_key,
                push_until=self._push_until,
                now=now,
            )
            if scored_color_now is not None:
                if scored_color_now == self._goal_scored_color:
                    self._goal_scored_streak += 1
                else:
                    self._goal_scored_color = scored_color_now
                    self._goal_scored_streak = 1
            else:
                self._goal_scored_streak = 0
                self._goal_scored_color = None

        if self._state not in (CELEBRATE_360, STOPPED) and self._goal_scored_streak >= self._goal_confirm_frames:
            self._state = CELEBRATE_360
            self._celebrate_start = now
            self._push_until = 0.0
            self._dribble_until = 0.0
            log.info("GOAL scored color=%s -> CELEBRATE_360", self._goal_scored_color)

        accept_ball_context = should_accept_ball_in_attack_context(
            ball,
            target_goal_visible=target_goal_visible,
            opponent_goal_visible=opponent_goal_visible,
        )
        if not accept_ball_context and ball is not None:
            self._ball_streak = 0
            self._miss_streak = 0
            self._jump_reject_streak = 0
            self._last_valid_w = 0.0
            self._last_valid_v = 0.0
            self._last_valid_cx = 0.0
            self._last_valid_r = 0.0
            self._last_seen_t = 0.0
            self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
            self._kalman_cx = Kalman1D(q=2.6, r=1.0)
            self._kalman_r = Kalman1D(q=0.9, r=1.5)
            self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
            if self._tick % 10 == 0:
                log.info("BALL rejected: opponent goal only cx=%.0f r=%.0f", float(cx), float(r))

        frame_width = self._vision.frame_width
        raw_ball_detected = accept_ball_context and (
            is_trackable_ball(ball, min_radius=self._ball_visible_min_radius)
            or should_accept_goal_edge_ball(
                ball, goal_cx=target_goal_cx_now, min_radius=self._goal_edge_ball_min_radius,
            )
        )
        self._ball_streak = update_confirmation_streak(self._ball_streak, raw_ball_detected)

        has_recent_memory = self._last_seen_t > 0.0 and (now - self._last_seen_t) <= self._local_memory_sec
        ball_confirmed = is_confirmed_ball_streak(self._ball_streak, min_frames=self._ball_confirm_frames)
        if self._state == TRACK or has_recent_memory:
            ball_visible = raw_ball_detected and ball_confirmed
        else:
            ball_visible = should_allow_initial_track(
                ball,
                streak=self._ball_streak,
                min_streak=self._ball_confirm_frames,
                max_initial_radius=self._search_max_initial_ball_radius,
            )
        push_commit_active = should_commit_push(now, self._push_until)

        if self._state == STOPPED:
            self._motors.stop(120)
            self._tick += 1
            time.sleep(0.05)
            return

        if self._state == CELEBRATE_360:
            elapsed_ms = int((now - self._celebrate_start) * 1000.0)
            if elapsed_ms < self._spin_360_ms:
                self._drive(self._spin_360_speed, self._spin_360_speed, 80)
                if self._tick % 15 == 0:
                    log.info("CELEBRATE_360 color=%s t=%dms/%dms", self._goal_scored_color, elapsed_ms, self._spin_360_ms)
            else:
                self._motors.stop(200)
                self._state = STOPPED
                log.info("CELEBRATE_360 done -> STOPPED")
            self._tick += 1
            time.sleep(0.01)
            return

        if self._line_cooldown > 0 and not push_commit_active:
            self._line_cooldown -= 1
            self._line_streak = 0

        dribble_prediction_active = should_continue_dribble_prediction(
            goal_cx=self._last_goal_cx,
            now=now,
            dribble_until=self._dribble_until,
            last_seen_t=self._last_seen_t,
            last_valid_r=self._last_valid_r,
            min_radius=self._dribble_min_radius,
            max_age_s=self._dribble_predict_max_age,
        )

        if push_commit_active:
            self._drive(self._last_push_v_left, self._last_push_v_right, 80)
            if self._tick % 10 == 0:
                remaining_ms = int(max(0.0, self._push_until - now) * 1000.0)
                log.info("PUSH commit remaining=%dms vL=%.0f vR=%.0f", remaining_ms, self._last_push_v_left, self._last_push_v_right)
            self._tick += 1
            time.sleep(0.01)
            return

        if self._line_phase == "retreat":
            if now - self._line_phase_start >= self._line_retreat_ms / 1000.0:
                if self._last_line_cx is not None and self._last_line_cx < self._half:
                    self._drive(110, 55, self._line_turn_ms)
                else:
                    self._drive(-55, -110, self._line_turn_ms)
                if self._tick % 5 == 0:
                    log.info("LINE turn dir=%s", "right" if (self._last_line_cx is not None and self._last_line_cx < self._half) else "left")
                self._line_phase = "turn"
                self._line_phase_start = now
        elif self._line_phase == "turn":
            if now - self._line_phase_start >= self._line_turn_ms / 1000.0:
                self._line_phase = "escape"
                self._line_phase_start = now
        elif self._line_phase == "escape":
            if now - self._line_phase_start >= 0.05:
                self._line_cooldown = self._line_cooldown_frames
                self._line_streak = 0
                self._line_phase = ""
                self._state = LOCAL_REACQUIRE if has_recent_memory else FIELD_SEARCH
                self._search_phase_start = now
                self._search_burst_sent = False
                self._miss_streak = 0

        if self._line_cooldown <= 0 and self._line_phase == "":
            line_snap = snap.get("line", {})
            line_detected = bool(line_snap.get("detected", False))
            line_cx = line_snap.get("cx")
            line_cy = line_snap.get("cy")
            line_pixels = line_snap.get("pixels", 0)
            if line_detected:
                if line_cx is not None:
                    self._last_line_cx = line_cx
                self._line_streak += 1
                if self._tick % 5 == 0:
                    log.info("LINE streak=%d cx=%s pixels=%d", self._line_streak, "{:.0f}".format(line_cx) if line_cx is not None else "none", line_pixels)
            else:
                self._line_streak = 0
            line_confirmed = is_confirmed_line(self._line_streak, self._line_streak_min)
            if line_confirmed:
                if should_attack_through_line(
                    ball,
                    goal_cx=target_goal_cx_now,
                    line_detected=True,
                    min_radius=self._ball_visible_min_radius,
                    allow_dribble_prediction=dribble_prediction_active and use_goal_memory,
                ):
                    if self._tick % 5 == 0:
                        log.info("LINE suppressed: ball+goal attack cx=%s goal=%s", cx, int(target_goal_cx_now) if target_goal_cx_now is not None else "none")
                    self._line_streak = 0
                else:
                    log.info("LINE DETECTED retreating %dms", self._line_retreat_ms)
                    self._drive(-self._line_retreat_speed, self._line_retreat_speed, self._line_retreat_ms)
                    self._line_phase = "retreat"
                    self._line_phase_start = now

        if self._line_phase:
            self._tick += 1
            time.sleep(0.01)
            return

        if should_hold_without_ball_near_line(
            ball_visible,
            bool(snap.get("line", {}).get("detected", False)),
            self._line_cooldown,
            allow_dribble_prediction=dribble_prediction_active and use_goal_memory,
            goal_cx=target_goal_cx_now,
            hold_ball_without_goal=True,
        ):
            self._motors.stop(80)
            if self._tick % 10 == 0:
                log.info("LINE hold: no ball, no blind search")
            self._tick += 1
            time.sleep(0.01)
            return

        if ball_visible and not self._line_phase:
            self._miss_streak = 0
            if self._state in (PREDICT, LOCAL_REACQUIRE, FIELD_SEARCH, WARMUP):
                if self._tick % 10 == 0:
                    log.info("pelota recuperada src=%s r=%.0f -> TRACK", source, r)
                self._state = TRACK
                self._loss_start_t = 0.0
                self._search_step_index = 0
                self._prev_hys_sign = 0
                self._last_turn = 0

        if self._state == WARMUP:
            elapsed_warmup = now - self._warmup_start
            if ball_visible or elapsed_warmup >= self._warmup_timeout:
                reason = "ball" if ball_visible else "timeout"
                log.info("WARMUP done t=%.1fs (%s) -> FIELD_SEARCH", elapsed_warmup, reason)
                self._state = FIELD_SEARCH
                self._search_phase_start = now
                self._search_burst_sent = False
                self._search_phase = "move"

        elif self._state == TRACK:
            tracked_ball_visible = ball_visible
            reset_ball_filter = False
            if ball_visible:
                raw_jump = abs(float(ball["cx"]) - float(self._last_valid_cx)) if self._last_valid_cx > 0.0 else 0.0
                weak_last_lock = 0.0 < float(self._last_valid_r) < self._dribble_min_radius
                dribble_reacquire = (
                    dribble_prediction_active
                    and raw_jump > frame_width * 0.25
                    and float(ball.get("r", 0.0)) >= self._ball_visible_min_radius
                )
                tracked_ball_visible = should_accept_tracked_ball_measurement(
                    ball,
                    last_cx=self._last_valid_cx,
                    last_seen_t=self._last_seen_t,
                    now=now,
                    frame_width=frame_width,
                    last_r=self._last_valid_r,
                    allow_large_jump=dribble_reacquire,
                    large_jump_min_radius=self._ball_visible_min_radius,
                )
                reset_ball_filter = tracked_ball_visible and (weak_last_lock or dribble_reacquire) and raw_jump > frame_width * 0.25
                if tracked_ball_visible:
                    self._jump_reject_streak = 0
                else:
                    self._jump_reject_streak += 1
                if not tracked_ball_visible and self._tick % 10 == 0:
                    log.info("BALL jump rejected raw=%.0f keep=%.0f age=%.2fs", float(cx), float(self._last_valid_cx), now - self._last_seen_t if self._last_seen_t > 0.0 else 0.0)
                if not tracked_ball_visible and should_reset_track_after_jump_rejections(self._jump_reject_streak):
                    coast_goal_cx = target_goal_cx_now if target_goal_cx_now is not None else self._last_goal_cx
                    coast_goal_cy = target_goal_cy_now if target_goal_cx_now is not None else self._last_goal_cy
                    line_now = bool(self._line_phase) or bool(snap.get("line", {}).get("detected", False))
                    goal_coast = should_goal_guided_coast(
                        last_ball_seen_t=self._last_seen_t,
                        last_ball_r=self._last_valid_r,
                        goal_cx=coast_goal_cx,
                        goal_seen_t=self._last_goal_ts,
                        now=now,
                        line_detected=line_now,
                        max_ball_age_s=self._goal_coast_max_ball_age,
                        max_goal_age_s=self._goal_coast_max_goal_age,
                        min_ball_radius=self._goal_coast_min_ball_radius,
                    )
                    if goal_coast:
                        coast_ball_cx = self._last_valid_cx if self._last_valid_cx > 0.0 else self._half
                        coast_ball_r = max(self._last_valid_r, self._goal_coast_min_ball_radius)
                        command = self._controller.compute(
                            ball_cx=coast_ball_cx,
                            ball_cy=None,
                            ball_r=coast_ball_r,
                            goal_cx=coast_goal_cx,
                            goal_cy=coast_goal_cy,
                            line_detected=False,
                            continue_push=False,
                        )
                        v_cmd = max(0.0, min((command.v_left - command.v_right) * 0.5, self._goal_coast_max_speed))
                        turn_cmd = (command.v_left + command.v_right) * 0.5
                        turn_cmd = max(-self._goal_coast_max_turn, min(self._goal_coast_max_turn, turn_cmd))
                        vL = v_cmd + turn_cmd
                        vR = -(v_cmd - turn_cmd)
                        self._last_valid_v = v_cmd
                        self._last_valid_w = turn_cmd
                        self._last_turn = turn_cmd
                        self._last_v_left = vL
                        self._last_v_right = vR
                        self._miss_streak = 0
                        self._ball_streak = 0
                        self._jump_reject_streak = 0
                        self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                        self._kalman_cx = Kalman1D(q=2.6, r=1.0)
                        self._kalman_r = Kalman1D(q=0.9, r=1.5)
                        self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                        self._drive(vL, vR, 80)
                        if self._tick % 5 == 0:
                            log.info("BALL track reset -> GOAL_COAST goal=%.0f last_ball=%.0f r=%.1f v=%.0f w=%+.0f", float(coast_goal_cx), float(coast_ball_cx), float(coast_ball_r), v_cmd, turn_cmd)
                        self._tick += 1
                        time.sleep(0.01)
                        return
                    self._last_valid_w = 0.0
                    self._last_valid_v = 0.0
                    self._last_valid_cx = 0.0
                    self._last_valid_r = 0.0
                    self._last_seen_t = 0.0
                    self._miss_streak = 0
                    self._ball_streak = 0
                    self._jump_reject_streak = 0
                    self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                    self._kalman_cx = Kalman1D(q=2.6, r=1.0)
                    self._kalman_r = Kalman1D(q=0.9, r=1.5)
                    self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                    self._motors.stop(80)
                    if self._tick % 5 == 0:
                        log.info("BALL track reset after jump rejects")
                    self._state = FIELD_SEARCH
                    self._search_phase_start = now
                    self._search_burst_sent = False
                    self._search_phase = "move"
                    self._tick += 1
                    time.sleep(0.01)
                    return
            if (tracked_ball_visible or dribble_prediction_active) and not self._line_phase:
                dt = now - self._tick_start if self._tick_start else 0.01
                self._tick_start = now
                if tracked_ball_visible:
                    command_source = source
                    cx_raw = ball["cx"]
                    cy_raw = ball.get("cy")
                    r_raw = ball["r"]
                    if reset_ball_filter:
                        self._kalman_cx = Kalman1D(q=2.6, r=1.0)
                        self._kalman_r = Kalman1D(q=0.9, r=1.5)
                        self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                        self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                    cx_f = self._kalman_cx.update(cx_raw)
                    r_f = self._kalman_r.update(r_raw)
                    if source in ("hsv", "yolo"):
                        self._predictor.update(cx_f, r_f, now)
                        self._last_valid_cx = cx_f
                        self._last_seen_t = now
                else:
                    command_source = "predict"
                    pred_cx, pred_r = self._predictor.predict(now - self._last_seen_t)
                    cx_f = pred_cx if pred_cx > 0.0 else self._last_valid_cx
                    r_f = max(pred_r, self._last_valid_r)
                    cx_raw = cx_f
                    cy_raw = None
                    r_raw = r_f
                theta_raw = (cx_f - self._half) / self._half
                theta_filtered = self._hysteresis.filter(theta_raw)
                cx_filtered = self._half + self._half * theta_filtered
                if tracked_ball_visible:
                    _, r_eff = self._predictor.predict(0.0)
                else:
                    _, r_eff = cx_f, r_f
                r_eff = effective_goal_radius(r_raw, r_eff)
                if dribble_prediction_active:
                    r_eff = max(r_eff, self._last_valid_r)
                continue_dribble = dribble_prediction_active or should_continue_dribble_push(
                    ball_visible=tracked_ball_visible,
                    ball=ball,
                    goal_cx=target_goal_cx_now,
                    now=now,
                    dribble_until=self._dribble_until,
                    min_radius=self._dribble_min_radius,
                )
                command = self._controller.compute(
                    ball_cx=cx_filtered,
                    ball_cy=cy_raw,
                    ball_r=r_eff,
                    goal_cx=target_goal_cx_now,
                    goal_cy=target_goal_cy_now,
                    line_detected=bool(self._line_phase),
                    continue_push=continue_dribble,
                )
                vL = command.v_left
                vR = command.v_right
                v_cmd = (vL - vR) * 0.5
                turn_cmd = (vL + vR) * 0.5
                command_mode = command.mode
                push_confirmed = should_allow_push_commit(
                    self._ball_streak,
                    min_streak=self._push_confirm_frames,
                )
                if command.mode == "PUSH" and command.reason != "dribble" and not push_confirmed:
                    v_cmd = min(v_cmd, self._controller.near_speed)
                    turn_cmd *= 0.75
                    command_mode = "CHASE_CONFIRM"
                elif command.mode == "PUSH" and command.reason == "dribble":
                    command_mode = "DRIBBLE_PUSH"
                if source == "cache":
                    v_cmd *= self._cache_speed_scale
                    turn_cmd *= self._cache_turn_scale
                vL = v_cmd + turn_cmd
                vR = -(v_cmd - turn_cmd)
                self._last_valid_v = v_cmd
                self._last_valid_w = turn_cmd
                self._last_valid_r = r_eff
                self._last_turn = turn_cmd
                self._last_v_left = vL
                self._last_v_right = vR
                if command.mode == "PUSH" and command.reason != "dribble" and push_confirmed:
                    self._push_until = now + self._push_commit_ms / 1000.0
                    self._dribble_until = self._push_until + self._dribble_after_push_ms / 1000.0
                    self._last_push_v_left = vL
                    self._last_push_v_right = vR
                if self._tick % 10 == 0:
                    log.info(
                        "src=%s r=%.0f cx=%.1f r_s=%.1f theta=%+.2f v=%.0f w=%+.0f vL=%.0f vR=%.0f mode=%s hys=%s goal=%s",
                        command_source, r_raw, cx_filtered, r_eff, theta_filtered, v_cmd, turn_cmd, vL, vR, command_mode,
                        self._hysteresis, "%.0f" % self._last_goal_cx if self._last_goal_cx is not None else "none",
                    )
                self._drive(vL, vR, 80)
            else:
                if self._last_valid_v > 0 or self._last_valid_w != 0:
                    self._miss_streak += 1
                    if should_hold_track_on_miss(self._miss_streak, max_miss_frames=self._track_miss_hold_frames):
                        decay = max(0.25, 1.0 - self._miss_streak / float(self._track_miss_hold_frames + 1))
                        v_cmd = self._last_valid_v * self._track_miss_hold_speed_scale * decay
                        turn_cmd = self._last_valid_w * self._track_miss_hold_turn_scale * decay
                        vL = v_cmd + turn_cmd
                        vR = -(v_cmd - turn_cmd)
                        self._drive(vL, vR, 80)
                        if self._tick % 10 == 0:
                            log.info("TRACK hold miss=%d v=%.0f w=%+.0f", self._miss_streak, v_cmd, turn_cmd)
                    else:
                        self._state = PREDICT
                        self._loss_start_t = now
                else:
                    self._state = FIELD_SEARCH
                    self._search_phase_start = now
                    self._search_burst_sent = False
                    self._search_phase = "move"

        elif self._state == PREDICT:
            elapsed = now - self._loss_start_t
            if elapsed < self._predict_timeout_s:
                decay = max(0.3, 1.0 - elapsed / self._predict_timeout_s)
                pred_v = self._last_valid_v * decay * self._prediction_speed_scale
                pred_w = self._last_valid_w * decay * self._prediction_turn_scale
                pred_w = max(-self._predict_turn_abs_limit * 0.4, min(self._predict_turn_abs_limit * 0.4, pred_w))
                vL = pred_v + pred_w
                vR = -(pred_v - pred_w)
                self._drive(vL, vR, 80)
                if self._tick % 15 == 0:
                    log.info("perdida PREDICT t=%.2fs", elapsed)
            else:
                if now - self._last_seen_t <= self._local_memory_sec:
                    self._state = LOCAL_REACQUIRE
                else:
                    self._state = FIELD_SEARCH
                self._search_phase_start = now
                self._search_burst_sent = False
                self._search_phase = "move"
            self._miss_streak += 1
            self._last_turn *= 0.6

        elif self._state == LOCAL_REACQUIRE:
            if not self._search_burst_sent:
                memory_cx = self._last_valid_cx if now - self._last_seen_t <= self._local_memory_sec else None
                direction, vL, vR = self._search.local_reacquire_step(memory_cx, self._last_valid_r, frame_width)
                self._drive(vL, vR, self._local_reacquire_ms)
                self._search_burst_sent = True
                self._search_phase_start = now
                if self._tick % 5 == 0:
                    log.info("LOCAL_REACQUIRE dir=%s last_cx=%s last_r=%.1f", direction, "%.0f" % memory_cx if memory_cx is not None else "-1", self._last_valid_r)
            if now - self._search_phase_start >= self._local_reacquire_ms / 1000.0:
                self._state = FIELD_SEARCH
                self._search_phase = "move"
                self._search_step_index = 0
                self._search_burst_sent = False
                self._search_phase_start = now
            self._miss_streak += 1
            self._last_turn *= 0.6

        elif self._state == FIELD_SEARCH:
            if self._search_phase == "move":
                if not self._search_burst_sent:
                    current_line_detected = bool(snap.get("line", {}).get("detected", False))
                    if self._line_cooldown > 0 or current_line_detected:
                        direction, vL, vR = self._search.line_aware_field_search_step(
                            self._search_step_index, self._last_line_cx, frame_width,
                        )
                    else:
                        direction, vL, vR = self._search.field_search_step(self._search_step_index)
                    self._drive(vL, vR, self._field_search_move_ms)
                    self._search_burst_sent = True
                    self._search_phase_start = now
                    if self._tick % 10 == 0:
                        log.info("FIELD_SEARCH%s paso=%d dir=%s", " line_aware" if (self._line_cooldown > 0 or current_line_detected) else "", self._search_step_index, direction)
                if now - self._search_phase_start >= self._field_search_move_ms / 1000.0:
                    self._motors.stop(100)
                    self._search_phase = "pause"
                    self._search_phase_start = now
            elif self._search_phase == "pause":
                if now - self._search_phase_start >= self._field_search_pause_ms / 1000.0:
                    self._search_step_index += 1
                    self._search_burst_sent = False
                    self._search_phase = "move"
                    self._search_phase_start = now
            self._miss_streak += 1
            self._last_turn *= 0.6

        if self._tick % 30 == 0:
            goals = snap.get("goals", {})
            line_diag = snap.get("line", {})
            log.info(
                "goals yellow=%s blue=%s line_det=%s line_pix=%s line_cy=%s",
                goals.get("yellow", False), goals.get("blue", False),
                line_diag.get("detected", False), line_diag.get("pixels", 0), line_diag.get("cy", None),
            )
        self._fps_count += 1
        if now - self._fps_start >= 1.0:
            fps = self._fps_count / (now - self._fps_start)
            self._fps_count = 0
            self._fps_start = now
            log.info("loop_fps=%.1f state=%s ball=%s line=%s goal=%s", fps, self._state, "yes" if ball_visible else "no", "yes" if snap.get("line", {}).get("detected", False) else "no", "yes" if self._last_goal_cx is not None else "no")
        self._tick += 1
        time.sleep(0.01)

    def run(self) -> None:
        self._running = True
        log.info("event=pipeline7_started mode=chase_dynamic")
        time.sleep(3)
        log.info("Listo. Frame=%s centro=%s", self._vision.frame_width, self._half)
        while self._running:
            self.tick()

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline7_closed")
