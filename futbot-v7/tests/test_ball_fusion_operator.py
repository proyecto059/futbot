import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vision.dto.ball_dto import BallDto
from vision.operators.ball_fusion_operator import BallFusionOperator


def test_fusion_ignores_yolo_fallback_by_default():
    fusion = BallFusionOperator(cache_ttl=0.5)
    yolo = BallDto(cx=59, cy=104, r=14.1, conf=0.9, source="yolo")

    assert fusion.merge(hsv_ball=None, yolo_ball=yolo, now_ts=1.0) is None


def test_fusion_does_not_cache_ignored_yolo_detection():
    fusion = BallFusionOperator(cache_ttl=0.5)
    yolo = BallDto(cx=59, cy=104, r=14.1, conf=0.9, source="yolo")

    fusion.merge(hsv_ball=None, yolo_ball=yolo, now_ts=1.0)

    assert fusion.merge(hsv_ball=None, yolo_ball=None, now_ts=1.1) is None


def test_fusion_does_not_return_stale_hsv_cache_by_default():
    fusion = BallFusionOperator(cache_ttl=0.5)
    hsv = BallDto(cx=59, cy=101, r=9.7, conf=1.0, source="hsv")

    assert fusion.merge(hsv_ball=hsv, yolo_ball=None, now_ts=1.0) == hsv
    assert fusion.merge(hsv_ball=None, yolo_ball=None, now_ts=1.1) is None
