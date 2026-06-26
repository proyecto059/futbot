"""Operador de búsqueda — gira sobre su eje y pausa cíclicamente.

Convención de giro (igual que v3 pipeline_service.py):
  - Girar izquierda: v_left = -speed, v_right = speed
  - Girar derecha:   v_left = speed,  v_right = -speed
  - Se envía directo a motors.drive(v_left, v_right, dur_ms)
"""

import time
<<<<<<< HEAD:futbot-v2/src/pipeline5/operators/search_operator.py
from pipeline5.utils.pipeline_constants import (
=======
from src.pipeline4.utils.pipeline_constants import (
>>>>>>> 5f36520a1fd37a0d5cef277410929cc404fd1920:futbot-v2/src/src/pipeline4/operators/search_operator.py
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

    def reset(self, direction=1):
        """Reinicia el estado de búsqueda al entrar al estado SEARCH.
        
        Args:
            direction (int): 1 para girar a la derecha, -1 para izquierda.
        """
        self._search_phase = "turn"
        self._search_start_ts = time.time()
        self._search_direction = direction

    def compute(self):
        """Ejecuta la rutina de búsqueda paso a paso.

        Retorna (v_left, v_right, dur_ms) para pasar a motors.drive().
        Convención v3: signos opuestos = giro sobre eje.

        Rutina cíclica de 2 fases:
            fase "turn" (500ms)  → gira sobre su eje en la dirección establecida
            fase "pause" (800ms) → se detiene para dar tiempo al sistema de visión

        Se envían pulsos cortos (STOP_DUR_MS=100ms) para que el motor pueda
        ser interrumpido rápidamente si se detecta la pelota.
        """
        now = time.time()
        time_in_phase = now - self._search_start_ts
        v_left, v_right = 0.0, 0.0
        dur_ms = STOP_DUR_MS

        if self._search_phase == "turn":
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
                self._search_start_ts = now

        return v_left, v_right, dur_ms
