"""Primitivas de movimiento de alto nivel para el robot.

Responsabilidad: ofrecer métodos semánticos (avanzar, retroceder, girar, stop)
que oculten los detalles de conversión diferencial y envío binario.

Cada primitiva sigue el mismo flujo:
    1. Convierte la intención en velocidades de rueda (v_left, v_right).
    2. Pasa por :class:`DifferentialOperator` para obtener el cuarteto de motores.
    3. Envía el burst al UART vía :class:`BurstOperator`.
    4. Pan/tilt se mantienen centrados en posición neutral (70°, 45°).

Uso::

    from motors.operators.burst_operator import BurstOperator
    from motors.operators.movement_operator import MovementOperator

    burst = BurstOperator(serial.Serial("/dev/ttyAMA0", 1_000_000))
    move = MovementOperator(burst)
    move.forward(speed=120, dur_ms=300)
    move.turn_left(speed=80, dur_ms=200)
    move.stop()
"""

from __future__ import annotations

import logging

from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import DEFAULT_DIFF_CAP, PAN_CENTER, TILT_CENTER

log = logging.getLogger("turbopi.motors")


class MovementOperator:
    """Primitivas de movimiento que delegan en DifferentialOperator + BurstOperator."""

    def __init__(self, burst: BurstOperator, cap: float = DEFAULT_DIFF_CAP) -> None:
        self._burst = burst
        self._diff = DifferentialOperator(cap=cap)

    def forward(self, speed: float, dur_ms: int = 300) -> None:
        _, _, m3, m4 = self._diff.apply(speed, speed)
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)

    def reverse(self, speed: float, dur_ms: int = 300) -> None:
        _, _, m3, m4 = self._diff.apply(-speed, -speed)
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)

    def turn_left(self, speed: float, dur_ms: int = 300) -> None:
        _, _, m3, m4 = self._diff.apply(-speed, speed)
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)

    def turn_right(self, speed: float, dur_ms: int = 300) -> None:
        _, _, m3, m4 = self._diff.apply(speed, -speed)
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)

    def stop(self, dur_ms: int = 300) -> None:
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, 0.0, 0.0)

    def drive(self, v_left: float, v_right: float, dur_ms: int = 140) -> None:
        _, _, m3, m4 = self._diff.apply(v_left, v_right)
        self._burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)
