import sys
sys.path.insert(0, ".")

def test_full_loop_with_stubs():
    """Ejecuta el bucle completo con stubs y verifica que no crashea."""
    import os
    os.environ["FUTBOT_MODE"] = "stub"

    from config import Config
    from stubs.camera_stub import CameraStub
    from stubs.motors_stub import MotorsStub
    from vision import Vision
    from pipeline import Pipeline

    cfg = Config()
    cam = CameraStub(cfg)
    vis = Vision(cfg)
    mot = MotorsStub(cfg)
    pip = Pipeline(cfg)

    for _ in range(10):
        frame = cam.grab()
        if frame is None:
            continue
        dets = vis.detect(frame)
        cmd = pip.tick(dets)
        mot.send(cmd)

    history = mot.get_history()
    assert len(history) > 0, "Debe haber al menos un comando enviado"
    for cmd in history:
        assert -300 <= cmd.left_speed <= 300
        assert -300 <= cmd.right_speed <= 300
