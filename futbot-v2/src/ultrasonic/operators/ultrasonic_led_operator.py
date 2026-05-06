"""Control del LED RGB integrado en el sensor ultrasónico.

Escribe 7 bytes al registro LED (0x02) del sensor:
    ``[mode, r, g, b, r, g, b]``

Modos soportados:
    ``0x00`` — color estático.
    ``0x01`` — parpadeo con los mismos colores.

Thread-safe: utiliza el ``threading.Lock`` compartido para proteger el bus
SMBus de accesos concurrentes desde el operador de lectura.
"""

from __future__ import annotations

import logging
import threading

from smbus2 import SMBus

from ultrasonic.utils.ultrasonic_constants import ULTRASONIC_ADDR, ULTRASONIC_LED_REG

log = logging.getLogger("turbopi.ultrasonic")


class UltrasonicLedOperator:
    def __init__(self, bus: SMBus, lock: threading.Lock) -> None:
        self._bus = bus
        self._lock = lock

    def set_led(self, r: int, g: int, b: int, blink: bool = False) -> None:
        """Envía el color y modo al LED del sensor.

        Args:
            r, g, b: Componentes de color (0–255).
            blink: ``True`` para modo parpadeo, ``False`` para estático.
        """
        mode = 0x01 if blink else 0x00
        data = [mode, r, g, b, r, g, b]
        with self._lock:
            try:
                self._bus.write_i2c_block_data(
                    ULTRASONIC_ADDR, ULTRASONIC_LED_REG, data
                )
            except Exception as e:
                log.warning("Ultrasonic LED error: %s", e)
