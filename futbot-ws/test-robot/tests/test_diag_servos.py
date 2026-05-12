import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

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


def _load_diag_symbols():
    _install_stub_modules()
    try:
        test_servos = importlib.import_module("test_servos")
        return (
            test_servos.run_diag_servos,
            test_servos.PAN_CENTER,
            test_servos.TILT_CENTER,
        )
    finally:
        _restore_modules()


run_diag_servos, PAN_CENTER, TILT_CENTER = _load_diag_symbols()


class _FakeSBus:
    def __init__(self):
        self.calls = []

    def burst(self, *args):
        self.calls.append(args)


class DiagServosTests(unittest.TestCase):
    @staticmethod
    def _collect_axis_moves(calls):
        tilt_moves = [
            call for call in calls if call[0] == PAN_CENTER and call[1] != TILT_CENTER
        ]
        pan_moves = [
            call for call in calls if call[1] == TILT_CENTER and call[0] != PAN_CENTER
        ]
        return tilt_moves, pan_moves

    @staticmethod
    def _run_diag_servos_with_flags(pan_inverted, tilt_inverted):
        sbus = _FakeSBus()
        with (
            patch("test_servos.SERVO_PAN_INVERTED", pan_inverted),
            patch("test_servos.SERVO_TILT_INVERTED", tilt_inverted),
            patch("test_servos.time.sleep", return_value=None),
        ):
            run_diag_servos(sbus)
        return sbus.calls

    def test_diag_servos_emits_tilt_pan_and_recenters(self):
        calls = self._run_diag_servos_with_flags(False, False)
        tilt_moves, pan_moves = self._collect_axis_moves(calls)

        self.assertEqual(calls[0][0:2], (PAN_CENTER, TILT_CENTER))
        self.assertEqual(calls[0][2], 1000)
        self.assertGreaterEqual(len(tilt_moves), 2)
        self.assertEqual(len(pan_moves), 2)
        self.assertEqual(calls[-2][0:2], (PAN_CENTER, TILT_CENTER))
        self.assertEqual(calls[-1][0:2], (PAN_CENTER, TILT_CENTER))
        self.assertEqual(calls[-2][2], 1000)
        self.assertEqual(calls[-1][2], 1000)

    def test_diag_servos_respects_inversion_flags(self):
        normal_calls = self._run_diag_servos_with_flags(False, False)
        inverted_calls = self._run_diag_servos_with_flags(True, True)

        normal_tilt, normal_pan = self._collect_axis_moves(normal_calls)
        inverted_tilt, inverted_pan = self._collect_axis_moves(inverted_calls)

        self.assertGreater(normal_tilt[0][1], normal_tilt[1][1])
        self.assertLess(normal_pan[0][0], normal_pan[1][0])

        self.assertLess(inverted_tilt[0][1], inverted_tilt[1][1])
        self.assertGreater(inverted_pan[0][0], inverted_pan[1][0])


if __name__ == "__main__":
    unittest.main()