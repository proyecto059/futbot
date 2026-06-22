import sys
sys.path.insert(0, ".")
import numpy as np

def test_detections_dataclass():
    """Verifica que los dataclasses de deteccion se crean correctamente."""
    from vision import Ball, Goal, WhiteLine, Detections

    ball = Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)
    assert ball.x == 0.5

    goal = Goal(color="blue", x=0.3, y=0.8)
    assert goal.color == "blue"

    line = WhiteLine(detected=True, position="center")
    assert line.detected

    dets = Detections(ball=ball, goal=goal, white_line=line)
    assert dets.ball is not None
    assert dets.goal is not None
    assert dets.white_line is not None

def test_detections_empty():
    from vision import Detections
    dets = Detections()
    assert dets.ball is None
    assert dets.goal is None
    assert dets.white_line is None

def test_vision_hsv_ball_detection():
    """Verifica que la deteccion HSV encuentra una bola naranja sintetica."""
    from vision import Vision
    from config import Config
    cfg = Config()
    vis = Vision(cfg)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2 = __import__("cv2")
    orange_bgr = (0, 140, 255)  # BGR = naranja
    cv2.circle(frame, (160, 120), 30, orange_bgr, -1)
    dets = vis.detect(frame)
    assert dets.ball is not None
    assert 0.3 < dets.ball.x < 0.7
    assert 0.3 < dets.ball.y < 0.7

def test_vision_no_ball():
    """Frame vacio no debe detectar nada."""
    from vision import Vision
    from config import Config
    cfg = Config()
    vis = Vision(cfg)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    dets = vis.detect(frame)
    assert dets.ball is None
