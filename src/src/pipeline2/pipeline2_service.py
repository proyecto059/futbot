"""Fachada del pipeline2 — modo simple: ver pelota → avanzar.

Este módulo NO contiene lógica de visión ni de motores — solo orquesta
operadores.  Se lee de arriba hacia abajo:
"leo cámara → ¿hay pelota? → si sí: avanzo, si no: me detengo".

Usa VISIÓN HÍBRIDA (HSV + YOLO):
    - HSV corre en el hilo principal (~30 FPS) y es preciso para color.
    - YOLO corre en paralelo (~15 FPS) como backup para oclusiones.
    - BallFusionOperator fusiona: HSV > YOLO > caché.

FSM de 2 estados:
    IDLE     → no ve pelota, motores detenidos.
    ADVANCE  → ve pelota, motores avanzar recto.

Transiciones:
    IDLE    → ADVANCE  (pelota visible)
    ADVANCE → IDLE     (pelota perdida)

No usa ultrasonido — este pipeline es intencionalmente simple para
pruebas de concepto y calibración de visión + motores.

Ejemplo:
    pipeline = Pipeline2Service(vision, motors)
    try:
        pipeline.run()
    finally:
        pipeline.close()
"""

from __future__ import annotations

import logging
import time

from pipeline2.dto.pipeline2_output_dto import Pipeline2OutputDto
from pipeline2.operators.advance_operator import AdvanceOperator
from pipeline2.utils import ADVANCE, IDLE, STOP_DUR_MS

log = logging.getLogger("turbopi.pipeline2")


class Pipeline2Service:
    """Pipeline simple: ve pelota → avanza recto."""

    def __init__(self, vision, motors) -> None:
        self._vision = vision
        self._motors = motors
        self._state = IDLE
        self._advance = AdvanceOperator()
        self._running = False
        self._consecutive_detections = 0

    def tick(self) -> Pipeline2OutputDto:
        """Ejecuta un paso: lee visión, decide estado, envía a motores."""
        now = time.time()

        # 1. Leer visión (híbrida HSV + YOLO)
        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None

        # Extraer info de HSV y YOLO por separado del snapshot
        hsv_ball = snap.get("hsv_ball")
        yolo_ball = snap.get("yolo_ball")
        hsv_detected = hsv_ball is not None
        yolo_detected = yolo_ball is not None

        # 2. Transición de estado
        prev_state = self._state

        if ball_visible:
            self._consecutive_detections += 1
            if self._consecutive_detections >= 8:  # 3 frames consecutivos
                self._state = ADVANCE
            else:
                self._state = self._state  # mantener estado
        else:
            self._consecutive_detections = 0
            self._state = IDLE

        if self._state != prev_state:
            if self._state == ADVANCE:
                log.info(
                    "event=state_change from=%s to=%s ball=True "
                    "hsv=%s yolo=%s source=%s",
                    prev_state, self._state,
                    hsv_detected, yolo_detected,
                    ball.get("source", "?") if ball else "?",
                )
                if hsv_detected:
                    log.info(
                        "  HSV: cx=%s cy=%s r=%s",
                        hsv_ball.get("cx"), hsv_ball.get("cy"), hsv_ball.get("r"),
                    )
                if yolo_detected:
                    log.info(
                        "  YOLO: cx=%s cy=%s r=%s conf=%s",
                        yolo_ball.get("cx"), yolo_ball.get("cy"),
                        yolo_ball.get("r"), yolo_ball.get("conf", "?"),
                    )
            else:
                log.info("event=state_change from=%s to=%s ball=%s hsv=%s yolo=%s",
                         prev_state, self._state, ball_visible, hsv_detected, yolo_detected)

        # 3. Calcular velocidades
        v_left, v_right, dur_ms = self._advance.compute(ball_visible)

        # 4. Enviar a motores
        if v_left != 0 or v_right != 0:
            self._motors.drive(v_left, v_right, dur_ms)
        else:
            self._motors.stop(STOP_DUR_MS)

        return Pipeline2OutputDto(
            state=self._state,
            ball_visible=ball_visible,
            v_left=v_left,
            v_right=v_right,
            dur_ms=dur_ms,
            ts=now,
        )

    def run(self) -> None:
        """Loop principal — corre hasta que se llame stop() o Ctrl+C."""
        self._running = True
        log.info("event=pipeline2_started")
        while self._running:
            self.tick()
            time.sleep(0.01)

    def stop(self) -> None:
        """Señala al loop que debe terminar."""
        self._running = False
        self._consecutive_detections = 0

    def close(self) -> None:
        """Detiene el loop y frena los motores."""
        self._running = False
        self._consecutive_detections = 0
        self._motors.stop(200)
        log.info("event=pipeline2_closed")