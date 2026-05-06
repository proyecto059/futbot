"""Parser puro: bbox crudos de YOLO → DTOs (sin estado, sin hilos, sin OpenCV)."""

from __future__ import annotations

from typing import List, Optional, Tuple

from vision.dto.ball_dto import BallDto
from vision.dto.robot_dto import RobotDto


class YoloParserOperator:
    """Convierte la salida cruda de `YoloInferenceOperator` a DTOs tipados.

    Es puro (sin estado ni locks) para que sea trivial de testear con bboxes
    sintéticos y para no contaminar el hilo YOLO con lógica de DTOs.
    """

    @staticmethod
    def _bbox_to_ball(
        bbox: Tuple[float, float, float, float, float, int],
    ) -> BallDto:
        x1, y1, x2, y2, conf, _cls = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        r = max(x2 - x1, y2 - y1) / 2.0
        return BallDto(
            cx=int(cx),
            cy=int(cy),
            r=float(r),
            conf=float(conf),
            source="yolo",
        )

    @staticmethod
    def _bbox_to_robot(
        bbox: Tuple[float, float, float, float, float, int],
    ) -> RobotDto:
        x1, y1, x2, y2, conf, _cls = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        r = max(x2 - x1, y2 - y1) / 2.0
        return RobotDto(
            bbox=(int(x1), int(y1), int(x2), int(y2)),
            cx=int(cx),
            cy=int(cy),
            r=float(r),
            conf=float(conf),
        )

    @classmethod
    def parse(cls, raw: dict) -> Tuple[Optional[BallDto], List[RobotDto]]:
        """Entrada: dict devuelto por `YoloInferenceOperator.get_latest_output()`.

        Salida: (ball opcional, lista de robots). Si no hay output del worker
        todavía (`ball_bbox=None, robot_bboxes=[]`), devuelve `(None, [])`.
        """
        ball_bbox = raw.get("ball_bbox")
        robot_bboxes = raw.get("robot_bboxes", [])
        ball = cls._bbox_to_ball(ball_bbox) if ball_bbox is not None else None
        robots = [cls._bbox_to_robot(b) for b in robot_bboxes]
        return ball, robots
