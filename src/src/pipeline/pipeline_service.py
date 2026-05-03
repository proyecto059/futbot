"""Fachada del pipeline (punto de entrada único).

Este módulo NO contiene lógica de visión ni de motores — solo orquesta
operadores.  Se lee de arriba hacia abajo como una receta:
"leo sensores → evalúo FSM → calculo velocidades → envío a motores".

FSM de 3 estados:
    SEARCH  → gira buscando la pelota.
    CHASE   → persigue la pelota con rotación proporcional.
    AVOID   → retrocede y gira para esquivar obstáculos (ultrasónico ≤ 250 mm).

Transiciones:
    SEARCH → CHASE  (pelota visible)
    SEARCH → AVOID  (obstáculo detectado)
    CHASE  → AVOID  (obstáculo detectado)
    CHASE  → SEARCH (miss timeout — pelota perdida demasiado tiempo)
    AVOID  → SEARCH / CHASE (plan de evasión completado)

Override de proximidad: si la pelota está visible y cerca, se suprime el
trigger de avoid (es la pelota, no una pared).

Ejemplo:
    pipeline = PipelineService(vision, ultrasonic, motors)
    try:
        pipeline.run()
    finally:
        pipeline.close()
"""

from __future__ import annotations

import logging
import time

from pipeline.dto.pipeline_output_dto import PipelineOutputDto
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

log = logging.getLogger("turbopi.pipeline")


class PipelineService:
    def __init__(self, vision, ultrasonic, motors) -> None:
        self._vision = vision
        self._ultrasonic = ultrasonic
        self._motors = motors

        self._state = SEARCH
        self._frame_width = vision.frame_width
        self._frame_center_x = self._frame_width / 2
        self._last_cx = None
        self._miss_start = None
        self._last_ball_time = 0.0
        self._last_radius = None
        self._avoid_plan: list[tuple[str, int, int]] = []
        self._avoid_index = 0
        self._last_search_turn_time = 0.0
        self._last_chase_turn_time = 0.0
        self._last_ultra_log = 0.0
        self._running = False

        self._chase = ChaseOperator()
        self._avoid = AvoidOperator()
        self._search = SearchOperator()

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None
        dist_dto = self._ultrasonic.tick()
        dist_mm = dist_dto.distance_mm

        cx = None
        radius = None
        if ball_visible:
            cx = ball["cx"]
            radius = ball["r"]
            self._last_cx = cx
            self._miss_start = None
        else:
            if self._miss_start is None:
                self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0
        recent_ball = ball_visible or (now - self._last_ball_time < CHASE_MISS_SECS)

        should_avoid = self._avoid.should_avoid(dist_mm)
        if (
            should_avoid
            and recent_ball
            and self._avoid.is_ball_proximity(ball_visible, dist_mm, recent_ball)
        ):
            should_avoid = False

        prev_state = self._state

        if self._state == AVOID:
            if self._avoid_index >= len(self._avoid_plan):
                if should_avoid:
                    self._avoid_plan = self._avoid.build_plan(
                        self._last_cx, self._frame_center_x, AVOID_MAX_STEPS
                    )
                    self._avoid_index = 0
                elif ball_visible:
                    self._state = CHASE
                else:
                    self._state = SEARCH

        elif self._state == CHASE:
            if should_avoid:
                self._state = AVOID
            elif not ball_visible and miss_secs >= CHASE_MISS_SECS:
                self._state = SEARCH

        elif self._state == SEARCH:
            if should_avoid:
                self._state = AVOID
            elif ball_visible:
                self._state = CHASE

        if self._state != prev_state:
            if self._state == SEARCH:
                self._last_search_turn_time = 0.0
                self._last_cx = None
            elif self._state == CHASE:
                self._last_chase_turn_time = 0.0
            elif self._state == AVOID:
                self._avoid_plan = self._avoid.build_plan(
                    self._last_cx, self._frame_center_x, AVOID_MAX_STEPS
                )
                self._avoid_index = 0

        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if self._state == SEARCH:
            if now - self._last_search_turn_time >= SEARCH_SCAN_SECS:
                direction = self._search.choose_direction(
                    self._last_cx, self._frame_center_x
                )
                speed = SEARCH_TURN_SPEED
                v_left = -speed if direction == "left" else speed
                v_right = speed if direction == "left" else -speed
                dur_ms = SEARCH_TURN_MS
                self._last_search_turn_time = now
            else:
                v_left, v_right, dur_ms = 0.0, 0.0, 100

        elif self._state == CHASE:
            if ball_visible:
                self._last_ball_time = now
                self._last_radius = radius
                v_left, v_right, dur_ms = self._chase.compute(self._frame_width, ball)
            elif now - self._last_ball_time < CHASE_MISS_SECS:
                v_left, v_right, dur_ms = self._chase.compute(
                    self._frame_width,
                    {"cx": self._last_cx or self._frame_center_x, "r": 0},
                )
            else:
                if now - self._last_chase_turn_time >= CHASE_BLIND_SCAN_SECS:
                    direction = self._search.choose_direction(
                        self._last_cx, self._frame_center_x
                    )
                    speed = CHASE_BLIND_SPEED
                    v_left = -speed if direction == "left" else speed
                    v_right = speed if direction == "left" else -speed
                    dur_ms = CHASE_BLIND_MS
                    self._last_chase_turn_time = now
                else:
                    v_left, v_right, dur_ms = 0.0, 0.0, 100

        elif self._state == AVOID:
            if self._avoid_index < len(self._avoid_plan):
                step_name, speed, step_ms = self._avoid_plan[self._avoid_index]
                if step_name == "reverse":
                    v_left, v_right = -speed, -speed
                elif step_name == "forward":
                    v_left, v_right = speed, speed
                elif step_name == "turn_left":
                    v_left, v_right = -speed, speed
                elif step_name == "turn_right":
                    v_left, v_right = speed, -speed
                dur_ms = step_ms
                self._avoid_index += 1
                time.sleep(step_ms / 1000.0)

        if now - self._last_ultra_log >= 2.0:
            log.info(
                "event=ultrasonic dist_mm=%s state=%s",
                dist_mm if dist_mm is not None else "none",
                self._state,
            )
            self._last_ultra_log = now

        if v_left != 0 or v_right != 0:
            self._motors.drive(v_left, v_right, dur_ms)
        else:
            self._motors.stop(dur_ms)

        return PipelineOutputDto(
            state=self._state,
            v_left=v_left,
            v_right=v_right,
            dur_ms=dur_ms,
            ts=now,
        )

    def run(self) -> None:
        self._running = True
        while self._running:
            self.tick()
            time.sleep(0.01)

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        self._running = False
        self._motors.stop(200)