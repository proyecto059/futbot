import importlib
import sys
import types
import unittest
from pathlib import Path

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


def _load_hardware_symbols():
    _install_stub_modules()
    try:
        hardware = importlib.import_module("hardware")
        return (
            hardware.map_ball_to_servos,
            hardware.map_x_to_pan,
            hardware.map_y_to_tilt,
            hardware.SERVO_PAN_INVERTED,
            hardware.SERVO_TILT_INVERTED,
            hardware.PAN_CENTER,
            hardware.TILT_CENTER,
        )
    finally:
        _restore_modules()


(
    map_ball_to_servos,
    map_x_to_pan,
    map_y_to_tilt,
    SERVO_PAN_INVERTED,
    SERVO_TILT_INVERTED,
    PAN_CENTER,
    TILT_CENTER,
) = _load_hardware_symbols()


class ServoMappingTests(unittest.TestCase):
    def test_center_trim_matches_mount_feedback(self):
        self.assertLess(PAN_CENTER, 90)
        self.assertGreater(TILT_CENTER, 90)

    def test_default_axis_inversion_is_disabled(self):
        self.assertFalse(SERVO_PAN_INVERTED)
        self.assertFalse(SERVO_TILT_INVERTED)
        self.assertEqual(map_x_to_pan(0, 640), 0)
        self.assertEqual(map_x_to_pan(640, 640), 180)
        self.assertEqual(map_y_to_tilt(0, 480), 180)
        self.assertEqual(map_y_to_tilt(480, 480), 0)

    def test_pan_non_inverted_edges(self):
        cases = [(0, 0), (640, 180)]
        for cx, expected in cases:
            with self.subTest(cx=cx, expected=expected):
                self.assertEqual(map_x_to_pan(cx, 640, pan_inverted=False), expected)

    def test_pan_inverted_edges(self):
        cases = [(0, 180), (640, 0)]
        for cx, expected in cases:
            with self.subTest(cx=cx, expected=expected):
                self.assertEqual(map_x_to_pan(cx, 640, pan_inverted=True), expected)

    def test_tilt_non_inverted_edges(self):
        cases = [(0, 180), (480, 0)]
        for cy, expected in cases:
            with self.subTest(cy=cy, expected=expected):
                self.assertEqual(map_y_to_tilt(cy, 480, tilt_inverted=False), expected)

    def test_tilt_inverted_edges(self):
        cases = [(0, 0), (480, 180)]
        for cy, expected in cases:
            with self.subTest(cy=cy, expected=expected):
                self.assertEqual(map_y_to_tilt(cy, 480, tilt_inverted=True), expected)

    def test_map_ball_to_servos_clamps_out_of_bounds(self):
        pan, tilt = map_ball_to_servos(-100, 9999, 640, 480, True, False)
        self.assertEqual(pan, 180)
        self.assertEqual(tilt, 0)


if __name__ == "__main__":
    unittest.main()
