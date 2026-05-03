"""Pipeline3 - Integra la cámara con rutina de seguimiento y Mapeo de Área.
Si ve la pelota -> la sigue (FOLLOW).
Si no la ve -> ejecuta la rutina "mapeoArea" (SEARCH).
"""

import logging
import time

IDLE = "IDLE"
SEARCH = "SEARCH"
FOLLOW = "FOLLOW"

SEARCH_SPEED = 23
SEARCH_TURN_DUR_MS = 500
SEARCH_PAUSE_DUR_MS = 800

STOP_DUR_MS = 1000

class Pipeline4Service:
    def __init__(self, vision, motors):
        self._vision = vision
        self._motors = motors
        self._state = IDLE
        self._running = False
        self._consecutive_detections = 0
        self._consecutive_misses = 0
        
        # Variables de mapeo de área
        self._search_phase = "turn"
        self._search_start_ts = 0
        self._search_direction = 1
        self._num_vueltas = 0
        self._last_move_ts = 0

    def tick(self):
        now = time.time()
        
        v_left = 0
        v_right = 0
        dur_ms = STOP_DUR_MS

        snap = self._vision.tick()
        ball = snap.get("ball")
        ball_visible = ball is not None

        prev_state = self._state

        if ball_visible:
            self._consecutive_misses = 0
            self._consecutive_detections += 1
            if self._consecutive_detections >= 2:
                if self._state != FOLLOW:
                    self._state = FOLLOW
        else:
            self._consecutive_detections = 0
            self._consecutive_misses += 1
            if self._consecutive_misses >= 3:
                if self._state != SEARCH:
                    self._state = SEARCH
                    self._search_phase = "turn"
                    self._search_start_ts = now
                    self._search_direction = 1
                    self._num_vueltas = 0

        if self._state != prev_state:
            log.info("state_change %s->%s ball_visible=%s", prev_state, self._state, ball_visible)

        if self._state == IDLE:
            v_left, v_right = 0, 0
            dur_ms = STOP_DUR_MS

        elif self._state == FOLLOW:
            if ball is not None:
                cx = ball.get("cx", 160)
                r = ball.get("r", 0)
                r = ball.get("r", 0)
                base_speed = 30
                
                # Avanza siempre recto hacia la pelota, sin importar qué tan cerca esté
                v_left, v_right = base_speed, base_speed
                
                dur_ms = 200
            else:
                v_left, v_right = 0, 0
                dur_ms = STOP_DUR_MS

        elif self._state == SEARCH:
            time_in_phase = now - self._search_start_ts

            if self._search_phase == "turn":
                v_left = SEARCH_SPEED * self._search_direction
                v_right = -SEARCH_SPEED * self._search_direction
                dur_ms = SEARCH_TURN_DUR_MS
                if time_in_phase > (SEARCH_TURN_DUR_MS / 1000.0):
                    self._search_phase = "pause"
                    self._search_start_ts = now

            elif self._search_phase == "pause":
                v_left, v_right = 0, 0
                dur_ms = STOP_DUR_MS
                if time_in_phase > (SEARCH_PAUSE_DUR_MS / 1000.0):
                    self._search_phase = "turn"
                    self._search_start_ts = now

        if v_left != 0 or v_right != 0:
            self._motors.drive(v_left, v_right, dur_ms)
            self._last_move_ts = now
        else:
            if now - self._last_move_ts > 0.05:
                self._motors.stop(STOP_DUR_MS)

        return {
            "state": self._state,
            "ball_visible": ball_visible,
            "v_left": v_left,
            "v_right": v_right,
            "ts": now,
        }

    def run(self):
        self._running = True
        log.info("event=pipeline3_started mode=mapeo_area_with_vision")
        while self._running:
            self.tick()
            time.sleep(0.03)

    def stop(self):
        self._running = False

    def close(self):
        self._running = False
        self._motors.stop(200)
        log.info("event=pipeline3_closed")

log = logging.getLogger("turbopi.pipeline3")