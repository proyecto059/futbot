import importlib
import json
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
                [200, 210, 250, 260, 0.75, 4],
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

    assert analyzer.ONNX_MODEL_PATH.as_posix().endswith(
        "models/yoloe26n_v2/onnx/yoloe26n_v2.onnx"
    )
    assert analyzer.NCNN_MODEL_DIR.as_posix().endswith(
        "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
    )
    assert analyzer.MODEL_IMAGE_SIZE == 320


def test_debug_alias_enables_low_confidence_mode():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--debug"])

    assert args.debug_low_conf is True


def test_debug_uses_rpi_camera_on_raspberry_without_image():
    analyzer = import_analyzer()
    args = analyzer.build_arg_parser().parse_args(["--debug"])

    assert analyzer.should_capture_rpi_for_debug(
        args,
        ["--debug"],
        is_raspberry_runtime=lambda: True,
    ) is True


def test_debug_keeps_static_image_when_image_is_explicit():
    analyzer = import_analyzer()
    args = analyzer.build_arg_parser().parse_args(["--debug", "--image", "frame.png"])

    assert analyzer.should_capture_rpi_for_debug(
        args,
        ["--debug", "--image", "frame.png"],
        is_raspberry_runtime=lambda: True,
    ) is False


def test_compute_frame_sharpness_reports_edges():
    analyzer = import_analyzer()
    blurry = np.zeros((20, 20, 3), dtype=np.uint8)
    sharp = blurry.copy()
    sharp[:, 10:] = 255

    assert analyzer.compute_frame_sharpness(blurry) == pytest.approx(0.0)
    assert analyzer.compute_frame_sharpness(sharp) > 0.0


def test_write_debug_camera_frame_saves_raw_frame(monkeypatch, tmp_path):
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    saved = []

    def fake_imwrite(path, image):
        saved.append((Path(path), image))
        return True

    monkeypatch.setattr(analyzer.cv2, "imwrite", fake_imwrite)

    raw_path, sharpness = analyzer.write_debug_camera_frame(
        frame,
        tmp_path / "image_annotated.png",
    )

    assert raw_path == tmp_path / "raw_camera_frame.png"
    assert sharpness == pytest.approx(0.0)
    assert saved == [(raw_path, frame)]


def test_vision_flag_uses_src_vision_backend():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--vision"])

    assert args.vision is True


def test_rpi_flag_exists():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--rpi"])

    assert args.rpi is True


def test_video_flag_defaults_to_ten_seconds():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--video"])

    assert args.video == pytest.approx(10.0)


def test_video_flag_accepts_duration_seconds():
    analyzer = import_analyzer()

    args = analyzer.build_arg_parser().parse_args(["--video", "3.5"])

    assert args.video == pytest.approx(3.5)


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


def test_write_video_frame_outputs_saves_raw_and_annotated(monkeypatch, tmp_path):
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    detections = [
        {"class_name": "robot", "conf": 0.8, "bbox": (1, 1, 4, 3)},
        {"class_name": "robot", "conf": 0.002, "bbox": (0, 0, 2, 2), "kind": "candidate"},
    ]
    saved = []

    def fake_imwrite(path, image):
        saved.append((Path(path).name, image.shape))
        return True

    monkeypatch.setattr(analyzer.cv2, "imwrite", fake_imwrite)

    record = analyzer.write_video_frame_outputs(
        tmp_path,
        frame_index=1,
        frame=frame,
        detections=detections,
        timestamp_sec=1.25,
        sharpness=12.5,
    )

    assert saved == [
        ("frame_000001_raw.png", frame.shape),
        ("frame_000001_annotated.png", frame.shape),
    ]
    assert record["frame"] == 1
    assert record["raw"] == "frame_000001_raw.png"
    assert record["annotated"] == "frame_000001_annotated.png"
    assert record["detections"] == 1
    assert record["low_conf_candidates"] == 1


def test_draw_fps_overlay_writes_fps_label(monkeypatch):
    analyzer = import_analyzer()
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    labels = []
    original_put_text = analyzer.cv2.putText

    def capture_put_text(image, text, *args, **kwargs):
        labels.append(text)
        return original_put_text(image, text, *args, **kwargs)

    monkeypatch.setattr(analyzer.cv2, "putText", capture_put_text)

    annotated = analyzer.draw_fps_overlay(frame, 5.75)

    assert labels[-1] == "FPS 5.8"
    assert np.count_nonzero(annotated) > 0


def test_write_video_frame_outputs_records_fps_and_overlays(monkeypatch, tmp_path):
    analyzer = import_analyzer()
    frame = np.zeros((4, 6, 3), dtype=np.uint8)
    overlay_calls = []

    monkeypatch.setattr(analyzer.cv2, "imwrite", lambda _path, _image: True)

    def fake_overlay(image, fps):
        overlay_calls.append(fps)
        return image

    monkeypatch.setattr(analyzer, "draw_fps_overlay", fake_overlay)

    record = analyzer.write_video_frame_outputs(
        tmp_path,
        frame_index=1,
        frame=frame,
        detections=[],
        timestamp_sec=0.5,
        sharpness=12.5,
        fps=7.25,
    )

    assert overlay_calls == [7.25]
    assert record["fps"] == pytest.approx(7.25)


def test_run_video_mode_reuses_capture_and_backend(monkeypatch, tmp_path):
    analyzer = import_analyzer()
    frames = [
        np.zeros((4, 6, 3), dtype=np.uint8),
        np.ones((4, 6, 3), dtype=np.uint8),
    ]
    events = []

    class FrameDto:
        def __init__(self, image, ts):
            self.image = image
            self.ts = ts

    class FakeCapture:
        instances = 0

        def __init__(self):
            FakeCapture.instances += 1
            self._frames = [FrameDto(frames[0], 1.0), FrameDto(frames[1], 2.0)]

        def start(self):
            events.append("start")

        def read_latest(self):
            events.append("read_latest")
            return self._frames.pop(0) if self._frames else None

        def close(self):
            events.append("close")

    class FakeBackend:
        instances = 0
        image_size = analyzer.MODEL_IMAGE_SIZE

        def __init__(self):
            FakeBackend.instances += 1

        def run(self, _frame):
            return np.array([[1, 1, 3, 3, 0.9, 1]], dtype=np.float32)

    monkeypatch.setattr(analyzer.cv2, "imwrite", lambda _path, _image: True)

    summary_path = analyzer.run_video_mode(
        duration_sec=10.0,
        output_dir=tmp_path,
        conf_threshold=0.4,
        low_conf_threshold=analyzer.LOW_CONF_THRESHOLD,
        debug_low_conf=False,
        capture_factory=FakeCapture,
        backend_factory=FakeBackend,
        time_fn=lambda: 0.0,
        sleep_fn=lambda _seconds: None,
        max_frames=2,
    )

    summary = json.loads(summary_path.read_text())
    assert FakeCapture.instances == 1
    assert FakeBackend.instances == 1
    assert events[0] == "start"
    assert events[-1] == "close"
    assert summary["backend"] == "ncnn"
    assert summary["duration_sec"] == 10.0
    assert len(summary["frames"]) == 2
    assert summary["frames"][0]["detections"] == 1


def test_run_video_mode_summary_includes_fps_stats(monkeypatch, tmp_path):
    analyzer = import_analyzer()
    frames = [
        np.zeros((4, 6, 3), dtype=np.uint8),
        np.ones((4, 6, 3), dtype=np.uint8),
        np.full((4, 6, 3), 2, dtype=np.uint8),
    ]

    class FrameDto:
        def __init__(self, image, ts):
            self.image = image
            self.ts = ts

    class FakeCapture:
        def __init__(self):
            self._frames = [
                FrameDto(frames[0], 10.0),
                FrameDto(frames[1], 10.5),
                FrameDto(frames[2], 11.0),
            ]

        def start(self):
            pass

        def read_latest(self):
            return self._frames.pop(0) if self._frames else None

        def close(self):
            pass

    class FakeBackend:
        image_size = analyzer.MODEL_IMAGE_SIZE

        def run(self, _frame):
            return np.empty((0, 6), dtype=np.float32)

    monkeypatch.setattr(analyzer.cv2, "imwrite", lambda _path, _image: True)

    summary_path = analyzer.run_video_mode(
        duration_sec=10.0,
        output_dir=tmp_path,
        capture_factory=FakeCapture,
        backend_factory=FakeBackend,
        time_fn=lambda: 10.0,
        sleep_fn=lambda _seconds: None,
        max_frames=3,
    )

    summary = json.loads(summary_path.read_text())
    assert summary["fps_avg"] == pytest.approx(2.0)
    assert summary["fps_min"] == pytest.approx(2.0)
    assert summary["fps_max"] == pytest.approx(2.0)
    assert summary["frames"][0]["fps"] == pytest.approx(0.0)
    assert summary["frames"][1]["fps"] == pytest.approx(2.0)


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


def test_parse_detections_groups_yoloe_classes():
    analyzer = import_analyzer()
    output = np.array(
        [
            [
                [10, 20, 50, 60, 0.80, 2],
                [100, 120, 150, 170, 0.70, 7],
            ]
        ],
        dtype=np.float32,
    )

    detections = analyzer.parse_detections(
        output,
        image_shape=(320, 320, 3),
        conf_threshold=0.40,
    )

    assert [det["class_name"] for det in detections] == ["ball", "robot"]


def test_analyzer_decodes_yoloe_segment_output():
    analyzer = import_analyzer()
    output = np.zeros((48, 1), dtype=np.float32)
    output[:4, 0] = [100.0, 80.0, 40.0, 20.0]
    output[4 + 2, 0] = 0.90
    output[16:, 0] = 1.0

    rows = analyzer._as_detection_rows(output)

    assert rows.shape == (1, 6)
    assert rows[0].tolist() == [80.0, 70.0, 120.0, 90.0, pytest.approx(0.90), 2.0]


def test_analyzer_suppresses_overlapping_yoloe_robot_subclasses():
    analyzer = import_analyzer()
    output = np.zeros((48, 2), dtype=np.float32)
    output[:4, 0] = [100.0, 80.0, 40.0, 20.0]
    output[:4, 1] = [101.0, 81.0, 40.0, 20.0]
    output[4 + 4, 0] = 0.90
    output[4 + 7, 1] = 0.80

    rows = analyzer._as_detection_rows(output)

    assert rows.shape == (1, 6)
    assert rows[0].tolist() == [80.0, 70.0, 120.0, 90.0, pytest.approx(0.90), 4.0]


def test_detection_conf_summary_uses_low_conf_candidates():
    analyzer = import_analyzer()
    detections = [
        {"class_name": "robot", "conf": 0.027, "kind": "candidate"},
        {"class_name": "ball", "conf": 0.007, "kind": "candidate"},
        {"class_name": "robot", "conf": 0.018, "kind": "candidate"},
    ]

    summary = analyzer.detection_conf_summary(detections)

    assert summary == {"best_ball_conf": pytest.approx(0.007), "best_robot_conf": pytest.approx(0.027)}


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
    output = np.array([[[10, 20, 50, 60, 0.002, 4]]], dtype=np.float32)

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
