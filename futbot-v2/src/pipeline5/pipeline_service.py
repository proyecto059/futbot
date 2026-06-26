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

from pipeline5.utils.pipeline_constants import SEARCH, ADVANCE, STOP_DUR_MS
from pipeline5.dto.pipeline_output_dto import PipelineOutputDto
from pipeline5.operators.search_operator import SearchOperator
from pipeline5.operators.advance_operator import AdvanceOperator
from pipeline5.operators.avoid_wall_operator import AvoidWallOperator

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

        self._search_op = SearchOperator()
        self._advance_op = AdvanceOperator()
        self._avoid_wall_op = AvoidWallOperator()

    def tick(self) -> PipelineOutputDto:
        now = time.time()

        # Obtener snapshot de visión (mismo que v3)
        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None

        # --- FILTROS INSTANTÁNEOS (Sin retrasos) ---
        if ball_visible:
            frame = self._vision.last_frame()
            if frame is not None:
                import cv2
                import numpy as np
                cx, cy = int(ball["cx"]), int(ball["cy"])
                
                # 1. Filtro de Color y Saturación (Rechaza amarillo y brillos blancos)
                patch_r = 3
                y0, y1 = max(0, cy - patch_r), min(frame.shape[0], cy + patch_r + 1)
                x0, x1 = max(0, cx - patch_r), min(frame.shape[1], cx + patch_r + 1)
                
                if x1 > x0 and y1 > y0:
                    patch_bgr = frame[y0:y1, x0:x1]
                    patch_hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
                    median_h = int(np.median(patch_hsv[:, :, 0]))
                    median_s = int(np.median(patch_hsv[:, :, 1]))
                    
                    # La pelota es naranja (Hue entre 0 y 12). 
                    # Rechazamos CUALQUIER OTRO COLOR (amarillo, verde, azul, morado, rosa)
                    if 13 <= median_h <= 170:
                        log.info(f"event=ball_rejected reason=wrong_color hue={median_h} source={ball.get('source')}")
                        ball = None
                        ball_visible = False
                    elif median_s < 140:  # Exigir que sea un "naranja chillón" (saturación alta). Rechaza madera, piel, cartón.
                        log.info(f"event=ball_rejected reason=not_neon_enough sat={median_s} source={ball.get('source')}")
                        ball = None
                        ball_visible = False
                        
            # 2. Filtro de Forma (Rechaza pilares altos, solo si YOLO ya los vio)
            if ball_visible and hasattr(self._vision, "_yolo"):
                yolo_raw = self._vision._yolo.get_latest_output()
                ball_bbox = yolo_raw.get("ball_bbox")
                if ball_bbox is not None:
                    x1, y1, x2, y2, conf, cls_id = ball_bbox
                    w = max(1.0, float(x2 - x1))
                    h = max(1.0, float(y2 - y1))
                    
                    # Si es un pilar, lo rechazamos al instante.
                    if (h / w) > 1.4:
                        log.info(f"event=ball_rejected reason=tall_pillar_shape source={ball.get('source')}")
                        ball = None
                        ball_visible = False
        # -------------------------------------------

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
