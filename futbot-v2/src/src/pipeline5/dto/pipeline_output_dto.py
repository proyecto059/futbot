"""DTO (Data Transfer Object) para la salida de cada tick del pipeline."""

from dataclasses import dataclass

@dataclass(frozen=True)
class PipelineOutputDto:
    """Snapshot inmutable del estado FSM y comandos de motor en un tick.

    Atributos:
        state: Estado actual de la FSM ("SEARCH" o "ADVANCE").
        ball_visible: True si se detectó pelota en este tick (post-filtros).
        v_left: Velocidad PWM enviada a la rueda izquierda (-255 a 255).
        v_right: Velocidad PWM enviada a la rueda derecha (-255 a 255).
        dur_ms: Duración del pulso de motor en milisegundos.
        ts: Timestamp Unix del momento en que se generó este tick.
    """
    state: str
    ball_visible: bool
    v_left: float
    v_right: float
    dur_ms: int
    ts: float

    def to_dict(self) -> dict:
        """Serializa el DTO a un diccionario JSON-serializable."""
        return {
            "state": self.state,
            "ball_visible": self.ball_visible,
            "v_left": self.v_left,
            "v_right": self.v_right,
            "dur_ms": self.dur_ms,
            "ts": self.ts,
        }
