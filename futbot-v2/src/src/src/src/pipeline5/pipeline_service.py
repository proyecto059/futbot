"""Pipeline 5 — sigue la pelota con visión avanzada (Kalman + Predictor + Hysteresis).

FSM de 2 estados:
    SEARCH  → gira buscando la pelota (giro + pausa cíclico).
    ADVANCE → avanza hacia la pelota con BallGoalController.

Usa:
    - Kalman1D para filtrar posición (cx, r)
    - BallPredictor para predecir movimiento
    - TurnHysteresis para histéresis de giro
    - BallGoalController para calcular velocidades
    - SearchOperator del chase para búsqueda inteligente
"""

import logging
import time

from src.pipeline5.utils.pipeline_constants import SEARCH, ADVANCE, STOP_DUR_MS
from src.pipeline5.dto.pipeline_output_dto import PipelineOutputDto
from src.pipeline5.operators.avoid_wall_operator import AvoidWallOperator
from src.chase.ball_goal_controller import BallGoalController
from src.chase.visual_servo_controller import (
    BallPredictor,
    Kalman1D,
    TurnHysteresis,
    is_trackable_ball,
    effective_goal_radius,
)
from src.chase.search_operator import SearchOperator

log = logging.getLogger("turbopi.pipeline5")

BALL_VISIBLE_MIN_RADIUS = 8.0
TRACK_MISS_HOLD_FRAMES = 8
TRACK_MISS_HOLD_SPEED_SCALE = 0.75
TRACK_MISS_HOLD_TURN_SCALE = 0.55
PREDICT_TIMEOUT_S = 0.50


class Pipeline5Service:
    def __init__(self, vision, motors) -> None:
        self._vision = vision
        self._motors = motors

        self._frame_width = vision.frame_width
        self._frame_center_x = self._frame_width / 2.0

        self._state = SEARCH
        self._running = False
        self._last_ball_log = 0.0
        self._last_no_ball_log = 0.0

        self._kalman_cx = Kalman1D(q=2.6, r=1.0)
        self._kalman_r = Kalman1D(q=0.9, r=1.5)
        self._predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
        self._hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)

        self._ball_goal_controller = BallGoalController(frame_width=self._frame_width)
        self._search_op = SearchOperator()
        self._avoid_wall_op = AvoidWallOperator()

        self._last_valid_cx = 0.0
        self._last_valid_r = 0.0
        self._last_seen_ts = 0.0
        self._last_valid_v = 0.0
        self._last_valid_w = 0.0

        self._miss_streak = 0
        self._ball_streak = 0

        self._search_phase_start = 0.0
        self._search_burst_sent = False
        self._search_step_index = 0
        self._recover_done = False

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        snap = self._vision.tick()
        ball = snap.get("ball")

        if is_trackable_ball(ball, min_radius=BALL_VISIBLE_MIN_RADIUS):
            self._ball_streak += 1
        else:
            self._ball_streak = 0

        ball_visible = self._ball_streak >= 1

        if ball is not None:
            source = ball.get("source", "hsv")
            cx_raw = ball["cx"]
            r_raw = ball["r"]
        else:
            source = "none"
            cx_raw = None
            r_raw = None

        if ball_visible and source in ("hsv", "yolo"):
            cx_f = self._kalman_cx.update(cx_raw)
            r_f = self._kalman_r.update(r_raw)

            self._predictor.update(cx_f, r_f, now)
            self._last_valid_cx = cx_f
            self._last_valid_r = r_f
            self._last_seen_ts = now

            theta_raw = (cx_f - self._frame_center_x) / self._frame_center_x
            theta_filtered = self._hysteresis.filter(theta_raw)
            cx_filtered = self._frame_center_x + self._frame_center_x * theta_filtered

            _, r_eff = self._predictor.predict(0.0)
            r_eff = effective_goal_radius(r_raw, r_eff)

            command = self._ball_goal_controller.compute(
                ball_cx=cx_filtered,
                ball_r=r_eff,
                goal_cx=None,
                line_detected=False,
            )

            vL = command.v_left
            vR = command.v_right
            v_cmd = (vL - vR) * 0.5
            turn_cmd = (vL + vR) * 0.5

            self._last_valid_v = v_cmd
            self._last_valid_w = turn_cmd

            if now - self._last_ball_log >= 0.5:
                log.info(
                    "event=ball_detected cx=%s r=%s source=%s state=%s mode=%s",
                    cx_f, r_eff, source, self._state, command.mode,
                )
                self._last_ball_log = now

            v_left, v_right = vL, vR
            dur_ms = 80

        else:
            if self._state == ADVANCE:
                self._miss_streak += 1
                if self._miss_streak <= TRACK_MISS_HOLD_FRAMES:
                    decay = max(0.25, 1.0 - self._miss_streak / float(TRACK_MISS_HOLD_FRAMES + 1))
                    v_cmd = self._last_valid_v * TRACK_MISS_HOLD_SPEED_SCALE * decay
                    turn_cmd = self._last_valid_w * TRACK_MISS_HOLD_TURN_SCALE * decay
                    v_left = v_cmd + turn_cmd
                    v_right = -(v_cmd - turn_cmd)
                    dur_ms = 80

                    if now - self._last_ball_log >= 1.0:
                        log.info("event=track_hold miss=%d", self._miss_streak)
                        self._last_ball_log = now
                else:
                    v_left, v_right, dur_ms = 0.0, 0.0, 100
                    self._miss_streak = 0
            else:
                v_left, v_right, dur_ms = 0.0, 0.0, 100

        if not ball_visible and now - self._last_no_ball_log >= 1.0:
            log.info("event=ball_NOT_detected state=%s", self._state)
            self._last_no_ball_log = now

        prev_state = self._state

        if self._state == SEARCH:
            if ball_visible:
                self._state = ADVANCE
                self._miss_streak = 0
                self._recover_done = False

        elif self._state == ADVANCE:
            if not ball_visible and (now - self._last_seen_ts > PREDICT_TIMEOUT_S):
                self._state = SEARCH
                log.info(f"event=state_change from=ADVANCE to=SEARCH")

        if self._state != prev_state:
            self._search_phase_start = now
            self._search_burst_sent = False

        if self._state == SEARCH:
            if not self._recover_done:
                if not self._search_burst_sent:
                    direction, vL, vR = self._search_op.recover_step(
                        self._last_valid_cx, self._frame_width
                    )
                    v_left, v_right, dur_ms = vL, vR, 1000
                    self._search_burst_sent = True
                    self._search_phase_start = now

                if now - self._search_phase_start >= 1.0:
                    self._recover_done = True
                    self._search_phase = "turn"
                    self._search_step_index = 0
                    self._search_burst_sent = False

        frame = self._vision.last_frame()
        evasion = self._avoid_wall_op.check_and_avoid(frame)
        if evasion is not None:
            v_left, v_right, dur_ms = evasion
            log.info("event=avoid_wall_activated")

        if v_left != 0 or v_right != 0:
            self._motors.drive(-v_left, v_right, dur_ms)
        else:
            self._motors.stop(dur_ms)

        return PipelineOutputDto(
            state=self._state,
            ball_visible=ball_visible,
            v_left=v_left,
            v_right=v_right,
            dur_ms=dur_ms,
            ts=now,
        )

    def run(self):
        self._running = True
        log.info("event=pipeline5_started mode=kalman_chase")
        while self._running:
            self.tick()
            time.sleep(0.01)

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline5_closed")