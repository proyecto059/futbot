import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def import_focus_camera():
    try:
        return importlib.import_module("focus_camera")
    except ModuleNotFoundError as exc:
        pytest.fail(f"scripts/focus_camera.py must exist: {exc}")


def test_select_best_sample_prefers_highest_sharpness():
    focus_camera = import_focus_camera()
    first = focus_camera.FocusSample(index=1, frame=np.zeros((2, 2, 3)), sharpness=10.0)
    second = focus_camera.FocusSample(index=2, frame=np.zeros((2, 2, 3)), sharpness=25.0)

    assert focus_camera.select_best_sample([first, second]) is second


def test_collect_focus_samples_reads_latest_frames_and_computes_sharpness(monkeypatch):
    focus_camera = import_focus_camera()
    frames = [np.zeros((6, 6, 3), dtype=np.uint8), np.zeros((6, 6, 3), dtype=np.uint8)]
    frames[1][:, 3:] = 255
    events = []

    class FrameDto:
        def __init__(self, image):
            self.image = image

    class FakeCapture:
        def __init__(self, **_kwargs):
            self._frames = list(frames)

        def start(self):
            events.append("start")

        def read_latest(self):
            events.append("read_latest")
            return FrameDto(self._frames.pop(0)) if self._frames else None

        def close(self):
            events.append("close")

    monkeypatch.setattr(focus_camera.time, "sleep", lambda _seconds: None)

    samples = focus_camera.collect_focus_samples(
        sample_count=2,
        interval_sec=0.0,
        timeout_sec=0.1,
        capture_factory=FakeCapture,
    )

    assert [sample.index for sample in samples] == [1, 2]
    assert samples[0].sharpness < samples[1].sharpness
    assert events[0] == "start"
    assert events[-1] == "close"


def test_collect_focus_samples_passes_requested_capture_settings(monkeypatch):
    focus_camera = import_focus_camera()
    init_args = []

    class FrameDto:
        image = np.zeros((4, 6, 3), dtype=np.uint8)

    class FakeCapture:
        def __init__(self, **kwargs):
            init_args.append(kwargs)

        def start(self):
            pass

        def read_latest(self):
            return FrameDto()

        def close(self):
            pass

    monkeypatch.setattr(focus_camera.time, "sleep", lambda _seconds: None)

    focus_camera.collect_focus_samples(
        sample_count=1,
        interval_sec=0.0,
        timeout_sec=0.1,
        width=320,
        height=240,
        sharpness=2.0,
        noise_reduction_mode="fast",
        exposure_us=8000,
        analogue_gain=1.5,
        capture_factory=FakeCapture,
    )

    assert init_args == [
        {
            "width": 320,
            "height": 240,
            "sharpness": 2.0,
            "noise_reduction_mode": "fast",
            "exposure_us": 8000,
            "analogue_gain": 1.5,
        }
    ]


def test_arg_parser_accepts_focus_resolution():
    focus_camera = import_focus_camera()

    args = focus_camera.build_arg_parser().parse_args(["--width", "320", "--height", "240"])

    assert args.width == 320
    assert args.height == 240


def test_arg_parser_accepts_camera_quality_controls():
    focus_camera = import_focus_camera()

    args = focus_camera.build_arg_parser().parse_args(
        [
            "--sharpness",
            "2.0",
            "--denoise",
            "fast",
            "--exposure-us",
            "8000",
            "--gain",
            "1.5",
        ]
    )

    assert args.sharpness == 2.0
    assert args.denoise == "fast"
    assert args.exposure_us == 8000
    assert args.gain == 1.5


def test_write_best_sample_saves_image(monkeypatch, tmp_path):
    focus_camera = import_focus_camera()
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    sample = focus_camera.FocusSample(index=3, frame=frame, sharpness=42.0)
    saved = []

    def fake_imwrite(path, image):
        saved.append((Path(path), image))
        return True

    monkeypatch.setattr(focus_camera.cv2, "imwrite", fake_imwrite)

    focus_camera.write_best_sample(sample, tmp_path / "focus_best.png")

    assert saved == [(tmp_path / "focus_best.png", frame)]


def test_center_crop_uses_middle_of_frame():
    focus_camera = import_focus_camera()
    frame = np.arange(8 * 10 * 3, dtype=np.uint8).reshape((8, 10, 3))

    crop = focus_camera.center_crop(frame, width=4, height=2)

    assert np.array_equal(crop, frame[3:5, 3:7])


def test_build_focus_diagnostic_images_returns_full_center_and_corners():
    focus_camera = import_focus_camera()
    frame = np.zeros((1200, 1600, 3), dtype=np.uint8)

    images = focus_camera.build_focus_diagnostic_images(frame)

    assert set(images) == {
        "full",
        "center_640",
        "center_1024",
        "corner_tl",
        "corner_tr",
        "corner_bl",
        "corner_br",
    }
    assert images["full"].shape == (1200, 1600, 3)
    assert images["center_640"].shape == (640, 640, 3)
    assert images["center_1024"].shape == (1024, 1024, 3)
    assert images["corner_tl"].shape == (640, 640, 3)


def test_write_focus_diagnostics_writes_images_and_metrics(monkeypatch, tmp_path):
    focus_camera = import_focus_camera()
    frame = np.zeros((1200, 1600, 3), dtype=np.uint8)
    frame[300:900, 500:1100] = 255
    sample = focus_camera.FocusSample(index=2, frame=frame, sharpness=12.5)
    saved = []

    def fake_imwrite(path, image):
        saved.append((Path(path).name, image.shape))
        return True

    monkeypatch.setattr(focus_camera.cv2, "imwrite", fake_imwrite)

    focus_camera.write_focus_diagnostics(sample, tmp_path)

    saved_names = {name for name, _shape in saved}
    assert saved_names == {
        "full.png",
        "center_640.png",
        "center_1024.png",
        "corner_tl.png",
        "corner_tr.png",
        "corner_bl.png",
        "corner_br.png",
    }
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["best_sample"] == 2
    assert metrics["full"]["width"] == 1600
    assert metrics["full"]["height"] == 1200
    assert "sharpness" in metrics["center_640"]


def test_arg_parser_accepts_focus_diagnostics_output_dir():
    focus_camera = import_focus_camera()

    args = focus_camera.build_arg_parser().parse_args(
        ["--diag-grid", "--output-dir", "output/focus_diag"]
    )

    assert args.diag_grid is True
    assert args.output_dir == Path("output/focus_diag")
