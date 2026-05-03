"""Constantes del sensor ultrasónico: bus I2C, dirección, registro LED, umbrales."""

from ultrasonic.utils.ultrasonic_constants import (
    DIST_TRIGGER_MM,
    I2C_BUS_NUM,
    ULTRASONIC_ADDR,
    ULTRASONIC_LED_REG,
)

__all__ = [
    "DIST_TRIGGER_MM",
    "I2C_BUS_NUM",
    "ULTRASONIC_ADDR",
    "ULTRASONIC_LED_REG",
]