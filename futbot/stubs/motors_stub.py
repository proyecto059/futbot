"""Motores stub: registra comandos en vez de enviarlos por UART.

Usado en modo FUTBOT_MODE=stub para desarrollo y pruebas sin hardware real.
"""

from __future__ import annotations

from motors import MotorCommand


class MotorsStub:
    """Motores fake que registran comandos para desarrollo local.

    En lugar de enviar comandos por UART al driver de motores, los almacena
    en una lista interna accesible via get_history(). Util para verificar
    que el pipeline FSM produce los comandos esperados.

    Atributos:
        _history: Lista cronologica de todos los comandos registrados.
    """

    def __init__(self, config) -> None:
        """Inicializa el stub con historial vacio.

        Args:
            config: Instancia de Config (conservada por compatibilidad,
                no se usa en el stub).
        """
        self._cfg = config
        self._history: list[MotorCommand] = []

    def send(self, cmd: MotorCommand) -> None:
        """Registra una copia del comando en el historial.

        Args:
            cmd: Comando de movimiento a registrar.
        """
        self._history.append(MotorCommand(
            left_speed=cmd.left_speed,
            right_speed=cmd.right_speed,
            dur_ms=cmd.dur_ms,
            pan_angle=cmd.pan_angle,
            tilt_angle=cmd.tilt_angle,
        ))

    def stop(self, dur_ms: int = 300) -> None:
        """Registra un comando de parada (velocidades cero).

        Args:
            dur_ms: Duracion del comando de parada.
        """
        self._history.append(MotorCommand(0.0, 0.0, dur_ms))

    def close(self) -> None:
        """No-op. No hay conexion UART que cerrar."""

    def get_history(self) -> list[MotorCommand]:
        """Devuelve el historial completo de comandos registrados.

        Util en tests para verificar que el pipeline produjo los comandos
        esperados en el orden correcto.

        Returns:
            Lista de MotorCommand en orden cronologico.
        """
        return self._history
