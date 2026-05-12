"""Fachada del sensor ultrasónico (punto de entrada único).

Este módulo NO contiene lógica de I2C — solo orquesta los operadores de
lectura de distancia y control del LED RGB integrado.

Un ``threading.Lock`` compartido protege el bus SMBus para que las operaciones
de lectura y escritura LED no se pisen entre sí.

API pública:
    tick()     → ``UltrasonicDto`` con distancia en mm y timestamp.
    set_led()  → Cambia el color del LED RGB (opcionalmente parpadea).
    close()    → Libera el bus I2C.

Ejemplo:
    ultra = UltrasonicService()
    try:
        while running:
            dto = ultra.tick()
            if dto.distance_mm and dto.distance_mm < 250:
                ultra.set_led(0xFF, 0, 0)   # obstáculo cercano → rojo
    finally:
        ultra.close()
"""

from __future__ import annotations

import logging
import threading

from smbus2 import SMBus

from ultrasonic.dto.ultrasonic_dto import UltrasonicDto
from ultrasonic.operators.ultrasonic_led_operator import UltrasonicLedOperator
from ultrasonic.operators.ultrasonic_read_operator import UltrasonicReadOperator
from ultrasonic.utils.ultrasonic_constants import (
    I2C_BUS_NUM,
    LED_INIT_R,
    LED_INIT_G,
    LED_INIT_B,
)

log = logging.getLogger("turbopi.ultrasonic")


class UltrasonicService:
    def __init__(self) -> None:
        self._bus = SMBus(I2C_BUS_NUM)
        self._lock = threading.Lock()
        self._read_op = UltrasonicReadOperator(self._bus, self._lock)
        self._led_op = UltrasonicLedOperator(self._bus, self._lock)
        self._led_op.set_led(LED_INIT_R, LED_INIT_G, LED_INIT_B)

    def tick(self) -> UltrasonicDto:
        """Realiza una lectura de distancia y devuelve un DTO inmutable."""
        return self._read_op.read()

    def set_led(self, r: int, g: int, b: int, blink: bool = False) -> None:
        """Cambia el color del LED RGB integrado en el sensor.

        Args:
            r, g, b: Componentes de color (0–255).
            blink: Si es ``True`` el LED parpadea.
        """
        self._led_op.set_led(r, g, b, blink=blink)

    def close(self) -> None:
        """Libera el bus SMBus. Debe llamarse al terminar el programa."""
        self._bus.close()