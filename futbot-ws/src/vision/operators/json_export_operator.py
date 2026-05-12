"""Ensambla el VisionOutputDto final y lo serializa al dict de salida.

Es la última pieza del pipeline: recibe DTOs individuales y los combina en el
shape público que consume `main.py`. Se mantiene aparte para poder testear
que la forma del JSON no cambia sin querer (contrato estable con la FSM).
"""

from __future__ import annotations

from typing import List, Optional

from vision.dto.ball_dto import BallDto
from vision.dto.goals_dto import GoalsDto
from vision.dto.line_dto import LineDto
from vision.dto.robot_dto import RobotDto
from vision.dto.vision_output_dto import VisionOutputDto


class JsonExportOperator:
    """Toma DTOs + debug y entrega el dict final (JSON-serializable)."""

    @staticmethod
    def build(
        ball: Optional[BallDto],
        robots: List[RobotDto],
        goals: GoalsDto,
        line: LineDto,
        ts: float,
        debug: Optional[dict] = None,
    ) -> dict:
        output = VisionOutputDto(
            ts=ts,
            ball=ball,
            robots=robots,
            goals=goals,
            line=line,
            debug=debug or {},
        )
        return output.to_dict()

    @staticmethod
    def empty(ts: float) -> dict:
        """Snapshot vacío con la estructura completa (campos null/[])."""
        return VisionOutputDto.empty(ts).to_dict()