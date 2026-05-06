"""DTO de salida final del pipeline — el JSON que consume el FSM (`main.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from vision.dto.ball_dto import BallDto, ball_to_dict
from vision.dto.goals_dto import GoalsDto
from vision.dto.line_dto import LineDto
from vision.dto.robot_dto import RobotDto


@dataclass(frozen=True)
class VisionOutputDto:
    """Snapshot unificado del estado visual del robot en un tick.

    Shape estable — cualquier campo puede ser None/vacío, pero las llaves
    siempre están presentes para que el consumidor no tenga que chequear
    existencia.
    ts: timestamp
    ball: pelota
    robots: lista de robots
    goals: porterias
    line: linea
    debug: diccionario de debug
    """

    ts: float
    ball: Optional[BallDto]
    robots: List[RobotDto]
    goals: GoalsDto
    line: LineDto
    debug: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ts": float(self.ts),
            "ball": ball_to_dict(self.ball),
            "robots": [r.to_dict() for r in self.robots],
            "goals": self.goals.to_dict(),
            "line": self.line.to_dict(),
            "debug": dict(self.debug),
        }

    @classmethod
    def empty(cls, ts: float) -> "VisionOutputDto":
        """Snapshot vacío (cuando aún no hay frame o todo falla)."""
        return cls(
            ts=ts,
            ball=None,
            robots=[],
            goals=GoalsDto.empty(),
            line=LineDto.empty(),
            debug={},
        )
