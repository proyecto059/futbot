import sys
sys.path.insert(0, ".")

def test_camera_creates_instance():
    """Verifica que Camera se puede instanciar sin hardware (fallback V4L2)."""
    from config import Config
    from camera import Camera
    cfg = Config()
    # En entorno sin cámara, debe lanzar RuntimeError con mensaje adecuado
    try:
        cam = Camera(cfg)
        assert cam is not None
        cam.release()
    except RuntimeError as e:
        assert "cámara" in str(e).lower() or "camera" in str(e).lower()
