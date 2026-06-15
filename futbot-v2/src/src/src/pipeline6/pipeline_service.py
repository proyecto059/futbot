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

from src.pipeline6.utils.pipeline_constants import SEARCH, ADVANCE, RECOVERY, STOP_DUR_MS, ADVANCE_SPEED
from src.pipeline6.dto.pipeline_output_dto import PipelineOutputDto
from src.pipeline6.operators.search_operator import SearchOperator
from src.pipeline6.operators.advance_operator import AdvanceOperator

log = logging.getLogger("turbopi.pipeline6")


class Pipeline6Service:
    def __init__(self, vision, motors) -> None:
        self._vision = vision
        self._motors = motors

        self._state = SEARCH
        self._running = False
        self._last_ball_log = 0.0
        self._last_no_ball_log = 0.0
        
        # Recuperacion inteligente variables
        self._last_cx = 160
        self._recovery_start = 0.0

        self._search_op = SearchOperator()
        self._advance_op = AdvanceOperator()

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        # Obtener snapshot de visión (mismo que v3)
        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None

        if ball_visible:
            self._last_cx = ball["cx"]

        # Log de detección de pelota
        if ball_visible and now - self._last_ball_log >= 0.5:
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
            if not ball_visible:
                self._state = RECOVERY
                self._recovery_start = now
                log.info("event=state_change from=ADVANCE to=RECOVERY last_cx=%s", self._last_cx)
        elif self._state == RECOVERY:
            if ball_visible:
                self._state = ADVANCE
                log.info("event=state_change from=RECOVERY to=ADVANCE")
            elif now - self._recovery_start >= 1.0:
                self._state = SEARCH
                self._search_op.reset()
                log.info("event=state_change from=RECOVERY to=SEARCH")

        # Ejecución del estado actual
        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if self._state == ADVANCE:
            v_left, v_right, dur_ms = self._advance_op.compute()

        elif self._state == SEARCH:
            v_left, v_right, dur_ms = self._search_op.compute()
            
        elif self._state == RECOVERY:
            velocidadLenta = ADVANCE_SPEED
            
            if self._last_cx < 100:
                # Izquierda
                v_left, v_right = -velocidadLenta, velocidadLenta
            elif self._last_cx >= 100 and self._last_cx <= 200:
                # Centro
                v_left, v_right = velocidadLenta, velocidadLenta
            else:
                # Derecha
                v_left, v_right = velocidadLenta, -velocidadLenta
            dur_ms = 100

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
        log.info("event=pipeline6_started mode=follow_ball_and_search")
        while self._running:
            self.tick()
            time.sleep(0.03)

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline6_closed")
