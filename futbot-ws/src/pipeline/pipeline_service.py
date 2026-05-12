"""Fachada del pipeline con conciencia de rol (atacante / defensor).

FSM de 2 estados (mejoras v2):
    SEARCH  → gira buscando la pelota.
    CHASE   → gira hacia la pelota de forma proporcional y continua.

Transiciones:
    SEARCH → CHASE  (pelota visible)
    CHASE  → SEARCH (miss timeout — pelota perdida demasiado tiempo)

El sensor ultrasónico se lee cada tick para logging, pero NO activa
ninguna lógica de evasión (cambio v2 — AVOID eliminado).

Comportamiento según rol (integración WebSocket, opcional):
    ROL_ATACANTE:
        FSM normal — SEARCH → CHASE → avance.

    ROL_DEFENSOR:
        Mantiene SEARCH permanentemente con velocidad reducida.
        No persigue la pelota.

    ROL_ESPERA:
        Motores detenidos hasta que el WebSocket asigne un rol.

Si `role_state` es None el pipeline actúa siempre como atacante
(compatibilidad total con código sin WebSocket).
"""

from __future__ import annotations

import logging
import time

from pipeline.dto.pipeline_output_dto import PipelineOutputDto
from pipeline.operators.chase_operator import ChaseOperator
from pipeline.operators.search_operator import SearchOperator
from pipeline.utils.pipeline_constants import (
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

# Parámetros del giro defensivo (más lento que atacante)
_DEF_TURN_SPEED = 80
_DEF_SCAN_SECS  = 0.8


class PipelineService:
    def __init__(self, vision, ultrasonic, motors, role_state=None) -> None:
        self._vision     = vision
        self._ultrasonic = ultrasonic
        self._motors     = motors
        self._role_state = role_state  # RoleState | None

        self._state               = SEARCH
        self._frame_width         = vision.frame_width
        self._frame_center_x      = self._frame_width / 2
        self._last_cx             = None
        self._miss_start          = None
        self._last_ball_time      = 0.0
        self._last_search_turn_time = 0.0
        self._last_chase_turn_time  = 0.0
        self._last_ultra_log      = 0.0
        self._last_chase_log      = 0.0
        self._running             = False

        self._chase  = ChaseOperator()
        self._search = SearchOperator()

    # ── Rol ──────────────────────────────────────────────────────────────

    def _get_rol(self) -> str:
        if self._role_state is None:
            return "atacante"
        return self._role_state.get()

    # ── Tick principal ────────────────────────────────────────────────────

    def tick(self) -> PipelineOutputDto:
        now = time.time()
        rol = self._get_rol()

        snap     = self._vision.tick()
        ball     = snap.get("ball")
        dist_dto = self._ultrasonic.tick()
        dist_mm  = dist_dto.distance_mm

        ball_visible = ball is not None
        cx = None
        if ball_visible:
            cx               = ball["cx"]
            self._last_cx    = cx
            self._miss_start = None
        else:
            if self._miss_start is None:
                self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0

        # Telemetría ultrasonido (cada 2 s)
        if now - self._last_ultra_log >= 2.0:
            log.info(
                "event=ultrasonic dist_mm=%s state=%s rol=%s",
                dist_mm if dist_mm is not None else "none",
                self._state, rol,
            )
            self._last_ultra_log = now

        # ── ESPERA ───────────────────────────────────────────────────────
        if rol == "espera":
            self._motors.stop()
            return PipelineOutputDto(state="ESPERA", ball=ball)

        # ── DEFENSOR ─────────────────────────────────────────────────────
        if rol == "defensor":
            return self._tick_defensor(now, ball, dist_mm)

        # ── ATACANTE ─────────────────────────────────────────────────────
        return self._tick_atacante(now, ball, ball_visible, cx, miss_secs)

    # ── FSM atacante (lógica v2 mejorada) ────────────────────────────────

    def _tick_atacante(self, now, ball, ball_visible, cx, miss_secs):
        prev_state = self._state

        # Transiciones
        if self._state == CHASE:
            if not ball_visible and miss_secs >= CHASE_MISS_SECS:
                self._state = SEARCH

        elif self._state == SEARCH:
            if ball_visible:
                self._state = CHASE

        # Reset de timers al cambiar de estado (mejora v2)
        if self._state != prev_state:
            if self._state == SEARCH:
                self._last_search_turn_time = 0.0
                self._last_cx = None
            elif self._state == CHASE:
                self._last_chase_turn_time = 0.0

        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if self._state == SEARCH:
            if now - self._last_search_turn_time >= SEARCH_SCAN_SECS:
                direction = self._search.choose_direction(self._last_cx, self._frame_center_x)
                speed = SEARCH_TURN_SPEED
                v_left  = -speed if direction == "left" else speed
                v_right =  speed if direction == "left" else -speed
                dur_ms  = SEARCH_TURN_MS
                self._last_search_turn_time = now

        elif self._state == CHASE:
            if ball_visible:
                self._last_ball_time       = now
                v_left, v_right, dur_ms    = self._chase.compute(self._frame_width, ball)
            elif now - self._last_ball_time < CHASE_MISS_SECS:
                # Pelota recién perdida → avance ciego recto
                v_left  = float(CHASE_BLIND_SPEED)
                v_right = float(CHASE_BLIND_SPEED)
                dur_ms  = 100
            else:
                # Pelota perdida hace rato → giro buscando en dirección conocida
                if now - self._last_chase_turn_time >= CHASE_BLIND_SCAN_SECS:
                    direction = self._search.choose_direction(self._last_cx, self._frame_center_x)
                    speed   = CHASE_BLIND_SPEED
                    v_left  = -speed if direction == "left" else speed
                    v_right =  speed if direction == "left" else -speed
                    dur_ms  = CHASE_BLIND_MS
                    self._last_chase_turn_time = now

        # Telemetría de CHASE (cada 0.5 s)
        if self._state == CHASE and now - self._last_chase_log >= 0.5:
            ball_cx = cx if cx is not None else self._last_cx
            error = (ball_cx - self._frame_center_x) if ball_cx is not None else "n/a"
            log.info(
                "event=chase cx=%s error=%s vL=%.1f vR=%.1f dur=%d ball=%s",
                ball_cx if ball_cx is not None else "none",
                error, v_left, v_right, dur_ms,
                "visible" if ball_visible else "blind",
            )
            self._last_chase_log = now

        # Envío a motores
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
            ball=ball,
        )

    # ── FSM defensor ─────────────────────────────────────────────────────

    def _tick_defensor(self, now, ball, dist_mm):
        """Giro defensivo lento. No persigue la pelota. Sin AVOID (v2)."""
        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if now - self._last_search_turn_time >= _DEF_SCAN_SECS:
            direction = self._search.choose_direction(self._last_cx, self._frame_center_x)
            speed   = _DEF_TURN_SPEED
            v_left  = -speed if direction == "left" else speed
            v_right =  speed if direction == "left" else -speed
            dur_ms  = SEARCH_TURN_MS
            self._last_search_turn_time = now

        if v_left != 0 or v_right != 0:
            self._motors.drive(v_left, v_right, dur_ms)
        else:
            self._motors.stop(dur_ms)

        return PipelineOutputDto(
            state=f"DEFENSOR/{SEARCH}",
            v_left=v_left,
            v_right=v_right,
            dur_ms=dur_ms,
            ts=now,
            ball=ball,
        )

    # ── Ciclo de vida ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Loop principal bloqueante con sleep de 10 ms (mejora v2)."""
        self._running = True
        while self._running:
            self.tick()
            time.sleep(0.01)

    def stop(self) -> None:
        """Detiene el loop sin liberar hardware."""
        self._running = False

    def close(self) -> None:
        """Detiene el loop y frena motores."""
        self._running = False
        self._motors.stop(200)