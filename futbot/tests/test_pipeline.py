import sys
sys.path.insert(0, ".")

def test_pipeline_starts_in_search():
    from pipeline import Pipeline
    from config import Config
    cfg = Config()
    pip = Pipeline(cfg)
    assert pip.state == "SEARCH"

def test_search_to_chase_transition():
    """Al detectar pelota, debe transicionar a CHASE."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    dets = Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9))
    cmd = pip.tick(dets)
    assert pip.state == "CHASE"
    assert cmd.left_speed != 0 or cmd.right_speed != 0

def test_chase_to_recovery_transition():
    """Al perder la pelota por suficiente tiempo, debe ir a RECOVERY."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    import time
    cfg = Config()
    pip = Pipeline(cfg)
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    assert pip.state == "CHASE"
    pip.tick(Detections())           # primer tick sin pelota: fija _miss_start
    time.sleep(1.0)                   # exceder chase_miss_secs (0.8)
    for _ in range(50):
        cmd = pip.tick(Detections())
    assert pip.state in ("RECOVERY", "SEARCH")

def test_ball_centered_goes_straight():
    """Pelota en el centro debe producir avance recto."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    cmd = pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    assert cmd.left_speed > 0
    assert cmd.right_speed > 0
