"""Fachada de movimiento — serializa comandos de alto nivel al UART.

No contiene lógica de protocolo binario ni conversión diferencial; delega
en :class:`MovementOperator` que a su vez usa :class:`BurstOperator`.

Flujo por cada llamada:
    1. El método público (``forward``, ``drive``, …) reenvía al ``MovementOperator``.
    2. ``MovementOperator`` convierte la intención a velocidades de rueda.
    3. ``BurstOperator`` empaqueta y envía los bytes al puerto serie.

Uso::

    from motors import MotorService

    motors = MotorService()
    motors.forward(speed=120, dur_ms=300)
    motors.drive(v_left=100, v_right=-50, dur_ms=140)
    motors.stop()
    motors.close()
"""

from __future__ import annotations

import logging

import serial

from motors.operators.burst_operator import BurstOperator
from motors.operators.movement_operator import MovementOperator
from motors.utils.motor_constants import SERIAL_BAUD, SERIAL_PORT

log = logging.getLogger("turbopi.motors")


class MotorService:
    """Fachada única para primitivas de movimiento del robot.

    Abre la conexión UART al instanciar y la cierra con :meth:`close`.
    """

    def __init__(self) -> None:
        self._ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD)
        self._burst = BurstOperator(self._ser)
        self._movement = MovementOperator(self._burst)
        log.info("UART conectado: %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)

    def forward(self, speed: float, dur_ms: int = 300) -> None:
        self._movement.forward(speed, dur_ms=dur_ms)

    def reverse(self, speed: float, dur_ms: int = 300) -> None:
        self._movement.reverse(speed, dur_ms=dur_ms)

    def turn_left(self, speed: float, dur_ms: int = 300) -> None:
        self._movement.turn_left(speed, dur_ms=dur_ms)

    def turn_right(self, speed: float, dur_ms: int = 300) -> None:
        self._movement.turn_right(speed, dur_ms=dur_ms)

    def stop(self, dur_ms: int = 300) -> None:
        self._movement.stop(dur_ms=dur_ms)

    def drive(self, v_left: float, v_right: float, dur_ms: int = 140) -> None:
        self._movement.drive(v_left, v_right, dur_ms=dur_ms)

    def close(self) -> None:
        self._ser.close()
        log.info("UART cerrado")
