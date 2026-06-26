"""DTO (Data Transfer Object) para la salida de cada tick del pipeline."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PipelineOutputDto:
    """Snapshot inmutable del estado FSM y comandos de motor en un tick.

    Atributos:
        state: Estado actual de la FSM ("SEARCH", "ADVANCE", "ALIGN" o "PUSH").
        ball_visible: True si se detectó pelota en este tick (post-filtros).
        goal_visible: True si se detectó portería (yellow o blue) en este tick.
        goal_cx: Centro X de la portería objetivo en píxeles, o None.
        v_left: Velocidad PWM enviada a la rueda izquierda (-255 a 255).
        v_right: Velocidad PWM enviada a la rueda derecha (-255 a 255).
        dur_ms: Duración del pulso de motor en milisegundos.
        ts: Timestamp Unix del momento en que se generó este tick.
    """
    state: str
    ball_visible: bool
    goal_visible: bool = False
    goal_cx: Optional[float] = None
    v_left: float = 0.0
    v_right: float = 0.0
    dur_ms: int = 100
    ts: float = 0.0

    def to_dict(self) -> dict:
        """Serializa el DTO a un diccionario JSON-serializable."""
        return {
            "state": self.state,
            "ball_visible": self.ball_visible,
            "goal_visible": self.goal_visible,
            "goal_cx": self.goal_cx,
            "v_left": self.v_left,
            "v_right": self.v_right,
            "dur_ms": self.dur_ms,
            "ts": self.ts,
        }
