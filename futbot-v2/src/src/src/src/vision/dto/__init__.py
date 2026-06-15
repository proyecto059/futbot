"""Data Transfer Objects: shape estable del pipeline hacia el consumidor (FSM)."""

from vision.dto.ball_dto import BallDto
from vision.dto.frame_dto import FrameDto
from vision.dto.goals_dto import GoalsDto
from vision.dto.line_dto import LineDto
from vision.dto.robot_dto import RobotDto
from vision.dto.vision_output_dto import VisionOutputDto

__all__ = [
    "BallDto",
    "FrameDto",
    "GoalsDto",
    "LineDto",
    "RobotDto",
    "VisionOutputDto",
]
