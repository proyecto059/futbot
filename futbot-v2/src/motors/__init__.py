"""Paquete `motors` — control de motores y servos vía UART (/dev/ttyAMA0).

Punto de entrada único:
    from motors import MotorService

    motors = MotorService()
    motors.forward(speed=120)
    motors.drive(v_left=100, v_right=-50, dur_ms=140)
    motors.close()
"""

from motors.motor_service import MotorService

__all__ = ["MotorService"]
