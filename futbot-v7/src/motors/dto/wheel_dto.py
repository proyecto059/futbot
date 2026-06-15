"""DTO de velocidades de rueda izquierda y derecha."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WheelDto:
    """Par de velocidades (v_left, v_right) para las dos ruedas de tracción."""

    v_left: float
    v_right: float

    def to_tuple(self) -> tuple[float, float]:
        """Devuelve ``(v_left, v_right)`` como tupla nativa."""
        return (self.v_left, self.v_right)

    @staticmethod
    def forward(speed: float) -> WheelDto:
        """Ambas ruedas avanzan a la misma velocidad."""
        return WheelDto(v_left=speed, v_right=speed)

    @staticmethod
    def reverse(speed: float) -> WheelDto:
        """Ambas ruedas retroceden a la misma velocidad."""
        return WheelDto(v_left=-speed, v_right=-speed)

    @staticmethod
    def turn_left(speed: float) -> WheelDto:
        """Giro a la izquierda: rueda izquierda atrás, derecha adelante."""
        return WheelDto(v_left=-speed, v_right=speed)

    @staticmethod
    def turn_right(speed: float) -> WheelDto:
        """Giro a la derecha: rueda izquierda adelante, derecha atrás."""
        return WheelDto(v_left=speed, v_right=-speed)

    @staticmethod
    def stop() -> WheelDto:
        """Ambas ruedas detenidas."""
        return WheelDto(v_left=0.0, v_right=0.0)
