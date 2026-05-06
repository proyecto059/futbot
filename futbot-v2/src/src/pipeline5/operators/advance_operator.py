"""Operador de avance — avanza recto hacia la pelota.

Misma convención que ChaseOperator de v3:
  - Ambas ruedas positivas = avanzar.
  - Se usa drive(v_left, v_right, dur_ms).
"""

from src.pipeline5.utils.pipeline_constants import ADVANCE_SPEED


class AdvanceOperator:
    def compute(self):
        """Retorna (v_left, v_right, dur_ms) para avanzar recto."""
        return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100
