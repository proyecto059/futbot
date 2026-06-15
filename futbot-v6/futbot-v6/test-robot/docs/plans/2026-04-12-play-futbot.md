# Play Futbot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--play-futbot` mode with a hybrid behavior-based architecture that searches, approaches, and kicks an orange ball using three kick types (push, angled, spin-shot). Also fix bugs in existing pipelines and unify vision reuse.

**Architecture:** Single continuous loop with layered behaviors (safety > kick > approach > search). Motor output is computed as a continuous function of visual input (PID-style steering). Kick selection is automatic based on ball position. Reuses `ServoBallTracker` and `AdaptiveOrangeBallDetector` from existing code.

**Tech Stack:** Python 3.11, OpenCV, NumPy, same hardware stack (SerialBus, SharedI2CBus, ServoBallTracker, AdaptiveOrangeBallDetector).

---

## Bug Fixes (Tasks 1-3)

These are prerequisites. Fix existing bugs before building new features.

### Task 1: Fix test_gol.py — remove invalid `exposure_cap` kwarg

`ServoBallTracker.__init__` does NOT accept `exposure_cap`. Both `run_gol_giro()` and `run_gol_avance()` pass it, causing a crash at runtime.

**Files:**
- Modify: `test_gol.py:35` and `test_gol.py:149`
- Test: `tests/test_main_approach_logic.py` (existing tests must still pass)

**Step 1: Fix run_gol_giro**

In `test_gol.py:35`, change:
```python
tracker = ServoBallTracker(fw, fh, sweep_enabled=True, exposure_cap=cap)
```
to:
```python
tracker = ServoBallTracker(fw, fh, sweep_enabled=True)
```

**Step 2: Fix run_gol_avance**

In `test_gol.py:149`, change:
```python
tracker = ServoBallTracker(fw, fh, sweep_enabled=True, exposure_cap=cap)
```
to:
```python
tracker = ServoBallTracker(fw, fh, sweep_enabled=True)
```

**Step 3: Run existing tests**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/ -v`
Expected: All existing tests PASS (no regression).

**Step 4: Commit**

```
fix(test_gol): remove invalid exposure_cap kwarg from ServoBallTracker
```

---

### Task 2: Fix test_gol.py — use `create_detector()` with `set_exposure_cap()` instead of global `detect_ball()`

`test_gol.py` uses the global `detect_ball()` function which shares a singleton detector with no exposure control. Should use `create_detector()` + `set_exposure_cap()` like `test_servo_motors.py` does.

**Files:**
- Modify: `test_gol.py:1-17` (imports), `test_gol.py:27-51` (run_gol_giro), `test_gol.py:141-153` (run_gol_avance)

**Step 1: Update imports in test_gol.py**

Change imports at top of file from:
```python
from hardware import (
    BALL_CLOSE_RADIUS,
    CENTER_THRESH,
    DEFAULT_SPEED,
    PAN_CENTER,
    SPIN_360_SEC,
    TILT_CENTER,
    detect_ball,
    differential,
    find_camera,
    log,
    map_x_to_pan,
)
```
to:
```python
from hardware import (
    BALL_CLOSE_RADIUS,
    CENTER_THRESH,
    DEFAULT_SPEED,
    PAN_CENTER,
    SPIN_360_SEC,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
```

**Step 2: Update run_gol_giro to use create_detector**

In `run_gol_giro()`, after `cap, fw, _ = find_camera()` and `fh = ...`, add detector setup. Replace all calls to `detect_ball(frame)` with `detector.detect(frame)`.

The function should become:
```python
def run_gol_giro(sbus, speed):
    cap, fw, _ = find_camera()
    if not cap:
        log.error("[GOL-GIRO] No se detecto camara. Abortando.")
        return
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fcx = fw // 2
    S = speed
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)
    tracker = ServoBallTracker(fw, fh, sweep_enabled=True)
    # ... rest stays the same, but replace detect_ball(frame) -> detector.detect(frame)
```

Similarly replace the two occurrences of `detect_ball(frame)` inside the `while` loop (search phase line ~52 and approach phase line ~70) with `detector.detect(frame)`.

**Step 3: Update run_gol_avance the same way**

Same pattern: add `detector = create_detector()` with `set_exposure_cap()`, replace `detect_ball(frame)` → `detector.detect(frame)`.

**Step 4: Run tests**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 5: Commit**

```
refactor(test_gol): use create_detector with exposure control
```

---

### Task 3: Fix test_sonic.py — use `differential()` instead of raw motor values

`test_sonic.py` uses raw motor values like `(S, -S, S, -S)` and `(-S, -S, -S, -S)` instead of the `differential()` function. This is inconsistent and may produce wrong directions since `differential()` applies the correct sign mapping.

**Files:**
- Modify: `test_sonic.py:1-3` (imports), `test_sonic.py:47` (retreat), `test_sonic.py:53` (spin), `test_sonic.py:60` (advance)

**Step 1: Add `differential` to imports**

Change:
```python
from hardware import PAN_CENTER, TILT_CENTER, SPIN_360_SEC, log
```
to:
```python
from hardware import PAN_CENTER, TILT_CENTER, SPIN_360_SEC, differential, log
```

**Step 2: Fix retreat (line 47)**

Change:
```python
sbus.burst(PAN_CENTER, TILT_CENTER, 1000, S, -S, S, -S)
```
to:
```python
m = differential(-S, -S, S)
sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
```

**Step 3: Fix spin (line 53)**

Change:
```python
sbus.burst(PAN_CENTER, TILT_CENTER, 200, -S, -S, -S, -S)
```
to:
```python
m = differential(S, -S, S)
sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
```

**Step 4: Fix advance (line 60)**

Change:
```python
sbus.burst(PAN_CENTER, TILT_CENTER, 200, -S, S, -S, S)
```
to:
```python
m = differential(S, S, S)
sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
```

**Step 5: Run tests**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 6: Commit**

```
fix(test_sonic): use differential() for correct motor direction mapping
```

---

## Vision Reuse Unification (Task 4)

### Task 4: Write tests for play_futbot pure functions

Write unit tests for the new pure functions that `play_futbot.py` will export: `compute_motor_output`, `should_kick`, and `execute_kick` sequence logic.

**Files:**
- Create: `tests/test_play_futbot.py`

**Step 1: Write the test file**

```python
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


def _load_play_futbot():
    _install_stub_modules()
    try:
        mod = importlib.import_module("play_futbot")
        return (
            mod.compute_motor_output,
            mod.should_kick,
            mod.KICK_PUSH,
            mod.KICK_ANGLED
            mod.KICK_SPIN,
        )
    finally:
        _restore_modules()


class ComputeMotorOutputTests(unittest.TestCase):
    def test_no_ball_zero_speed(self):
        compute_motor_output, _, _, _, _ = _load_play_futbot()
        result = compute_motor_output(
            {"detected": False, "mode": "recenter", "ema_cx": None, "ema_cy": None},
            None,
            250.0,
            640,
            480,
        )
        self.assertEqual(result, (0.0, 0.0))

    def test_ball_centered_approaches_straight(self):
        compute_motor_output, _, _, _, _ = _load_play_futbot()
        result = compute_motor_output(
            {"detected": True, "mode": "tracking", "ema_cx": 320, "ema_cy": 240},
            (320, 240, 40.0),
            250.0,
            640,
            480,
        )
        v_left, v_right = result
        self.assertGreater(v_left, 0)
        self.assertAlmostEqual(v_left, v_right, places=0)

    def test_ball_left_steers_left(self):
        compute_motor_output, _, _, _, _ = _load_play_futbot()
        result_center = compute_motor_output(
            {"detected": True, "mode": "tracking", "ema_cx": 320, "ema_cy": 240},
            (320, 240, 40.0),
            250.0,
            640,
            480,
        )
        result_left = compute_motor_output(
            {"detected": True, "mode": "tracking", "ema_cx": 160, "ema_cy": 240},
            (160, 240, 40.0),
            250.0,
            640,
            480,
        )
        v_left_c, v_right_c = result_center
        v_left_l, v_right_l = result_left
        self.assertLess(v_left_l - v_right_l, v_left_c - v_right_c)


class ShouldKickTests(unittest.TestCase):
    def test_no_kick_when_no_ball(self):
        _, should_kick, KICK_PUSH, KICK_ANGLED, KICK_SPIN = _load_play_futbot()
        result = should_kick(
            {"detected": False, "mode": "recenter", "tracking_locked": False, "ema_cx": None},
            None,
            250.0,
            640,
        )
        self.assertIsNone(result)

    def test_no_kick_when_ball_far(self):
        _, should_kick, KICK_PUSH, KICK_ANGLED, KICK_SPIN = _load_play_futbot()
        result = should_kick(
            {"detected": True, "mode": "tracking", "tracking_locked": True, "ema_cx": 320},
            (320, 240, 20.0),
            250.0,
            640,
        )
        self.assertIsNone(result)

    def test_kick_push_when_centered_and_close(self):
        _, should_kick, KICK_PUSH, KICK_ANGLED, KICK_SPIN = _load_play_futbot()
        result = should_kick(
            {"detected": True, "mode": "tracking", "tracking_locked": True, "ema_cx": 320},
            (320, 240, 65.0),
            250.0,
            640,
        )
        self.assertIn(result, (KICK_PUSH, KICK_ANGLED))

    def test_kick_spin_when_ball_at_left_edge(self):
        _, should_kick, KICK_PUSH, KICK_ANGLED, KICK_SPIN = _load_play_futbot()
        result = should_kick(
            {"detected": True, "mode": "tracking", "tracking_locked": True, "ema_cx": 60},
            (60, 240, 55.0),
            250.0,
            640,
        )
        self.assertEqual(result, KICK_SPIN)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails (module not found)**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/test_play_futbot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'play_futbot'`

**Step 3: Commit the test**

```
test(play_futbot): add unit tests for compute_motor_output and should_kick
```

---

## Core Implementation (Tasks 5-7)

### Task 5: Create play_futbot.py — pure functions

Implement the pure/testable functions: `compute_motor_output`, `should_kick`, and constants.

**Files:**
- Create: `play_futbot.py`

**Step 1: Implement play_futbot.py (pure functions + constants)**

```python
import random
import time

from hardware import (
    BALL_CLOSE_RADIUS,
    CENTER_THRESH,
    DEFAULT_SPEED,
    OBSTACLE_MM,
    PAN_CENTER,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
from test_servos import ServoBallTracker

KICK_PUSH = "push"
KICK_ANGLED = "angled"
KICK_SPIN = "spin"

KICK_RADIUS_THRESHOLD = 50.0
KICK_CENTER_THRESHOLD = 60
KICK_EDGE_MARGIN = 120
KICK_SPIN_RADIUS_THRESHOLD = 40.0

APPROACH_SPEED_RATIO = 0.6
SEARCH_SPIN_SPEED = 150.0
KICK_SHOT_SEC = 1.0
KICK_ANGLED_TURN_SEC = 0.4
KICK_SPIN_SEC = 0.6
RECOVERY_SEC = 1.0
RECOVERY_SPEED = 150.0
PLAY_DURATION = 300.0
SONIC_EVERY_N = 5


def compute_motor_output(result, ball, speed, fw, fh):
    fcx = fw // 2
    fcy = fh // 2

    if not result["detected"] or not result["tracking_locked"]:
        return (0.0, 0.0)

    ema_cx = result["ema_cx"]
    if ema_cx is None:
        return (0.0, 0.0)

    offset_x = ema_cx - fcx
    omega = max(-1.0, min(1.0, float(offset_x) / float(fcx)))

    v_left = speed * APPROACH_SPEED_RATIO * (1 + omega * 0.5)
    v_right = speed * APPROACH_SPEED_RATIO * (1 - omega * 0.5)

    return (v_left, v_right)


def should_kick(result, ball, speed, fw):
    if ball is None:
        return None
    if not result.get("tracking_locked"):
        return None

    cx, cy, r = ball
    ema_cx = result.get("ema_cx")
    if ema_cx is None:
        return None

    fcx = fw // 2
    offset = abs(ema_cx - fcx)

    at_edge = ema_cx < KICK_EDGE_MARGIN or ema_cx > (fw - KICK_EDGE_MARGIN)

    if r >= KICK_RADIUS_THRESHOLD and offset < KICK_CENTER_THRESHOLD:
        if at_edge:
            return KICK_SPIN
        return random.choice([KICK_PUSH, KICK_ANGLED])

    if r >= KICK_SPIN_RADIUS_THRESHOLD and at_edge:
        return KICK_SPIN

    return None
```

**Step 2: Run tests to verify they pass**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/test_play_futbot.py -v`
Expected: All tests PASS.

**Step 3: Commit**

```
feat(play_futbot): add compute_motor_output and should_kick pure functions
```

---

### Task 6: Add `run_play_futbot` main loop to play_futbot.py

Add the main loop function that ties everything together: behaviors + continuous control.

**Files:**
- Modify: `play_futbot.py` — append `run_play_futbot()` at end

**Step 1: Add the run_play_futbot function**

Append to `play_futbot.py`:

```python
def run_play_futbot(sbus, ibus, speed):
    cap, fw, _ = find_camera()
    if not cap:
        log.error("[FUTBOT] No se detecto camara. Abortando.")
        return

    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fcx = fw // 2
    S = speed

    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)

    tracker = ServoBallTracker(fw, fh, sweep_enabled=True, max_track_delta=25)

    baseline = ibus.calibrate_line()
    ibus.set_ultrasonic_led(0x00, 0x10, 0x00)

    log.info("=" * 60)
    log.info("[FUTBOT] === PLAY FUTBOT (%.0fs) ===", PLAY_DURATION)
    log.info("[FUTBOT] Buscar pelota -> acercar -> patear (push/angled/spin)")
    log.info("[FUTBOT] Speed: %.0f | Res: %dx%d", S, fw, fh)
    log.info("=" * 60)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    t0 = time.time()
    last_frame_time = t0
    frame_count = 0
    detect_count = 0
    kick_count = 0
    last_fps_log = t0
    retreating_until = 0.0
    kick_active_until = 0.0
    kick_type_active = None
    kick_phase = None
    kick_phase_until = 0.0
    cached_dist = 9999
    kick_counts = {KICK_PUSH: 0, KICK_ANGLED: 0, KICK_SPIN: 0}

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= PLAY_DURATION:
                break

            now = time.time()
            dt = now - last_frame_time
            last_frame_time = now

            # ── Safety: line follower ──
            line_changed, line_cur = ibus.line_changed(baseline)
            if line_changed and now >= kick_active_until:
                log.warning(
                    "[FUTBOT] Linea blanca! sensores=%s -> retroceder", line_cur
                )
                ibus.set_ultrasonic_led(0xFF, 0x00, 0x00, blink=True)
                m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, S)
                sbus.burst(PAN_CENTER, TILT_CENTER, int(RECOVERY_SEC * 1000), *m)
                time.sleep(RECOVERY_SEC + 0.1)
                ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
                continue

            # ── Safety: ultrasonico ──
            if frame_count % SONIC_EVERY_N == 0:
                cached_dist = ibus.read_ultrasonic()
            if cached_dist < OBSTACLE_MM and now >= kick_active_until:
                log.warning("[FUTBOT] Obstaculo %dmm -> retroceder", cached_dist)
                m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, S)
                sbus.burst(PAN_CENTER, TILT_CENTER, int(RECOVERY_SEC * 1000), *m)
                time.sleep(RECOVERY_SEC + 0.1)
                continue

            # ── Camera frame ──
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            frame_count += 1
            ball = detector.detect(frame, now)
            if ball is not None:
                detect_count += 1

            result = tracker.update(ball, now)
            pan = result["pan"]
            tilt = result["tilt"]

            # ── Kick active sequence ──
            if now < kick_active_until:
                if kick_type_active == KICK_PUSH:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info("[FUTBOT] PUSH shot! (%.1fs)", kick_active_until - now)
                    time.sleep(0.15)

                elif kick_type_active == KICK_ANGLED:
                    if kick_phase == "turn":
                        if now < kick_phase_until:
                            m = differential(-S * 0.5, S * 0.5, S)
                            sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                            log.info("[FUTBOT] ANGLED turn (%.1fs)", kick_phase_until - now)
                            time.sleep(0.15)
                        else:
                            kick_phase = "strike"
                            kick_phase_until = now + KICK_SHOT_SEC
                    elif kick_phase == "strike":
                        m = differential(S, S, S)
                        sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                        log.info("[FUTBOT] ANGLED strike! (%.1fs)", kick_active_until - now)
                        time.sleep(0.15)

                elif kick_type_active == KICK_SPIN:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info("[FUTBOT] SPIN shot! (%.1fs)", kick_active_until - now)
                    time.sleep(0.15)

                continue

            # ── Post-kick recovery ──
            if now < retreating_until:
                m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, S)
                sbus.burst(pan, tilt, 200, *m)
                if frame_count % 10 == 0:
                    log.info("[FUTBOT] Recovering... (%.1fs)", retreating_until - now)
                continue

            # ── Should kick? ──
            kick_type = should_kick(result, ball, S, fw)
            if kick_type is not None:
                kick_count += 1
                kick_counts[kick_type] += 1
                kick_type_active = kick_type
                ibus.set_ultrasonic_led(0xFF, 0x20, 0x00, blink=True)

                if kick_type == KICK_PUSH:
                    kick_active_until = now + KICK_SHOT_SEC
                    kick_phase = None
                    log.info("[FUTBOT] === KICK #%d: PUSH ===", kick_count)
                elif kick_type == KICK_ANGLED:
                    kick_active_until = now + KICK_ANGLED_TURN_SEC + KICK_SHOT_SEC
                    kick_phase = "turn"
                    kick_phase_until = now + KICK_ANGLED_TURN_SEC
                    log.info("[FUTBOT] === KICK #%d: ANGLED ===", kick_count)
                elif kick_type == KICK_SPIN:
                    kick_active_until = now + KICK_SPIN_SEC
                    kick_phase = None
                    log.info("[FUTBOT] === KICK #%d: SPIN ===", kick_count)

                retreating_until = kick_active_until + RECOVERY_SEC
                continue

            # ── Continuous motor output ──
            v_left, v_right = compute_motor_output(result, ball, S, fw, fh)

            if v_left == 0.0 and v_right == 0.0:
                m = (0, 0, 0, 0)
            else:
                m = differential(v_left, v_right, S)

            sbus.burst(pan, tilt, 200, *m)

            # ── Search spin when idle ──
            if not result["tracking_locked"] and result["mode"] in ("recenter", "sweep"):
                m_spin = differential(SEARCH_SPIN_SPEED, -SEARCH_SPIN_SPEED, S)
                sbus.burst(pan, tilt, 200, *m_spin)

            # ── Periodic logging ──
            if frame_count % 10 == 0:
                ball_str = "LOST"
                if ball is not None:
                    cx, cy, r = ball
                    ball_str = "cx=%d cy=%d r=%.0f" % (cx, cy, r)
                log.info(
                    "[FUTBOT] %.1fs | %s | mode=%s | m=(%d,%d,%d,%d) | pan=%d tilt=%d",
                    elapsed,
                    ball_str,
                    result["mode"],
                    int(m[0]),
                    int(m[1]),
                    int(m[2]),
                    int(m[3]),
                    pan,
                    tilt,
                )

            if now - last_fps_log >= 5.0:
                fps = frame_count / elapsed if elapsed > 0 else 0
                pct = detect_count / frame_count * 100 if frame_count > 0 else 0
                log.info(
                    "[FUTBOT] --- FPS:%.1f Detect:%.0f%% (%d/%d) Kicks:%d (P:%d A:%d S:%d) ---",
                    fps,
                    pct,
                    detect_count,
                    frame_count,
                    kick_count,
                    kick_counts[KICK_PUSH],
                    kick_counts[KICK_ANGLED],
                    kick_counts[KICK_SPIN],
                )
                last_fps_log = now

    except KeyboardInterrupt:
        log.info("[FUTBOT] Interrumpido")
    finally:
        sbus.stop(PAN_CENTER, TILT_CENTER)
        time.sleep(0.3)
        cap.release()
        total = time.time() - t0
        pct = detect_count / frame_count * 100 if frame_count > 0 else 0
        log.info("=" * 60)
        log.info("[FUTBOT] === FIN (%.1fs) ===", total)
        log.info(
            "[FUTBOT] Frames:%d Detects:%d (%.0f%%) Kicks:%d (P:%d A:%d S:%d)",
            frame_count,
            detect_count,
            pct,
            kick_count,
            kick_counts[KICK_PUSH],
            kick_counts[KICK_ANGLED],
            kick_counts[KICK_SPIN],
        )
        log.info("=" * 60)
```

**Step 2: Run tests**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 3: Commit**

```
feat(play_futbot): add run_play_futbot main loop with 3 kick types
```

---

### Task 7: Wire `--play-futbot` into main.py

Add the CLI flag and import to `main.py`.

**Files:**
- Modify: `main.py:37` (import), `main.py:69-140` (argparse)

**Step 1: Add import**

After `from test_gol import run_gol_giro, run_gol_avance` (line 37), add:
```python
from play_futbot import run_play_futbot
```

**Step 2: Add argparse argument**

After the `--gol-avance` argument block (around line 139), add:
```python
    ap.add_argument(
        "--play-futbot",
        action="store_true",
        help="Jugar futbol: buscar pelota -> acercar -> patear (push/angled/spin)",
    )
```

**Step 3: Add handler block**

After the `--gol-avance` handler block (around line 262), add:
```python
    # ── Play-futbot mode: UART + I2C + camara ──
    if args.play_futbot:
        ibus_pf = SharedI2CBus()
        try:
            run_play_futbot(sbus, ibus_pf, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus_pf.close()
            log.info("TurboPi – Fin (play-futbot)")
        return
```

**Step 4: Run all tests**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python -m pytest tests/ -v`
Expected: All tests PASS.

**Step 5: Verify CLI help shows new flag**

Run: `cd /home/shino/Documents/personal/futbot-uas-git/test-robot && uv run python main.py --help`
Expected: Shows `--play-futbot` in help text.

**Step 6: Commit**

```
feat(main): add --play-futbot CLI flag
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Fix test_gol.py `exposure_cap` bug | `test_gol.py` |
| 2 | Unify test_gol.py to use `create_detector()` | `test_gol.py` |
| 3 | Fix test_sonic.py raw motor values | `test_sonic.py` |
| 4 | Write unit tests for play_futbot | `tests/test_play_futbot.py` |
| 5 | Implement play_futbot.py pure functions | `play_futbot.py` |
| 6 | Add run_play_futbot main loop | `play_futbot.py` |
| 7 | Wire `--play-futbot` into main.py | `main.py` |
