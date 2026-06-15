"""Operador de avance — avanza hacia la pelota corrigiendo dirección.

Misma convención que ChaseOperator de v3:
  - Ambas ruedas positivas = avanzar.
  - Se usa drive(v_left, v_right, dur_ms).
  - Corrige la dirección basándose en la posición cx de la pelota.
"""

from src.pipeline6.utils.pipeline_constants import ADVANCE_SPEED


class AdvanceOperator:
    def __init__(self):
        self._last_cx = 160

    def compute(self, ball=None):
        """
        Retorna (v_left, v_right, dur_ms) para avanzar hacia la pelota.
        Si ball es None, avanza recto.
        """
        if ball is not None:
            self._last_cx = ball.get("cx", 160)

        frame_center = 160
        turn_factor = 0.15

        if self._last_cx < frame_center - 20:
            offset = frame_center - self._last_cx
            adjustment = offset * turn_factor
            v_left = ADVANCE_SPEED - adjustment
            v_right = ADVANCE_SPEED + adjustment
        elif self._last_cx > frame_center + 20:
            offset = self._last_cx - frame_center
            adjustment = offset * turn_factor
            v_left = ADVANCE_SPEED + adjustment
            v_right = ADVANCE_SPEED - adjustment
        else:
            v_left = ADVANCE_SPEED
            v_right = ADVANCE_SPEED

        return float(v_left), float(v_right), 100