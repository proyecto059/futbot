"""Fachada del pipeline con conciencia de rol (atacante / defensor).

FSM de estados:
    SEARCH  → gira buscando la pelota.
    CHASE   → persigue la pelota con rotación proporcional.
    AVOID   → retrocede y gira para esquivar obstáculos.

Comportamiento según rol (leído del `RoleState` en cada tick):
    ROL_ATACANTE:
        Comportamiento normal — SEARCH → CHASE → patear.

    ROL_DEFENSOR:
        No persigue la pelota. Giro defensivo lento.
        Si ultrasonido activa DIST_TRIGGER_MM → ejecuta plan AVOID.

    ROL_ESPERA:
        Robot detenido hasta que el WebSocket asigne un rol.

Si `role_state` es None el pipeline actúa siempre como atacante
(compatibilidad con código anterior).
"""

from __future__ import annotations

import logging
import time

from pipeline.operators.avoid_operator import AvoidOperator
from pipeline.operators.chase_operator import ChaseOperator
from pipeline.operators.search_operator import SearchOperator
from pipeline.utils.pipeline_constants import (
    AVOID,
    AVOID_MAX_STEPS,
    CHASE,
    CHASE_BLIND_MS,
    CHASE_BLIND_SCAN_SECS,
    CHASE_BLIND_SPEED,
    CHASE_MISS_SECS,
    SEARCH,
    SEARCH_SCAN_SECS,
    SEARCH_TURN_MS,
    SEARCH_TURN_SPEED,
)
from pipeline.dto.pipeline_output_dto import PipelineOutputDto

log = logging.getLogger("turbopi.pipeline")

_DEF_TURN_SPEED = 80
_DEF_TURN_MS    = 200
_DEF_SCAN_SECS  = 0.8


class PipelineService:
    def __init__(self, vision, ultrasonic, motors, role_state=None) -> None:
        self._vision     = vision
        self._ultrasonic = ultrasonic
        self._motors     = motors
        self._role_state = role_state

        self._state                 = SEARCH
        self._frame_width           = vision.frame_width
        self._frame_center_x        = self._frame_width / 2
        self._last_cx               = None
        self._miss_start            = None
        self._last_ball_time        = 0.0
        self._avoid_plan: list      = []
        self._avoid_index           = 0
        self._last_search_turn_time = 0.0
        self._last_chase_turn_time  = 0.0
        self._running               = False

        self._chase  = ChaseOperator()
        self._avoid  = AvoidOperator()
        self._search = SearchOperator()

    def _get_rol(self) -> str:
        if self._role_state is None:
            return "atacante"
        return self._role_state.get()

    def tick(self) -> PipelineOutputDto:
        now = time.time()
        rol = self._get_rol()

        snap     = self._vision.tick()
        ball     = snap.get("ball")
        dist_dto = self._ultrasonic.tick()
        dist_mm  = dist_dto.distance_mm

        ball_visible = ball is not None
        if ball_visible:
            self._last_cx        = ball["cx"]
            self._last_ball_time = now
            self._miss_start     = None
        else:
            if self._miss_start is None:
                self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0

        if rol == "espera":
            self._motors.stop()
            return PipelineOutputDto(state="ESPERA", ball=ball)

        if rol == "defensor":
            return self._tick_defensor(now, ball, dist_mm)

        return self._tick_atacante(now, ball, ball_visible, dist_mm, miss_secs)

    def _tick_atacante(self, now, ball, ball_visible, dist_mm, miss_secs):
        recent_ball   = ball_visible or (now - self._last_ball_time < CHASE_MISS_SECS)
        avoid_trigger = self._avoid.should_avoid(dist_mm)
        suppress      = self._avoid.is_ball_proximity(ball_visible, dist_mm, recent_ball)
        if suppress:
            avoid_trigger = False

        if self._state == SEARCH:
            if ball_visible:
                self._state = CHASE
                log.info("event=state_transition SEARCH->CHASE")
            elif avoid_trigger:
                self._state       = AVOID
                self._avoid_plan  = self._avoid.build_plan(self._last_cx, self._frame_center_x, AVOID_MAX_STEPS)
                self._avoid_index = 0
                log.info("event=state_transition SEARCH->AVOID")

        elif self._state == CHASE:
            if avoid_trigger:
                self._state       = AVOID
                self._avoid_plan  = self._avoid.build_plan(self._last_cx, self._frame_center_x, AVOID_MAX_STEPS)
                self._avoid_index = 0
                log.info("event=state_transition CHASE->AVOID")
            elif not ball_visible and miss_secs >= CHASE_MISS_SECS:
                self._state = SEARCH
                log.info("event=state_transition CHASE->SEARCH miss_timeout")

        elif self._state == AVOID:
            if self._avoid_index >= len(self._avoid_plan):
                self._state = SEARCH if not ball_visible else CHASE
                log.info("event=state_transition AVOID->%s", self._state)

        if self._state == SEARCH:
            self._exec_search(now, SEARCH_TURN_SPEED, SEARCH_TURN_MS, SEARCH_SCAN_SECS)

        elif self._state == CHASE:
            v_left, v_right, dur = self._chase.compute(self._frame_width, ball)
            if dur > 0:
                self._motors.drive(v_left=v_left, v_right=v_right, dur_ms=dur)
            else:
                if now - self._last_chase_turn_time >= CHASE_BLIND_SCAN_SECS:
                    self._motors.forward(speed=CHASE_BLIND_SPEED, dur_ms=CHASE_BLIND_MS)
                    self._last_chase_turn_time = now

        elif self._state == AVOID:
            if self._avoid_index < len(self._avoid_plan):
                self._exec_avoid_step(self._avoid_plan[self._avoid_index])
                self._avoid_index += 1

        return PipelineOutputDto(state=self._state, ball=ball)

    def _tick_defensor(self, now, ball, dist_mm):
        avoid_trigger = self._avoid.should_avoid(dist_mm)

        if avoid_trigger and self._state != AVOID:
            self._avoid_plan  = self._avoid.build_plan(self._last_cx, self._frame_center_x, AVOID_MAX_STEPS)
            self._avoid_index = 0
            self._state       = AVOID
            log.info("event=state_transition defensor ->AVOID")

        if self._state == AVOID:
            if self._avoid_index < len(self._avoid_plan):
                self._exec_avoid_step(self._avoid_plan[self._avoid_index])
                self._avoid_index += 1
            else:
                self._state = SEARCH
                log.info("event=state_transition defensor AVOID->SEARCH")
        else:
            self._state = SEARCH
            self._exec_search(now, _DEF_TURN_SPEED, _DEF_TURN_MS, _DEF_SCAN_SECS)

        return PipelineOutputDto(state=f"DEFENSOR/{self._state}", ball=ball)

    def _exec_search(self, now, speed, dur_ms, scan_secs):
        if now - self._last_search_turn_time >= scan_secs:
            direction = self._search.choose_direction(self._last_cx, self._frame_center_x)
            if direction == "left":
                self._motors.turn_left(speed=speed, dur_ms=dur_ms)
            else:
                self._motors.turn_right(speed=speed, dur_ms=dur_ms)
            self._last_search_turn_time = now

    def _exec_avoid_step(self, step: tuple):
        action, speed, dur_ms = step
        if action == "reverse":
            self._motors.reverse(speed=speed, dur_ms=dur_ms)
        elif action == "turn_left":
            self._motors.turn_left(speed=speed, dur_ms=dur_ms)
        elif action == "turn_right":
            self._motors.turn_right(speed=speed, dur_ms=dur_ms)
        elif action == "forward":
            self._motors.forward(speed=speed, dur_ms=dur_ms)

    def run(self) -> None:
        self._running = True
        log.info("event=pipeline_started")
        while self._running:
            try:
                self.tick()
            except Exception as exc:
                log.exception("event=tick_error error=%s", exc)

    def close(self) -> None:
        self._running = False
        log.info("event=pipeline_stopped")
