"""Pipeline 5 — sigue la pelota con visión y busca al perderla.

FSM de 2 estados:
    SEARCH  → gira buscando la pelota (giro + pausa cíclico).
    ADVANCE → avanza recto hacia la pelota detectada.

Transiciones:
    SEARCH  → ADVANCE (pelota visible)
    ADVANCE → SEARCH  (pelota perdida)

Usa motors.drive(v_left, v_right, dur_ms) con la misma convención que
el pipeline de v3:
    - Ambos positivos = avanzar
    - Signos opuestos = girar sobre eje
"""

import logging
import time

from src.pipeline5.utils.pipeline_constants import SEARCH, ADVANCE, STOP_DUR_MS
from src.pipeline5.dto.pipeline_output_dto import PipelineOutputDto
from src.pipeline5.operators.search_operator import SearchOperator
from src.pipeline5.operators.advance_operator import AdvanceOperator
from src.pipeline5.operators.avoid_wall_operator import AvoidWallOperator

log = logging.getLogger("turbopi.pipeline5")


class Pipeline5Service:
    def __init__(self, vision, motors) -> None:
        self._vision = vision
        self._motors = motors

        self._state = SEARCH
        self._running = False
        self._last_ball_log = 0.0
        self._last_no_ball_log = 0.0
        self._last_ball_cx = 0.0  # Para saber dónde se vio por última vez
        self._last_ball_cy = 0.0  # Para saber qué tan cerca estaba antes de perderla
        self._last_seen_ts = 0.0  # Para evitar parpadeos falsos

        import os
        self._attack_blue = os.environ.get("ATTACK_BLUE", "1").strip().lower() not in {"0", "false", "no"}
        self._ball_visible_min_radius = float(os.environ.get("BALL_VISIBLE_MIN_RADIUS", "8.0"))
        self._goal_edge_ball_min_radius = float(os.environ.get("GOAL_EDGE_BALL_MIN_RADIUS", "5.0"))
        self._ball_streak = 0

        self._search_op = SearchOperator()
        self._advance_op = AdvanceOperator()
        self._avoid_wall_op = AvoidWallOperator()

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        # Obtener snapshot de visión (mismo que v3)
        snap = self._vision.tick()
        ball = snap.get("ball")

        # --- FILTROS DE VISIÓN (estilo test_chase_dynamic.py de v4) ---
        target_key = "blue" if self._attack_blue else "yellow"
        target_goal_cx_now = snap.get("goals", {}).get(f"{target_key}_cx")

        if self._is_trackable_ball(
            ball,
            min_radius=self._ball_visible_min_radius,
        ) or self._should_accept_goal_edge_ball(
            ball,
            goal_cx=target_goal_cx_now,
            min_radius=self._goal_edge_ball_min_radius,
        ):
            self._ball_streak += 1
        else:
            self._ball_streak = 0

        ball_visible = self._ball_streak >= 1

        if not ball_visible:
            ball = None

        # Log de detección de pelota y actualización de última posición
        if ball_visible:
            self._last_ball_cx = ball["cx"]
            self._last_ball_cy = ball["cy"]
            self._last_seen_ts = now
            if now - self._last_ball_log >= 0.5:
                log.info(
                    "event=ball_detected cx=%s cy=%s r=%s source=%s state=%s",
                    ball["cx"], ball["cy"], ball["r"], ball["source"], self._state,
                )
                self._last_ball_log = now
        elif not ball_visible and now - self._last_no_ball_log >= 1.0:
            log.info("event=ball_NOT_detected state=%s", self._state)
            self._last_no_ball_log = now

        # Transición de estados
        if self._state == SEARCH:
            if ball_visible:
                self._state = ADVANCE
                log.info("event=state_change from=SEARCH to=ADVANCE")
        elif self._state == ADVANCE:
            if not ball_visible and (now - self._last_seen_ts > 0.2):
                # Esperamos 0.2s antes de darla por perdida para evitar "parpadeos"
                # Se perdió la pelota -> pasamos a BUSQUEDA (SEARCH)
                self._state = SEARCH
                centro_x = self._vision.frame_width / 2.0
                direccion = -1 if self._last_ball_cx < centro_x else 1
                self._search_op.reset(direction=direccion)
                log.info(f"event=state_change from=ADVANCE to=SEARCH direction={'left' if direccion == -1 else 'right'}")

        # Ejecución del estado actual
        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if self._state == ADVANCE:
            v_left, v_right, dur_ms = self._advance_op.compute(self._vision.frame_width, ball)

        elif self._state == SEARCH:
            v_left, v_right, dur_ms = self._search_op.compute()

        # Capa de seguridad: Evaluación de pared negra antes de mandar a motores
        frame = self._vision.last_frame()
        evasion = self._avoid_wall_op.check_and_avoid(frame)
        if evasion is not None:
            v_left, v_right, dur_ms = evasion
            log.info("event=avoid_wall_activated action=reversing")

        # Invertir v_left porque la rueda izquierda tiene polaridad invertida
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
        log.info("event=pipeline5_started mode=follow_ball_and_search")
        while self._running:
            self.tick()
            time.sleep(0.03)

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline5_closed")

    def _is_trackable_ball(
        self,
        ball: dict | None,
        min_radius: float = 8.0,
        allowed_sources: tuple[str, ...] = ("hsv",),
    ) -> bool:
        if ball is None:
            return False
        return ball.get("source") in allowed_sources and float(ball.get("r", 0.0)) >= min_radius

    def _should_accept_goal_edge_ball(
        self,
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
