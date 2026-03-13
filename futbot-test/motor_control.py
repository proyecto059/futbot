"""
Motor control for dual DC motors via RPi.GPIO PWM.
GPIO pins (BCM): Motor A DIR=2 PWM=5, Motor B DIR=4 PWM=6
H-bridge DIR+PWM scheme (e.g. L298N).
"""
from config import (
    MOTOR_A_DIR, MOTOR_A_PWM, MOTOR_B_DIR, MOTOR_B_PWM,
    PWM_FREQ, MAX_SPEED, PID_KP, PID_KI, PID_KD,
)


class PIDController:
    """Pure-Python PID — no GPIO dependency, fully testable."""

    def __init__(
        self,
        kp: float = PID_KP,
        ki: float = PID_KI,
        kd: float = PID_KD,
        max_output: float = float(MAX_SPEED),
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.max_output = max_output
        self._integral = 0.0
        self._prev_error = 0.0

    def update(self, error: float, dt: float) -> float:
        self._integral += error * dt
        derivative = (error - self._prev_error) / dt if dt > 0 else 0.0
        self._prev_error = error
        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(-self.max_output, min(self.max_output, output))

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0


class MotorController:
    """
    Controls dual DC motors. Lazy-imports RPi.GPIO so module
    can be imported on non-RPi for unit tests.
    """

    def __init__(self):
        self._gpio = None
        self._pwm_a = None
        self._pwm_b = None
        self._direction_pid = PIDController()

    def setup(self):
        import RPi.GPIO as GPIO
        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        for pin in (MOTOR_A_DIR, MOTOR_A_PWM, MOTOR_B_DIR, MOTOR_B_PWM):
            GPIO.setup(pin, GPIO.OUT)
        self._pwm_a = GPIO.PWM(MOTOR_A_PWM, PWM_FREQ)
        self._pwm_b = GPIO.PWM(MOTOR_B_PWM, PWM_FREQ)
        self._pwm_a.start(0)
        self._pwm_b.start(0)

    def apply(self, left_speed: float, right_speed: float):
        """
        Speed: -MAX_SPEED to +MAX_SPEED.
        Positive = forward, negative = backward.
        """
        if self._gpio is None:
            return
        GPIO = self._gpio

        def _set_motor(dir_pin, pwm, speed):
            GPIO.output(dir_pin, GPIO.HIGH if speed >= 0 else GPIO.LOW)
            pwm.ChangeDutyCycle(min(abs(speed), MAX_SPEED))

        _set_motor(MOTOR_A_DIR, self._pwm_a, left_speed)
        _set_motor(MOTOR_B_DIR, self._pwm_b, right_speed)

    def forward(self, speed: float = MAX_SPEED):
        self.apply(speed, speed)

    def turn_right(self, speed: float = MAX_SPEED * 0.6):
        self.apply(speed, -speed)

    def turn_left(self, speed: float = MAX_SPEED * 0.6):
        self.apply(-speed, speed)

    def stop(self):
        self.apply(0, 0)

    def cleanup(self):
        if self._gpio:
            self.stop()
            self._gpio.cleanup()
