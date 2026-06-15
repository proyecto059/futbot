"""Conversión diferencial: velocidades de rueda → 4 valores de motor.

Responsabilidad: traducir ``v_left`` y ``v_right`` al cuarteto ``(m1, m2, m3, m4)``
que espera el firmware, aplicando un *cap* de velocidad máxima.

Reglas de mapeo (validadas en pruebas reales):
    1. ``m1`` y ``m2`` siempre valen ``0.0`` (no son ruedas de tracción).
    2. ``m3`` = ``-v_right`` → controla la rueda derecha física.
    3. ``m4`` = ``-v_left`` → controla la rueda izquierda física.
    4. El signo negativo en ambos motores corrige la inversión física del hardware.
    5. Si ``max(|v_left|, |v_right|)`` supera *cap*, ambas velocidades se escalan
       proporcionalmente para mantener la relación sin exceder el límite.

Convención de control (IMPORTANTE):
    - Valores negativos en ``v_right`` producen avance en la rueda derecha.
    - Valores positivos en ``v_left`` producen avance en la rueda izquierda.
    - Ejemplo de avance recto:
        ``v_left = 80``, ``v_right = -80``

Uso::

    from motors.operators.differential_operator import DifferentialOperator

    diff = DifferentialOperator(cap=250.0)
    m1, m2, m3, m4 = diff.apply(v_left=120.0, v_right=-80.0)
    # → (0.0, 0.0, 80.0, -120.0)
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
        return (0.0, 0.0, -v_right, -v_left)
