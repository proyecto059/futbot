"""Conversión diferencial: velocidades de rueda → 4 valores de motor.

Responsabilidad: traducir ``v_left`` y ``v_right`` al cuarteto ``(m1, m2, m3, m4)``
que espera el firmware, aplicando un *cap* de velocidad máxima.

Reglas de mapeo:
    1. ``m1`` y ``m2`` siempre valen ``0.0`` (no son ruedas de tracción).
    2. ``m3`` = ``v_left`` (rueda izquierda directa).
    3. ``m4`` = ``-v_right`` (rueda derecha invertida por montaje físico).
    4. Si ``max(|v_left|, |v_right|)`` supera *cap*, se escala
       proporcionalmente para que ningún valor exceda el límite.

Uso::

    from motors.operators.differential_operator import DifferentialOperator

    diff = DifferentialOperator(cap=250.0)
    m1, m2, m3, m4 = diff.apply(v_left=120.0, v_right=-80.0)
    # → (0.0, 0.0, 120.0, 80.0)
"""

from __future__ import annotations

from motors.utils.motor_constants import DEFAULT_DIFF_CAP


class DifferentialOperator:
    """Traductor de velocidades de rueda a cuarteto de motor con cap."""

    def __init__(self, cap: float = DEFAULT_DIFF_CAP) -> None:
        self.cap = cap

    def apply(self, v_left: float, v_right: float) -> tuple[float, float, float, float]:
        """Convierte velocidades de rueda a ``(m1, m2, m3, m4)`` con cap."""
        mx = max(abs(v_left), abs(v_right))
        if mx > self.cap:
            s = self.cap / mx
            v_left *= s
            v_right *= s
        return (0.0, 0.0, v_left, -v_right)