import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src" / "vision" / "utils"))


def import_worker():
    return importlib.import_module("_libcamera_worker")


def test_worker_import_does_not_require_libcamera_bindings():
    import_worker()


def test_worker_arg_parser_accepts_startup_controls():
    worker = import_worker()

    args = worker.build_arg_parser().parse_args(
        [
            "640",
            "480",
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

    assert args.width == 640
    assert args.height == 480
    assert args.sharpness == 2.0
    assert args.denoise == "fast"
    assert args.exposure_us == 8000
    assert args.gain == 1.5


def test_worker_builds_startup_controls_for_request_api():
    worker = import_worker()

    fake_lc = SimpleNamespace(
        controls=SimpleNamespace(
            Sharpness="Sharpness",
            AeEnable="AeEnable",
            ExposureTime="ExposureTime",
            AnalogueGain="AnalogueGain",
            draft=SimpleNamespace(
                NoiseReductionMode="NoiseReductionMode",
                NoiseReductionModeEnum=SimpleNamespace(Fast=101),
            ),
        )
    )
    args = SimpleNamespace(
        sharpness=2.0,
        denoise="fast",
        exposure_us=8000,
        gain=1.5,
    )

    controls = worker._build_startup_controls(fake_lc, args)

    assert controls == {
        "Sharpness": 2.0,
        "NoiseReductionMode": 101,
        "AeEnable": False,
        "ExposureTime": 8000,
        "AnalogueGain": 1.5,
    }


def test_worker_applies_controls_with_request_set_control():
    worker = import_worker()
    calls = []

    class FakeRequest:
        def set_control(self, control_id, value):
            calls.append((control_id, value))

    worker._apply_controls_to_request(
        FakeRequest(),
        {"Sharpness": 2.0, "ExposureTime": 8000},
    )

    assert calls == [("Sharpness", 2.0), ("ExposureTime", 8000)]
