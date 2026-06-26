"""Operador de empuje — avanza recto a máxima velocidad para empujar la pelota.

Una vez iniciado, mantiene velocidad máxima por PUSH_DUR_MS y luego se desactiva.
"""

import time

from pipeline4.utils.pipeline_constants import PUSH_SPEED, PUSH_DUR_MS, STOP_DUR_MS


class PushOperator:
    def __init__(self):
        self._start_ts = 0.0
        self._active = False

    def start(self):
        self._start_ts = time.time()
        self._active = True

    def compute(self):
        if not self._active:
            return 0.0, 0.0, STOP_DUR_MS

        if self.is_done():
            self._active = False
            return 0.0, 0.0, STOP_DUR_MS

        return float(PUSH_SPEED), float(PUSH_SPEED), STOP_DUR_MS

    def is_done(self):
        return self._active and (time.time() - self._start_ts) > (PUSH_DUR_MS / 1000.0)

    def reset(self):
        self._active = False
