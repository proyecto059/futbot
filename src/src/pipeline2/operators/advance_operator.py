"""Operador de avance — lógica simple: si hay pelota, avanza recto.

Este operador es el equivalente simplificado de ChaseOperator del pipeline
original, pero sin rotación proporcional ni persecución. Solo avanza recto
a velocidad constante.
"""

from __future__ import annotations

from pipeline2.utils import ADVANCE_DUR_MS, ADVANCE_SPEED


class AdvanceOperator:
    """Calcula velocidades de avance recto cuando la pelota es visible."""

    def compute(self, ball_visible: bool) -> tuple[float, float, int]:
        """Devuelve (v_left, v_right, dur_ms).

        Si la pelota es visible → avanza recto.
        Si no → velocidades en cero.
        """
        if ball_visible:
            return (float(ADVANCE_SPEED), float(ADVANCE_SPEED), ADVANCE_DUR_MS)
        return (0.0, 0.0, 0)