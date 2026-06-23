"""Motores stub: registra comandos en vez de enviarlos por UART."""

from __future__ import annotations

from motors import MotorCommand


class MotorsStub:
    """Motores fake que loguean comandos para desarrollo local."""

    def __init__(self, config) -> None:
        self._cfg = config
        self._history: list[MotorCommand] = []

    def send(self, cmd: MotorCommand) -> None:
        self._history.append(MotorCommand(
            left_speed=cmd.left_speed,
            right_speed=cmd.right_speed,
            dur_ms=cmd.dur_ms,
            pan_angle=cmd.pan_angle,
            tilt_angle=cmd.tilt_angle,
        ))

    def stop(self, dur_ms: int = 300) -> None:
        self._history.append(MotorCommand(0.0, 0.0, dur_ms))

    def close(self) -> None:
        pass

    def get_history(self) -> list[MotorCommand]:
        return self._history
