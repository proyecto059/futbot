"""Lectura sincrónica de distancia vía I2C (sensor ultrasónico 0x77).

Flujo de bajo nivel:
    1. Envía ``[0x00]`` al registro 0 para disparar la medición.
    2. Lee 2 bytes (little-endian) con la distancia en milímetros.
    3. Limita el valor a 5000 mm (máximo físico del sensor).

Thread-safe: utiliza el ``threading.Lock`` compartido para proteger el bus
SMBus de accesos concurrentes desde el operador LED.

En caso de error de comunicación devuelve ``UltrasonicDto(distance_mm=None)``
para que el consumidor nunca reciba una excepción sin manejar.
"""

from __future__ import annotations

import logging
import time
import threading
from typing import Optional

from smbus2 import SMBus, i2c_msg

from ultrasonic.dto.ultrasonic_dto import UltrasonicDto
from ultrasonic.utils.ultrasonic_constants import ULTRASONIC_ADDR

log = logging.getLogger("turbopi.ultrasonic")


class UltrasonicReadOperator:
    def __init__(self, bus: SMBus, lock: threading.Lock) -> None:
        self._bus = bus
        self._lock = lock

    def read(self) -> UltrasonicDto:
        """Realiza una lectura I2C y devuelve la distancia en mm."""
        now = time.time()
        with self._lock:
            try:
                w = i2c_msg.write(ULTRASONIC_ADDR, [0])
                self._bus.i2c_rdwr(w)
                r = i2c_msg.read(ULTRASONIC_ADDR, 2)
                self._bus.i2c_rdwr(r)
                distance = min(int.from_bytes(bytes(r), "little"), 5000)
                return UltrasonicDto(distance_mm=distance, ts=now)
            except Exception as e:
                log.warning("Ultrasonic read error: %s", e)
                return UltrasonicDto(distance_mm=None, ts=now)