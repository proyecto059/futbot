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


def _load_main_symbols():
    _install_stub_modules()
    try:
        main = importlib.import_module("main")
        return (
            main.APPROACH_HOLD_SEC,
            main.APPROACH_LOST_CONFIRM_FRAMES,
            main.should_hold_approach,
        )
    finally:
        _restore_modules()


def _load_servo_test_symbols():
    _install_stub_modules()
    try:
        test_servos = importlib.import_module("test_servos")
        return (
            test_servos.recenter_step,
            test_servos.tracking_step,
            test_servos.should_enter_tracking,
            test_servos.should_keep_lock_on_miss,
            test_servos.should_hold_pan,
            test_servos.max_tracking_delta,
            test_servos.detection_is_consistent,
            test_servos.should_validate_detection,
        )
    finally:
        _restore_modules()


APPROACH_HOLD_SEC, APPROACH_LOST_CONFIRM_FRAMES, should_hold_approach = (
    _load_main_symbols()
)
(
    recenter_step,
    tracking_step,
    should_enter_tracking,
    should_keep_lock_on_miss,
    should_hold_pan,
    max_tracking_delta,
    detection_is_consistent,
    should_validate_detection,
) = _load_servo_test_symbols()


class ApproachHoldLogicTests(unittest.TestCase):
    def test_holds_while_miss_count_within_threshold(self):
        self.assertTrue(
            should_hold_approach(
                miss_count=APPROACH_LOST_CONFIRM_FRAMES,
                last_seen_ts=10.0,
                now_ts=10.0 + APPROACH_HOLD_SEC + 1.0,
            )
        )

    def test_holds_while_within_hold_window_after_threshold(self):
        self.assertTrue(
            should_hold_approach(
                miss_count=APPROACH_LOST_CONFIRM_FRAMES + 1,
                last_seen_ts=20.0,
                now_ts=20.0 + APPROACH_HOLD_SEC - 0.01,
            )
        )

    def test_releases_after_threshold_and_timeout_elapsed(self):
        self.assertFalse(
            should_hold_approach(
                miss_count=APPROACH_LOST_CONFIRM_FRAMES + 1,
                last_seen_ts=30.0,
                now_ts=30.0 + APPROACH_HOLD_SEC + 0.01,
            )
        )


class RecenterStepTests(unittest.TestCase):
    def test_recenter_step_advances_when_fractional_step_truncates(self):
        self.assertEqual(recenter_step(78, 90, 0.08), 79)


class TrackingStepTests(unittest.TestCase):
    def test_tracking_step_limits_large_jump_per_frame(self):
        self.assertEqual(tracking_step(90, 150, 0.4, 8), 98)

    def test_tracking_step_moves_at_least_one_degree(self):
        self.assertEqual(tracking_step(90, 91, 0.1, 8), 91)

    def test_tracking_step_can_move_negative_direction(self):
        self.assertEqual(tracking_step(90, 20, 0.4, 8), 82)


class PanHoldTests(unittest.TestCase):
    def test_hold_pan_inside_deadband(self):
        self.assertTrue(should_hold_pan(320, 320, 35))
        self.assertTrue(should_hold_pan(340, 320, 35))
        self.assertTrue(should_hold_pan(300, 320, 35))

    def test_not_hold_pan_outside_deadband(self):
        self.assertFalse(should_hold_pan(356, 320, 35))


class AdaptiveDeltaTests(unittest.TestCase):
    def test_near_center_uses_small_delta(self):
        self.assertEqual(max_tracking_delta(330, 320, 35, 3, 8), 3)

    def test_far_from_center_uses_large_delta(self):
        self.assertEqual(max_tracking_delta(500, 320, 35, 3, 8), 8)


class TrackingLockLogicTests(unittest.TestCase):
    def test_locked_tracking_reacquires_without_acquire_mode(self):
        self.assertTrue(
            should_enter_tracking(
                consecutive_detect=1,
                tracking_locked=True,
                track_confirm_frames=2,
            )
        )

    def test_unlocked_tracking_still_requires_confirmation(self):
        self.assertFalse(
            should_enter_tracking(
                consecutive_detect=1,
                tracking_locked=False,
                track_confirm_frames=2,
            )
        )

    def test_keep_lock_during_transient_miss(self):
        self.assertTrue(
            should_keep_lock_on_miss(
                consecutive_miss=1,
                hold_window_active=False,
                lost_confirm_frames=3,
            )
        )

    def test_reset_lock_only_after_confirmed_loss(self):
        self.assertFalse(
            should_keep_lock_on_miss(
                consecutive_miss=10,
                hold_window_active=False,
                lost_confirm_frames=3,
            )
        )


class DetectionConsistencyTests(unittest.TestCase):
    def test_accepts_detection_without_previous_reference(self):
        self.assertTrue(detection_is_consistent(None, (320, 240, 30), 120, 0.6))

    def test_accepts_small_position_change_and_radius_change(self):
        self.assertTrue(
            detection_is_consistent((320, 240, 30), (342, 251, 24), 120, 0.6)
        )

    def test_rejects_large_position_jump(self):
        self.assertFalse(
            detection_is_consistent((320, 240, 30), (500, 240, 30), 120, 0.6)
        )

    def test_rejects_large_radius_drop(self):
        self.assertFalse(
            detection_is_consistent((320, 240, 30), (330, 250, 10), 120, 0.6)
        )


class DetectionValidationGateTests(unittest.TestCase):
    def test_does_not_validate_consistency_before_lock(self):
        self.assertFalse(
            should_validate_detection(
                previous_ball=(320, 240, 30),
                has_seen_ball=True,
                tracking_locked=False,
                last_seen_ts=10.0,
                now_ts=10.1,
                hold_no_detect_sec=0.4,
            )
        )

    def test_validates_consistency_after_lock_within_hold_window(self):
        self.assertTrue(
            should_validate_detection(
                previous_ball=(320, 240, 30),
                has_seen_ball=True,
                tracking_locked=True,
                last_seen_ts=10.0,
                now_ts=10.1,
                hold_no_detect_sec=0.4,
            )
        )


if __name__ == "__main__":
    unittest.main()
