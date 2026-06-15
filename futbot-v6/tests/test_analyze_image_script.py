import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def import_analyzer():
    try:
        return importlib.import_module("analyze_image")
    except ModuleNotFoundError as exc:
        pytest.fail(f"scripts/analyze_image.py must exist: {exc}")


def test_preprocess_image_returns_rgb_normalized_blob():
    analyzer = import_analyzer()
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    frame[:] = (0, 0, 255)  # BGR red.

    blob = analyzer.preprocess_image(frame)

    assert blob.shape == (1, 3, analyzer.MODEL_IMAGE_SIZE, analyzer.MODEL_IMAGE_SIZE)
    assert blob.dtype == np.float32
    assert np.allclose(blob[:, 0], 1.0)
    assert np.allclose(blob[:, 1:], 0.0)


def test_parse_detections_filters_scales_and_sorts_yolo_rows():
    analyzer = import_analyzer()
    output = np.array(
        [
            [
                [10, 20, 50, 60, 0.80, 0],
                [100, 110, 140, 150, 0.35, 1],
                [200, 210, 250, 260, 0.75, 1],
            ]
        ],
        dtype=np.float32,
    )

    detections = analyzer.parse_detections(
        output, image_shape=(480, 640, 3), conf_threshold=0.40
    )
    scale_x = 640 / analyzer.MODEL_IMAGE_SIZE
    scale_y = 480 / analyzer.MODEL_IMAGE_SIZE

    assert [det["class_name"] for det in detections] == ["ball", "robot"]
    assert detections[0]["bbox"] == (
        round(10 * scale_x),
        round(20 * scale_y),
        round(50 * scale_x),
        round(60 * scale_y),
    )
    assert detections[0]["conf"] == pytest.approx(0.80)
    assert detections[1]["bbox"] == (
        round(200 * scale_x),
        round(210 * scale_y),
        round(250 * scale_x),
        round(260 * scale_y),
    )
    assert detections[1]["conf"] == pytest.approx(0.75)


def test_pt_model_path_uses_custom_best_model():
    analyzer = import_analyzer()

    assert analyzer.PT_MODEL_PATH.name == "best.pt"


def test_export_paths_match_updated_model_layout():
    analyzer = import_analyzer()

    assert analyzer.ONNX_MODEL_PATH.name == "best.onnx"
    assert analyzer.NCNN_MODEL_DIR.name == "best_ncnn_model"


def test_debug_alias_enables_low_confidence_mode():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--debug"])

    assert args.debug_low_conf is True


def test_vision_flag_uses_src_vision_backend():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--vision"])

    assert args.vision is True


def test_rpi_flag_exists():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--rpi"])

    assert args.rpi is True


def test_capture_rpi_frame_uses_src_vision_capture():
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    events = []

    class FrameDto:
        image = frame

    class FakeCapture:
        def start(self):
            events.append("start")

        def read_latest(self):
            events.append("read_latest")
            return FrameDto()

        def close(self):
            events.append("close")

    captured = analyzer.capture_rpi_frame(
        capture_factory=FakeCapture,
        timeout_sec=0.1,
        poll_sec=0.0,
    )

    assert captured is frame
    assert events == ["start", "read_latest", "close"]


def test_run_ncnn_runtime_only_reports_clear_error():
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)

    def failing_backend_factory():
        raise RuntimeError("ncnn unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        analyzer.run_ncnn_runtime_only(
            frame,
            backend_factory=failing_backend_factory,
        )

    assert str(exc_info.value) == "NCNN runtime failed: ncnn unavailable"


def test_run_ncnn_runtime_only_uses_ncnn_without_onnx_fallback():
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    output = np.array([[10, 20, 50, 60, 0.8, 1]], dtype=np.float32)
    calls = []

    class FakeNcnnBackend:
        name = "ncnn"
        image_size = 320

        def run(self, _frame):
            calls.append("ncnn")
            return output

    result = analyzer.run_ncnn_runtime_only(
        frame,
        backend_factory=FakeNcnnBackend,
    )

    assert result.backend == "ncnn"
    assert result.output is output
    assert result.model_image_size == 320
    assert calls == ["ncnn"]


def test_parse_detections_uses_backend_class_names():
    analyzer = import_analyzer()
    output = np.array([[[10, 20, 50, 60, 0.80, 60]]], dtype=np.float32)

    detections = analyzer.parse_detections(
        output,
        image_shape=(480, 640, 3),
        conf_threshold=0.40,
        class_names={60: "dining table"},
    )

    assert detections[0]["class_name"] == "dining table"


def test_parse_detections_can_keep_image_space_boxes_unscaled():
    analyzer = import_analyzer()
    output = np.array([[[10, 20, 50, 60, 0.80, 1]]], dtype=np.float32)

    detections = analyzer.parse_detections(
        output,
        image_shape=(480, 640, 3),
        conf_threshold=0.40,
        boxes_in_image_space=True,
    )

    assert detections[0]["bbox"] == (10, 20, 50, 60)


def test_parse_detections_default_threshold_rejects_low_confidence_candidates():
    analyzer = import_analyzer()
    output = np.array([[[10, 20, 50, 60, 0.002, 1]]], dtype=np.float32)

    detections = analyzer.parse_detections(output, image_shape=(480, 640, 3))

    assert detections == []


def test_parse_detections_marks_low_confidence_debug_candidates():
    analyzer = import_analyzer()
    output = np.array([[[10, 20, 50, 60, 0.002, 1]]], dtype=np.float32)

    detections = analyzer.parse_detections(
        output,
        image_shape=(480, 640, 3),
        conf_threshold=analyzer.LOW_CONF_THRESHOLD,
        valid_conf_threshold=analyzer.DEFAULT_CONF_THRESHOLD,
    )

    assert len(detections) == 1
    assert detections[0]["class_name"] == "robot"
    assert detections[0]["kind"] == "candidate"


def test_run_with_fallback_uses_pt_first():
    analyzer = import_analyzer()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    pt_output = analyzer.RunnerOutput(
        np.zeros((1, 0, 6), dtype=np.float32),
        class_names={1: "robot"},
        boxes_in_image_space=True,
    )
    calls = []

    def pt_runner(_frame):
        calls.append("pt")
        return pt_output

    def ncnn_runner(_frame):
        calls.append("ncnn")
        raise AssertionError("NCNN should not run when PT succeeds")

    def onnx_runner(_frame):
        calls.append("onnx")
        raise AssertionError("ONNX should not run when PT succeeds")

    result = analyzer.run_with_fallback(
        frame,
        pt_runner=pt_runner,
        onnx_runner=onnx_runner,
        ncnn_runner=ncnn_runner,
    )

    assert result.backend == "pt"
    assert result.output is pt_output.output
    assert result.class_names == {1: "robot"}
    assert result.boxes_in_image_space is True
    assert result.fallback_reason is None
    assert calls == ["pt"]


def test_run_with_fallback_uses_onnx_when_pt_fails():
    analyzer = import_analyzer()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    onnx_output = np.zeros((1, 0, 6), dtype=np.float32)
    calls = []

    def failing_pt(_frame):
        calls.append("pt")
        raise RuntimeError("pt unavailable")

    def onnx_runner(_frame):
        calls.append("onnx")
        return onnx_output

    def ncnn_runner(_frame):
        calls.append("ncnn")
        raise AssertionError("NCNN should not run when ONNX succeeds")

    result = analyzer.run_with_fallback(
        frame,
        pt_runner=failing_pt,
        onnx_runner=onnx_runner,
        ncnn_runner=ncnn_runner,
    )

    assert result.backend == "onnx"
    assert result.output is onnx_output
    assert result.fallback_reason == "pt unavailable"
    assert calls == ["pt", "onnx"]


def test_run_with_fallback_uses_ncnn_when_pt_and_onnx_fail():
    analyzer = import_analyzer()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    ncnn_output = np.zeros((1, 0, 6), dtype=np.float32)
    calls = []

    def failing_pt(_frame):
        calls.append("pt")
        raise RuntimeError("pt unavailable")

    def failing_onnx(_frame):
        calls.append("onnx")
        raise RuntimeError("onnx unavailable")

    def ncnn_runner(_frame):
        calls.append("ncnn")
        return ncnn_output

    result = analyzer.run_with_fallback(
        frame,
        pt_runner=failing_pt,
        onnx_runner=failing_onnx,
        ncnn_runner=ncnn_runner,
    )

    assert result.backend == "ncnn"
    assert result.output is ncnn_output
    assert result.fallback_reason == "pt unavailable; onnx unavailable"
    assert calls == ["pt", "onnx", "ncnn"]


def test_run_with_fallback_reports_all_failures_when_no_backend_runs():
    analyzer = import_analyzer()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)

    def failing_pt(_frame):
        raise RuntimeError("pt unavailable")

    def failing_onnx(_frame):
        raise RuntimeError("onnx unavailable")

    def failing_ncnn(_frame):
        raise RuntimeError("ncnn unavailable")

    with pytest.raises(RuntimeError) as exc_info:
        analyzer.run_with_fallback(
            frame,
            pt_runner=failing_pt,
            onnx_runner=failing_onnx,
            ncnn_runner=failing_ncnn,
        )

    assert str(exc_info.value) == (
        "PT: pt unavailable | ONNX: onnx unavailable | NCNN: ncnn unavailable"
    )


class FakeTensor:
    def __init__(self, values):
        self._values = np.array(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self._values


class FakeBoxes:
    xyxy = FakeTensor([[10, 20, 50, 60], [100, 110, 140, 150]])
    conf = FakeTensor([0.9, 0.7])
    cls = FakeTensor([0, 1])


class FakeResult:
    boxes = FakeBoxes()


def test_ultralytics_result_to_rows_converts_boxes():
    analyzer = import_analyzer()

    rows = analyzer.ultralytics_result_to_rows(FakeResult())

    assert rows.shape == (2, 6)
    assert rows.dtype == np.float32
    assert rows.tolist() == [
        [10.0, 20.0, 50.0, 60.0, pytest.approx(0.9), 0.0],
        [100.0, 110.0, 140.0, 150.0, pytest.approx(0.7), 1.0],
    ]


def test_draw_detections_returns_annotated_copy():
    analyzer = import_analyzer()
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    detections = [
        {"class_name": "ball", "conf": 0.9, "bbox": (10, 10, 40, 40)},
    ]

    annotated = analyzer.draw_detections(frame, detections)

    assert np.count_nonzero(frame) == 0
    assert np.count_nonzero(annotated) > 0


def test_draw_detections_labels_low_confidence_candidates(monkeypatch):
    analyzer = import_analyzer()
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    detections = [
        {
            "class_name": "robot",
            "conf": 0.00234,
            "bbox": (10, 10, 40, 40),
            "kind": "candidate",
        },
    ]
    labels = []
    original_put_text = analyzer.cv2.putText

    def capture_put_text(image, text, *args, **kwargs):
        labels.append(text)
        return original_put_text(image, text, *args, **kwargs)

    monkeypatch.setattr(analyzer.cv2, "putText", capture_put_text)

    analyzer.draw_detections(frame, detections)

    assert labels == ["LOW robot 0.002"]
