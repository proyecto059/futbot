"""DTO de salida de un tick del pipeline2."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pipeline2OutputDto:
    """Snapshot del estado y comandos de motor en un tick del pipeline2."""

    state: str
    ball_visible: bool
    v_left: float
    v_right: float
    dur_ms: int
    ts: float

    def to_dict(self) -> dict:
        """Serializa el DTO a un dict JSON-serializable."""
        return {
            "state": self.state,
            "ball_visible": self.ball_visible,
            "v_left": self.v_left,
            "v_right": self.v_right,
            "dur_ms": self.dur_ms,
            "ts": self.ts,
        }