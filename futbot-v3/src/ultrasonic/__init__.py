"""Paquete `ultrasonic` — sensor ultrasónico I2C (0x77) para detección de obstáculos.

Punto de entrada único:
    from ultrasonic import UltrasonicService

    ultra = UltrasonicService()
    dto = ultra.tick()           # UltrasonicDto(distance_mm=48, ts=...)
    ultra.set_led(0xFF, 0, 0)   # LED rojo
    ultra.close()
"""

from ultrasonic.ultrasonic_service import UltrasonicService

__all__ = ["UltrasonicService"]
