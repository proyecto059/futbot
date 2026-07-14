"""Operador base con movimientos modulares seleccionables por índice.

Convención de giro (igual que v3 pipeline_service.py):
  - Girar izquierda: v_left = -speed, v_right = speed
  - Girar derecha:   v_left = speed,  v_right = -speed
  - Se envía directo a motors.drive(v_left, v_right, dur_ms)
"""

import time


class OperatorBase:
    def __init__(self):
        self._step = 0
        self._step_start_ts = time.time()
        self._dur_ms = 1000
        self._sequence = [
            (0, 3000),   # avanzar 3s
            (2, 500),    # Aderecha 0.5s
            (0, 1500),   # avanzar 1.5s
            (2, 500),    # Aderecha 0.5s
            (0, 3000),   # avanzar 3s
            (2, 500),    # Aderecha 0.5s
            (0, 1500),   # avanzar 1.5s
            (2, 500),    # Aderecha 0.5s
        ]

    def move(self, step: int):
        moves = [
            (150.0,  150.0),   # 0: Avanzar
            (0,      150.0),   # 1: Adelante derecha
            (150.0,  0),       # 2: Adelante izquierda
            (-150.0, -150.0),  # 3: Retroceder
            (-150.0, 0),       # 4: Retroceder derecha
            (0,     -150.0),   # 5: Retroceder izquierda
        ]
        v_left, v_right = moves[step]
        return v_left, v_right, self._dur_ms

    def compute(self):
        now = time.time()
        elapsed_ms = (now - self._step_start_ts) * 1000

        if elapsed_ms >= self._dur_ms:
            self._step = (self._step + 1) % 6
            self._step_start_ts = now

        return self.move(self._step)

        time.sleep(1)

    def reset(self):
        self._step = 0
        self._step_start_ts = time.time()
