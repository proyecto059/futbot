import importlib
import sys
import types
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


_ORIGINAL_MODULES = {}


def _install_stub_modules():
    for name in ("smbus2", "serial"):
        _ORIGINAL_MODULES[name] = sys.modules.get(name)

    smbus2 = types.ModuleType("smbus2")

    class _DummySMBus:
        def __init__(self, *args, **kwargs):
            pass

    class _DummyI2CMsg:
        @staticmethod
        def write(*args, **kwargs):
            return None

        @staticmethod
        def read(*args, **kwargs):
            return None

    smbus2.SMBus = _DummySMBus
    smbus2.i2c_msg = _DummyI2CMsg
    sys.modules["smbus2"] = smbus2

    serial = types.ModuleType("serial")

    class _DummySerial:
        def __init__(self, *args, **kwargs):
            pass

    serial.Serial = _DummySerial
    sys.modules["serial"] = serial


def _restore_modules():
    for name, original in _ORIGINAL_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def _load_hardware_module():
    _install_stub_modules()
    try:
        module = importlib.import_module("hardware")
        return importlib.reload(module)
    finally:
        _restore_modules()


def _make_frame(ball_hsv, bg_hsv=(0, 0, 40), radius=48, center=(320, 240)):
    hsv = np.zeros((480, 640, 3), dtype=np.uint8)
    hsv[:, :] = np.array(bg_hsv, dtype=np.uint8)
    cv2.circle(hsv, center, radius, tuple(int(v) for v in ball_hsv), -1)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


class AdaptiveBallDetectionTests(unittest.TestCase):
    def test_detects_orange_ball_in_dark_scene(self):
        hardware = _load_hardware_module()
        frame = _make_frame(ball_hsv=(12, 160, 95), bg_hsv=(0, 0, 22))

        ball = hardware.detect_ball(frame)

        self.assertIsNotNone(ball)
        cx, cy, radius = ball
        self.assertLess(abs(cx - 320), 20)
        self.assertLess(abs(cy - 240), 20)
        self.assertGreater(radius, 20)

    def test_detects_orange_ball_with_low_saturation_glare(self):
        hardware = _load_hardware_module()
        frame = _make_frame(ball_hsv=(14, 105, 250), bg_hsv=(0, 20, 225))

        ball = hardware.detect_ball(frame)

        self.assertIsNotNone(ball)

    def test_recovers_on_shifted_orange_hue(self):
        hardware = _load_hardware_module()
        warmup = _make_frame(ball_hsv=(12, 220, 220), bg_hsv=(0, 10, 60))
        shifted = _make_frame(ball_hsv=(26, 220, 220), bg_hsv=(0, 10, 60))

        first = hardware.detect_ball(warmup)
        second = hardware.detect_ball(shifted)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    def test_reports_strict_mode_after_reacquire_when_primary_recovers(self):
        hardware = _load_hardware_module()
        shifted = _make_frame(ball_hsv=(26, 220, 220), bg_hsv=(0, 10, 60))
        baseline = _make_frame(ball_hsv=(12, 220, 220), bg_hsv=(0, 10, 60))

        first = hardware.detect_ball(shifted)
        self.assertIsNotNone(first)

        second = hardware.detect_ball(baseline)
        self.assertIsNotNone(second)

        dbg = hardware.get_ball_detection_debug()
        self.assertEqual(dbg.get("mode"), "strict")

    def test_rejects_non_orange_ball(self):
        hardware = _load_hardware_module()
        frame = _make_frame(ball_hsv=(95, 230, 220), bg_hsv=(0, 0, 40))

        ball = hardware.detect_ball(frame)

        self.assertIsNone(ball)


if __name__ == "__main__":
    unittest.main()
