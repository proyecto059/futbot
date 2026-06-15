import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vision.operators.frame_capture_operator import FrameCaptureOperator
from vision.utils.camera_backend_resolver import _LibcameraCap


def test_frame_capture_passes_camera_quality_controls(monkeypatch):
    calls = []

    class FakeCap:
        def release(self):
            pass

    def fake_resolve(**kwargs):
        calls.append(kwargs)
        return FakeCap(), kwargs["width"], 200

    monkeypatch.setattr(
        "vision.operators.frame_capture_operator.CameraBackendResolver.resolve",
        fake_resolve,
    )

    capture = FrameCaptureOperator(
        width=640,
        height=480,
        sharpness=2.0,
        noise_reduction_mode="fast",
        exposure_us=8000,
        analogue_gain=1.5,
    )
    capture.close()

    assert calls == [
        {
            "width": 640,
            "height": 480,
            "sharpness": 2.0,
            "noise_reduction_mode": "fast",
            "exposure_us": 8000,
            "analogue_gain": 1.5,
        }
    ]


def test_libcamera_cap_passes_startup_controls_to_worker(monkeypatch):
    commands = []

    class FakeStdin:
        def write(self, data):
            commands.append(data.decode())

        def flush(self):
            pass

    class FakeStderr:
        def readline(self):
            return b"READY 640 480 2560\n"

    class FakeProc:
        stdin = FakeStdin()
        stdout = None
        stderr = FakeStderr()
        returncode = None

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    popen_args = []

    def fake_popen(args, **_kwargs):
        popen_args.append(args)
        return FakeProc()

    monkeypatch.setattr("vision.utils.camera_backend_resolver.os.path.isfile", lambda _path: True)
    monkeypatch.setattr("vision.utils.camera_backend_resolver.subprocess.Popen", fake_popen)

    cap = _LibcameraCap(
        width=640,
        height=480,
        sharpness=2.0,
        noise_reduction_mode="fast",
        exposure_us=8000,
        analogue_gain=1.5,
    )
    cap.release()

    assert popen_args == [
        [
            "/usr/bin/python3",
            str(PROJECT_ROOT / "src" / "vision" / "utils" / "_libcamera_worker.py"),
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
    ]
    assert commands == ["QUIT\n"]
