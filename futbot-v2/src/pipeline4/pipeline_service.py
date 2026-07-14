"""Pipeline 4 — rutina de disparo a portería.

FSM de 4 estados:
    SEARCH  → gira buscando la pelota (turn + pause cíclico).
    ADVANCE → avanza hacia la pelota con control proporcional.
    ALIGN   → rota lentamente para alinear pelota + portería al centro.
    PUSH    → avanza recto a máxima velocidad empujando la pelota.

Transiciones:
    SEARCH  → ADVANCE (pelota visible)
    ADVANCE → ALIGN   (pelota cerca + portería visible)
    ADVANCE → SEARCH  (pelota perdida >0.2s)
    ALIGN   → PUSH    (pelota y portería centradas)
    ALIGN   → ADVANCE (pelota se alejó)
    ALIGN   → SEARCH  (pelota perdida >0.5s)
    PUSH    → SEARCH  (empuje completado tras PUSH_DUR_MS)

Cada tick ejecuta:
    1. Obtener snapshot de visión (frame + pelota + porterías)
    2. Aplicar filtros de color/saturación/forma
    3. Evaluar transiciones del FSM
    4. Calcular velocidades según el operador del estado actual
    5. Aplicar capa de seguridad AvoidWall (máxima prioridad)
    6. Enviar comandos a motores (invirtiendo rueda izquierda por polaridad)
"""

import logging
import time

from pipeline4.utils.pipeline_constants import (
    SEARCH, ADVANCE, ALIGN, PUSH,
    STOP_DUR_MS, BALL_CLOSE_RADIUS,
)
from pipeline4.dto.pipeline_output_dto import PipelineOutputDto
from pipeline4.operators.search_operator import SearchOperator
from pipeline4.operators.advance_operator import AdvanceOperator
from pipeline4.operators.align_to_goal_operator import AlignToGoalOperator
from pipeline4.operators.push_operator import PushOperator
from pipeline4.operators.avoid_wall_operator import AvoidWallOperator
from pipeline4.operators.operator_base import OperatorBase

log = logging.getLogger("turbopi.pipeline4")


class Pipeline4Service:
    def __init__(self, vision, motors) -> None:
        self._vision = vision
        self._motors = motors

        self._state = SEARCH
        self._running = False
        self._last_ball_log = 0.0
        self._last_no_ball_log = 0.0
        self._last_ball_cx = 0.0
        self._last_ball_cy = 0.0
        self._last_seen_ts = 0.0
        self._sequence
        self._seq_idx = 0
        self._seq_start_ts = time.time()

        self._search_op = SearchOperator()
        self._advance_op = AdvanceOperator()
        self._align_op = AlignToGoalOperator()
        self._push_op = PushOperator()
        self._avoid_wall_op = AvoidWallOperator()
        self._operator_basic_op = OperatorBase()

    '''def tick(self) -> PipelineOutputDto:
        """Ejecuta un ciclo completo del FSM: visión → filtros → transición → motores."""
        now = time.time()
    
        # ── Paso 1: Obtener snapshot de visión ──
        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None
    
        goals = snap.get("goals", {})
        goal_visible = goals.get("yellow", False) or goals.get("blue", False)
        goal_cx = None
        if goals.get("yellow"):
            goal_cx = goals.get("yellow_cx")
        elif goals.get("blue"):
            goal_cx = goals.get("blue_cx")
    
        # ── Paso 2: FILTROS INSTANTÁNEOS anti falsos positivos ──
        if ball_visible:
            frame = self._vision.last_frame()
            if frame is not None:
                import cv2
                import numpy as np
                cx, cy = int(ball["cx"]), int(ball["cy"])
    
                patch_r = 3
                y0, y1 = max(0, cy - patch_r), min(frame.shape[0], cy + patch_r + 1)
                x0, x1 = max(0, cx - patch_r), min(frame.shape[1], cx + patch_r + 1)
    
                if x1 > x0 and y1 > y0:
                    patch_bgr = frame[y0:y1, x0:x1]
                    patch_hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
                    median_h = int(np.median(patch_hsv[:, :, 0]))
                    median_s = int(np.median(patch_hsv[:, :, 1]))
    
                    if 13 <= median_h <= 170:
                        log.info("event=ball_rejected reason=wrong_color hue=%s source=%s", median_h, ball.get("source"))
                        ball = None
                        ball_visible = False
                    elif median_s < 140:
                        log.info("event=ball_rejected reason=not_neon_enough sat=%s source=%s", median_s, ball.get("source"))
                        ball = None
                        ball_visible = False
    
            if ball_visible and hasattr(self._vision, "_yolo"):
                yolo_raw = self._vision._yolo.get_latest_output()
                ball_bbox = yolo_raw.get("ball_bbox")
                if ball_bbox is not None:
                    x1, y1, x2, y2, conf, cls_id = ball_bbox
                    w = max(1.0, float(x2 - x1))
                    h = max(1.0, float(y2 - y1))
    
                    if (h / w) > 1.4:
                        log.info("event=ball_rejected reason=tall_pillar_shape source=%s", ball.get("source"))
                        ball = None
                        ball_visible = False
    
        # ── Paso 3: Loggeo y actualización de última posición conocida ──
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
    
        if goal_visible and now - self._last_ball_log >= 0.5:
            log.info(
                "event=goal_detected yellow=%s blue=%s state=%s",
                goals.get("yellow"), goals.get("blue"), self._state,
            )
     
        # ── Paso 4: Transiciones del FSM ──
        if self._state == SEARCH:
            if ball_visible:
                self._state = ADVANCE
                log.info("event=state_change from=SEARCH to=ADVANCE")
     
        elif self._state == ADVANCE:
            if not ball_visible and (now - self._last_seen_ts > 0.2):
                self._state = SEARCH
                centro_x = self._vision.frame_width / 2.0
                direccion = -1 if self._last_ball_cx < centro_x else 1
                self._search_op.reset(direction=direccion)
                log.info("event=state_change from=ADVANCE to=SEARCH direction=%s", "left" if direccion == -1 else "right")
            elif ball_visible and ball["r"] >= BALL_CLOSE_RADIUS and goal_visible:
                self._state = ALIGN
                self._align_op.reset()
                log.info("event=state_change from=ADVANCE to=ALIGN ball_r=%s", ball["r"])
     
        elif self._state == ALIGN:
            if not ball_visible and (now - self._last_seen_ts > 0.5):
                self._state = SEARCH
                centro_x = self._vision.frame_width / 2.0
                direccion = -1 if self._last_ball_cx < centro_x else 1
                self._search_op.reset(direction=direccion)
                log.info("event=state_change from=ALIGN to=SEARCH reason=ball_lost")
            elif ball_visible and ball["r"] < (BALL_CLOSE_RADIUS - 10):
                self._state = ADVANCE
                log.info("event=state_change from=ALIGN to=ADVANCE reason=ball_moved_away r=%s", ball["r"])
            elif self._align_op.is_aligned():
                self._state = PUSH
                self._push_op.start()
                log.info("event=state_change from=ALIGN to=PUSH reason=aligned")
     
        elif self._state == PUSH:
            if self._push_op.is_done():
                self._state = SEARCH
                centro_x = self._vision.frame_width / 2.0
                direccion = -1 if self._last_ball_cx < centro_x else 1
                self._search_op.reset(direction=direccion)
                self._push_op.reset()
                log.info("event=state_change from=PUSH to=SEARCH reason=push_complete")
    
        # ── Paso 5: Ejecutar operador del estado actual ──
        v_left, v_right, dur_ms = 0.0, 0.0, STOP_DUR_MS
     
        if self._state == SEARCH:
            v_left, v_right, dur_ms = self._search_op.compute()
     
        elif self._state == ADVANCE:
            v_left, v_right, dur_ms = self._advance_op.compute(self._vision.frame_width, ball)
    
        elif self._state == ALIGN:
            v_left, v_right, dur_ms = self._align_op.compute(self._vision.frame_width, ball, goals)
     
        elif self._state == PUSH:
            v_left, v_right, dur_ms = self._push_op.compute()
    
        # ── Paso 6: Capa de seguridad — AvoidWall tiene prioridad máxima ──
        frame = self._vision.last_frame()
        evasion = self._avoid_wall_op.check_and_avoid(frame)
        if evasion is not None:
            v_left, v_right, dur_ms = evasion
            log.info("event=avoid_wall_activated action=reversing")
     
        # ── Paso 7: Enviar comandos a motores ──
        if v_left != 0 or v_right != 0:
            self._motors.drive(-v_left, v_right, dur_ms)
        else:
            self._motors.stop(dur_ms)'''

    def tick(self) -> PipelineOutputDto:
        ball_visible = False
        goal_visible = False
        goal_cx = None
        now = time.time()
        step, dur_ms = self._sequence[self._seq_idx]
        elapsed_ms = (now - self._seq_start_ts) * 1000

        if elapsed_ms >= dur_ms:
            self._seq_idx = (self._seq_idx + 1) % len(self._sequence)
            self._seq_start_ts = now
            step, dur_ms = self._sequence[self._seq_idx]

        v_left, v_right, _ = self._operator_basic_op.move(step)

        if v_left != 0 or v_right != 0:
            self._motors.drive(-v_left, v_right, dur_ms)
        else:
            self._motors.stop(dur_ms)

        return PipelineOutputDto(
            state=self._state,
            ball_visible=ball_visible,
            goal_visible=goal_visible,
            goal_cx=goal_cx,
            v_left=v_left,
            v_right=v_right,
            dur_ms=dur_ms,
            ts=now,
        )
        
    def run(self):
        self._running = True
        log.info("event=pipeline4_started mode=shoot_to_goal")
        while self._running:
            self.tick()
            time.sleep(0.03)

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline4_closed")
