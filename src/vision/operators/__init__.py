"""Operadores atómicos del pipeline.

Cada operador encapsula una responsabilidad única (captura, HSV, YOLO, fusión, ...).
`HybridVisionService` compone estos operadores para producir el snapshot JSON final.
"""

from vision.operators.ball_fusion_operator import BallFusionOperator
from vision.operators.frame_capture_operator import FrameCaptureOperator
from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from vision.operators.json_export_operator import JsonExportOperator
from vision.operators.white_line_detection_operator import WhiteLineDetectionOperator
from vision.operators.yolo_inference_operator import YoloInferenceOperator
from vision.operators.yolo_parser_operator import YoloParserOperator

__all__ = [
    "BallFusionOperator",
    "FrameCaptureOperator",
    "GoalColorDetectionOperator",
    "HsvBallDetectionOperator",
    "JsonExportOperator",
    "WhiteLineDetectionOperator",
    "YoloInferenceOperator",
    "YoloParserOperator",
]