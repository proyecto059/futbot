"""Envío de paquetes binarios al UART — protocolo propietario del driver.

Responsabilidad única: construir y escribir frames binarios al puerto serie.

Protocolo de trama:
    ``0xAA 0x55`` + ``cmd`` + ``len`` + ``payload`` + ``CRC8``

Dos frames por cada llamada a :meth:`send`:

1. **Servo frame** (cmd ``0x04``) — pan y tilt como PWM 500–2500 µs.
2. **Motor frame** (cmd ``0x03``) — 4 motores como float32 little-endian.

Thread-safety garantizada por un :class:`threading.Lock` que protege la
escritura serial, evitando que hilos concurrentes intercalen bytes.

Uso::

    import serial
    from motors.operators.burst_operator import BurstOperator

    ser = serial.Serial("/dev/ttyAMA0", 1_000_000)
    burst = BurstOperator(ser)
    burst.send(pan=70, tilt=45, dur_ms=140,
               m1=0.0, m2=0.0, m3=100.0, m4=-100.0)
"""

from __future__ import annotations

import logging
import struct
import threading

import serial

from motors.utils.motor_constants import SERVO_PAN_ID, SERVO_TILT_ID, crc8

log = logging.getLogger("turbopi.motors")


class BurstOperator:
    """Serializa y envía pares servo+motor frames al UART."""

    def __init__(self, ser: serial.Serial) -> None:
        self._ser = ser
        self._lock = threading.Lock()

    def send(
        self,
        pan: float,
        tilt: float,
        dur_ms: int,
        m1: float,
        m2: float,
        m3: float,
        m4: float,
    ) -> None:
        """Envía un burst de dos frames (servo + motor) al UART.

        Pasos:
            1. Convierte ángulos pan/tilt (0–180°) a PWM (500–2500 µs).
            2. Construye el payload de servos y empaqueta en frame cmd 0x04.
            3. Empaqueta los 4 motores como float32 LE en frame cmd 0x03.
            4. Calcula CRC8 de cada frame y lo añade como byte final.
            5. Escribe ambos frames de forma atómica bajo Lock.
        """
        pp = int(500 + (max(0, min(180, pan)) / 180.0) * 2000)
        tp = int(500 + (max(0, min(180, tilt)) / 180.0) * 2000)
        d = int(dur_ms)

        sd = bytearray(
            [
                0x01,
                d & 0xFF,
                (d >> 8) & 0xFF,
                2,
                SERVO_PAN_ID,
                pp & 0xFF,
                (pp >> 8) & 0xFF,
                SERVO_TILT_ID,
                tp & 0xFF,
                (tp >> 8) & 0xFF,
            ]
        )
        fs = bytearray(b"\xaa\x55") + bytes([0x04, len(sd)]) + sd
        fs.append(crc8(fs[2:]))

        md = bytearray([0x05, 4])
        for mid, val in ((1, m1), (2, m2), (3, m3), (4, m4)):
            md += struct.pack("<Bf", mid - 1, float(val))
        fm = bytearray(b"\xaa\x55") + bytes([0x03, len(md)]) + md
        fm.append(crc8(fm[2:]))

        with self._lock:
            self._ser.write(fs + fm)
