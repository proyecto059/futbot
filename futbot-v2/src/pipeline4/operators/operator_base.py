"""Operador de búsqueda — gira sobre su eje y pausa cíclicamente.

Convención de giro (igual que v3 pipeline_service.py):
  - Girar izquierda: v_left = -speed, v_right = speed
  - Girar derecha:   v_left = speed,  v_right = -speed
  - Se envía directo a motors.drive(v_left, v_right, dur_ms)
"""

import time
from pipeline4.utils.pipeline_constants import (
    SEARCH_SPEED,
    SEARCH_TURN_DUR_MS,
    SEARCH_PAUSE_DUR_MS,
    STOP_DUR_MS,
)


class OperatorBase:
    def __init__(self):
        self._search_phase = "turn"
        self._search_start_ts = time.time()
        self._search_direction = 1  # 1 = derecha, -1 = izquierda

    def reset(self, direction=1):
        self._search_phase = "turn"
        self._search_start_ts = time.time()
        self._search_direction = direction

    def compute(self):
        now = time.time()
        time_in_phase = now - self._search_start_ts
        v_left, v_right = 180.0, 180.0
        dur_ms = 1000

        """if self._search_phase == "turn":
            # Giro sobre su eje:
            #   direction=1 (derecha):   v_left=+speed, v_right=-speed
            #   direction=-1 (izquierda): v_left=-speed, v_right=+speed
            speed = SEARCH_SPEED
            v_left = speed * self._search_direction
            v_right = -speed * self._search_direction
            dur_ms = STOP_DUR_MS  # Pulso corto para respuesta rápida a detección
            if time_in_phase > (SEARCH_TURN_DUR_MS / 1000.0):
                self._search_phase = "pause"
                self._search_start_ts = now

        elif self._search_phase == "pause":
            # Detenido: damos tiempo a que el sistema de visión procese
            v_left, v_right = 0.0, 0.0
            dur_ms = STOP_DUR_MS
            if time_in_phase > (SEARCH_PAUSE_DUR_MS / 1000.0):
                self._search_phase = "turn"
                self._search_start_ts = now"""

        return v_left, v_right, dur_ms
