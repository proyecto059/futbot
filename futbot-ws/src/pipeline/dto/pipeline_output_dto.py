"""DTO de salida de un tick del pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PipelineOutputDto:
    """Snapshot del estado FSM y comandos de motor en un tick.

    Campos v2 (v_left, v_right, dur_ms, ts) añadidos para telemetría.
    El campo `ball` es opcional — lo usa el módulo de comunicación WebSocket
    para construir el estado local que envía al robot opuesto.
    """

    state: str
    v_left: float = 0.0
    v_right: float = 0.0
    dur_ms: int = 0
    ts: float = 0.0
    ball: Optional[dict] = field(default=None, compare=False)

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "v_left": self.v_left,
            "v_right": self.v_right,
            "dur_ms": self.dur_ms,
            "ts": self.ts,
        }