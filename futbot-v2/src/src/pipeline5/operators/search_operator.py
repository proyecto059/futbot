"""Operador de búsqueda — gira sobre su eje y pausa cíclicamente.

Convención de giro (igual que v3 pipeline_service.py):
  - Girar izquierda: v_left = -speed, v_right = speed
  - Girar derecha:   v_left = speed,  v_right = -speed
  - Se envía directo a motors.drive(v_left, v_right, dur_ms)
"""

import time
from src.pipeline5.utils.pipeline_constants import (
    SEARCH_SPEED,
    SEARCH_TURN_DUR_MS,
    SEARCH_PAUSE_DUR_MS,
    STOP_DUR_MS,
)


class SearchOperator:
    def __init__(self):
        self._search_phase = "turn"
        self._search_start_ts = time.time()
        self._search_direction = 1  # 1 = derecha, -1 = izquierda

    def reset(self):
        """Reinicia el estado de búsqueda al entrar al estado SEARCH."""
        self._search_phase = "turn"
        self._search_start_ts = time.time()

    def compute(self):
        """Ejecuta la rutina de búsqueda paso a paso.

        Retorna (v_left, v_right, dur_ms) para pasar a motors.drive().
        Convención v3: signos opuestos = giro sobre eje.
        """
        now = time.time()
        time_in_phase = now - self._search_start_ts
        v_left, v_right = 0.0, 0.0
        dur_ms = STOP_DUR_MS

        if self._search_phase == "turn":
            # Giro sobre su eje — misma convención que v3:
            #   derecha (direction=1):  v_left=+speed, v_right=-speed
            #   izquierda (direction=-1): v_left=-speed, v_right=+speed
            speed = SEARCH_SPEED
            v_left = speed * self._search_direction
            v_right = -speed * self._search_direction
            dur_ms = SEARCH_TURN_DUR_MS
            if time_in_phase > (SEARCH_TURN_DUR_MS / 1000.0):
                self._search_phase = "pause"
                self._search_start_ts = now

        elif self._search_phase == "pause":
            v_left, v_right = 0.0, 0.0
            dur_ms = STOP_DUR_MS
            if time_in_phase > (SEARCH_PAUSE_DUR_MS / 1000.0):
                self._search_phase = "turn"
                self._search_start_ts = now

        return v_left, v_right, dur_ms
