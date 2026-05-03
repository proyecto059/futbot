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


def _load_play_futbot_symbols():
    _install_stub_modules()
    try:
        pf = importlib.import_module("play_futbot")
        return (
            pf.should_kick,
            pf.KICK_PUSH,
            pf.KICK_ANGLED,
            pf.KICK_SPIN,
        )
    finally:
        _restore_modules()


(
    should_kick,
    KICK_PUSH,
    KICK_ANGLED,
    KICK_SPIN,
) = _load_play_futbot_symbols()

FW = 320
FH = 240
FCX = FW // 2
SPEED = 250.0


class ShouldKickTests(unittest.TestCase):
    def test_no_ball_no_kick(self):
        result = {
            "detected": False,
            "tracking_locked": False,
            "ema_cx": None,
            "ema_cy": None,
        }
        self.assertIsNone(should_kick(result, None, SPEED, FW))

    def test_ball_far_no_kick(self):
        result = {
            "detected": True,
            "tracking_locked": True,
            "ema_cx": FCX,
            "ema_cy": 120,
        }
        ball = (FCX, 120, 20)
        self.assertIsNone(should_kick(result, ball, SPEED, FW))

    def test_ball_centered_close_push_or_angled(self):
        result = {
            "detected": True,
            "tracking_locked": True,
            "ema_cx": FCX,
            "ema_cy": 120,
        }
        ball = (FCX, 120, 55)
        kick = should_kick(result, ball, SPEED, FW)
        self.assertIn(kick, [KICK_PUSH, KICK_ANGLED])

    def test_ball_left_edge_close_spin(self):
        result = {
            "detected": True,
            "tracking_locked": True,
            "ema_cx": 50,
            "ema_cy": 120,
        }
        ball = (50, 120, 55)
        kick = should_kick(result, ball, SPEED, FW)
        self.assertEqual(kick, KICK_SPIN)

    def test_not_tracking_locked_no_kick(self):
        result = {
            "detected": True,
            "tracking_locked": False,
            "ema_cx": FCX,
            "ema_cy": 120,
        }
        ball = (FCX, 120, 55)
        self.assertIsNone(should_kick(result, ball, SPEED, FW))

    def test_ema_cx_none_no_kick(self):
        result = {
            "detected": True,
            "tracking_locked": True,
            "ema_cx": None,
            "ema_cy": None,
        }
        ball = (FCX, 120, 55)
        self.assertIsNone(should_kick(result, ball, SPEED, FW))

    def test_ball_edge_medium_radius_spin(self):
        result = {
            "detected": True,
            "tracking_locked": True,
            "ema_cx": 50,
            "ema_cy": 120,
        }
        ball = (50, 120, 42)
        kick = should_kick(result, ball, SPEED, FW)
        self.assertEqual(kick, KICK_SPIN)


if __name__ == "__main__":
    unittest.main()