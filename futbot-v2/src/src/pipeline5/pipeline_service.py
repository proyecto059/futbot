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

from src.pipeline5.utils.pipeline_constants import SEARCH, ADVANCE, SHOOT, SHOOT_SPEED, STOP_DUR_MS
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
        self._shoot_start_ts = 0.0

        self._search_op = SearchOperator()
        self._advance_op = AdvanceOperator()
        self._avoid_wall_op = AvoidWallOperator()

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        # Obtener snapshot de visión (mismo que v3)
        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None

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
                # Determinar altura de la cámara, por default 240 (o 480 según configuración)
                cam_height = 240
                if hasattr(self._vision, "_cfg"):
                    cam_height = self._vision._cfg.camera_height
                
                umbral_tiro = cam_height * 0.70  # 70% hacia abajo es la "parte baja"

                if self._last_ball_cy >= umbral_tiro:
                    # Se perdió por abajo -> TIRO
                    self._state = SHOOT
                    self._shoot_start_ts = now
                    log.info("event=state_change from=ADVANCE to=SHOOT reason=ball_lost_bottom")
                else:
                    # Se perdió por los lados -> BUSQUEDA
                    self._state = SEARCH
                    centro_x = self._vision.frame_width / 2.0
                    direccion = -1 if self._last_ball_cx < centro_x else 1
                    self._search_op.reset(direction=direccion)
                    log.info(f"event=state_change from=ADVANCE to=SEARCH direction={'left' if direccion == -1 else 'right'}")
        elif self._state == SHOOT:
            if now - self._shoot_start_ts >= 0.5:
                # Termina el periodo de 0.5s de tiro
                self._state = SEARCH
                self._search_op.reset(direction=1) # Reinicia búsqueda hacia la derecha por defecto
                log.info("event=state_change from=SHOOT to=SEARCH reason=shoot_finished")

        # Ejecución del estado actual
        v_left, v_right, dur_ms = 0.0, 0.0, 100

        if self._state == ADVANCE:
            v_left, v_right, dur_ms = self._advance_op.compute()

        elif self._state == SEARCH:
            v_left, v_right, dur_ms = self._search_op.compute()

        elif self._state == SHOOT:
            v_left, v_right, dur_ms = float(SHOOT_SPEED), float(SHOOT_SPEED), 100

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
