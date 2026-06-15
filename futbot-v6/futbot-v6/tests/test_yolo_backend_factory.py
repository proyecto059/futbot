import builtins
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def test_importing_ncnn_backend_does_not_import_onnxruntime(monkeypatch):
    for module_name in [
        "onnxruntime",
        "vision.utils",
        "vision.utils.onnx_session_factory",
        "vision.utils.yolo_backend_factory",
    ]:
        sys.modules.pop(module_name, None)
    if "vision" in sys.modules and hasattr(sys.modules["vision"], "utils"):
        delattr(sys.modules["vision"], "utils")

    attempted_imports = []
    original_import = builtins.__import__

    def guard_import(name, *args, **kwargs):
        if name == "onnxruntime" or name.startswith("onnxruntime."):
            attempted_imports.append(name)
            raise AssertionError("NCNN backend import must not import onnxruntime")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard_import)

    from vision.utils.yolo_backend_factory import NcnnYoloBackend

    assert NcnnYoloBackend.name == "ncnn"
    assert attempted_imports == []


def test_yolo_backend_factory_uses_ncnn_first():
    from vision.utils.yolo_backend_factory import YoloBackendFactory

    calls = []

    def make_ncnn():
        calls.append("ncnn")
        return "ncnn-backend"

    def make_onnx():
        calls.append("onnx")
        return "onnx-backend"

    backend = YoloBackendFactory.create(
        ncnn_factory=make_ncnn,
        onnx_factory=make_onnx,
    )

    assert backend == "ncnn-backend"
    assert calls == ["ncnn"]


def test_yolo_backend_factory_falls_back_to_onnx():
    from vision.utils.yolo_backend_factory import YoloBackendFactory

    calls = []

    def make_ncnn():
        calls.append("ncnn")
        raise RuntimeError("ncnn unavailable")

    def make_onnx():
        calls.append("onnx")
        return "onnx-backend"

    backend = YoloBackendFactory.create(
        ncnn_factory=make_ncnn,
        onnx_factory=make_onnx,
    )

    assert backend == "onnx-backend"
    assert calls == ["ncnn", "onnx"]


def test_yolo_backend_factory_reports_both_failures():
    from vision.utils.yolo_backend_factory import YoloBackendFactory

    def make_ncnn():
        raise RuntimeError("ncnn unavailable")

    def make_onnx():
        raise RuntimeError("onnx unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        YoloBackendFactory.create(ncnn_factory=make_ncnn, onnx_factory=make_onnx)

    assert str(exc_info.value) == "NCNN: ncnn unavailable | ONNX: onnx unavailable"


def test_yolo_image_size_matches_current_ncnn_export():
    from vision.utils.vision_constants import YOLO_IMGSZ, resolve_yolo_ncnn_model_dir

    param_text = (resolve_yolo_ncnn_model_dir() / "model.ncnn.param").read_text()

    assert "0=8400 1=2" in param_text
    assert YOLO_IMGSZ == 640


def test_ncnn_backend_run_uses_backend_image_size(monkeypatch):
    import vision.utils.yolo_backend_factory as factory

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    output = np.array([[10, 20, 50, 60, 0.8, 1]], dtype=np.float32)
    calls = []

    def fake_preprocess(_frame, image_size):
        calls.append(image_size)
        return np.zeros((3, image_size, image_size), dtype=np.float32)

    class FakeMat:
        def __init__(self, _blob):
            pass

        def clone(self):
            return self

    class FakeNcnn:
        Mat = FakeMat

    class FakeExtractor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def input(self, name, _mat):
            assert name == "in0"
            return 0

        def extract(self, name):
            assert name == "out0"
            return 0, output

    class FakeNet:
        def create_extractor(self):
            return FakeExtractor()

    backend = object.__new__(factory.NcnnYoloBackend)
    backend.image_size = 640
    backend._ncnn = FakeNcnn()
    backend._net = FakeNet()

    monkeypatch.setattr(factory, "preprocess_yolo_frame", fake_preprocess)

    rows = backend.run(frame)

    assert calls == [640]
    assert rows.tolist() == output.tolist()


def test_onnx_backend_run_returns_rows_from_session_output():
    from vision.utils.yolo_backend_factory import OnnxYoloBackend

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    output = np.array([[[10, 20, 50, 60, 0.8, 1]]], dtype=np.float32)

    class Input:
        name = "images"
        shape = [1, 3, 320, 320]

    class Session:
        def get_inputs(self):
            return [Input()]

        def run(self, _outputs, _feed):
            return [output]

    backend = OnnxYoloBackend(Session())

    rows = backend.run(frame)

    assert rows.shape == (1, 6)
    assert rows[0].tolist() == [10, 20, 50, 60, pytest.approx(0.8), 1]
