# Servo Tracking Direction Bugfix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix opposite-direction servo tracking and stabilize ball reacquisition in both `--test-servo` and the main `SEARCHING/APPROACHING` flow.

**Architecture:** Introduce shared camera-to-servo mapping helpers with axis inversion controls in `hardware.py`, then consume those helpers from `test_servos.py` and `main.py` so both paths use identical pan direction logic. Add short hold-before-recenter behavior to avoid immediate loss after brief detection dropouts.

**Tech Stack:** Python 3.11, opencv-python-headless, numpy, unittest, ruff

---

## Task 1: Add failing tests for shared servo mapping

**Files:**
- Create: `tests/test_servo_mapping.py`

**Step 1: Create test directory**

Run: `mkdir -p tests`
Expected: `tests/` exists.

**Step 2: Write failing unit tests for mapping behavior**

```python
import unittest

from hardware import map_ball_to_servos, map_x_to_pan, map_y_to_tilt


class ServoMappingTests(unittest.TestCase):
    def test_pan_non_inverted_edges(self):
        self.assertEqual(map_x_to_pan(0, 640, pan_inverted=False), 0)
        self.assertEqual(map_x_to_pan(640, 640, pan_inverted=False), 180)

    def test_pan_inverted_edges(self):
        self.assertEqual(map_x_to_pan(0, 640, pan_inverted=True), 180)
        self.assertEqual(map_x_to_pan(640, 640, pan_inverted=True), 0)

    def test_tilt_non_inverted_edges(self):
        self.assertEqual(map_y_to_tilt(0, 480, tilt_inverted=False), 180)
        self.assertEqual(map_y_to_tilt(480, 480, tilt_inverted=False), 0)

    def test_tilt_inverted_edges(self):
        self.assertEqual(map_y_to_tilt(0, 480, tilt_inverted=True), 0)
        self.assertEqual(map_y_to_tilt(480, 480, tilt_inverted=True), 180)

    def test_map_ball_to_servos_clamps_out_of_bounds(self):
        pan, tilt = map_ball_to_servos(-100, 9999, 640, 480, True, False)
        self.assertEqual(pan, 180)
        self.assertEqual(tilt, 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 3: Run tests to verify failure before implementation**

Run: `python -m unittest tests.test_servo_mapping -v`
Expected: FAIL with import error for missing `map_x_to_pan` / `map_y_to_tilt` / `map_ball_to_servos`.

**Step 4: Commit failing tests**

```bash
git add tests/test_servo_mapping.py
git commit -m "test: add failing tests for servo coordinate mapping"
```

---

## Task 2: Implement shared mapping helpers in `hardware.py`

**Files:**
- Modify: `hardware.py`

**Step 1: Add servo axis direction config constants near existing servo constants**

```python
SERVO_PAN_INVERTED = True
SERVO_TILT_INVERTED = False
```

**Step 2: Add reusable helpers below existing motion helpers**

```python
def _clamp_int(value, lo, hi):
    return max(lo, min(hi, int(value)))


def map_x_to_pan(cx, frame_width, pan_inverted=SERVO_PAN_INVERTED):
    if frame_width <= 0:
        return PAN_CENTER
    x_norm = max(0.0, min(1.0, cx / float(frame_width)))
    pan = int(x_norm * 180)
    if pan_inverted:
        pan = 180 - pan
    return _clamp_int(pan, PAN_MIN, PAN_MAX)


def map_y_to_tilt(cy, frame_height, tilt_inverted=SERVO_TILT_INVERTED):
    if frame_height <= 0:
        return TILT_CENTER
    y_norm = max(0.0, min(1.0, cy / float(frame_height)))
    tilt = int((1.0 - y_norm) * 180)
    if tilt_inverted:
        tilt = 180 - tilt
    return _clamp_int(tilt, 0, 180)


def map_ball_to_servos(
    cx,
    cy,
    frame_width,
    frame_height,
    pan_inverted=SERVO_PAN_INVERTED,
    tilt_inverted=SERVO_TILT_INVERTED,
):
    pan = map_x_to_pan(cx, frame_width, pan_inverted=pan_inverted)
    tilt = map_y_to_tilt(cy, frame_height, tilt_inverted=tilt_inverted)
    return pan, tilt
```

**Step 3: Run mapping unit tests**

Run: `python -m unittest tests.test_servo_mapping -v`
Expected: PASS (`OK`).

**Step 4: Commit helper implementation**

```bash
git add hardware.py
git commit -m "feat: add shared camera-to-servo mapping helpers"
```

---

## Task 3: Update `--test-servo` to use shared mapping and hold-before-recenter

**Files:**
- Modify: `test_servos.py`

**Step 1: Import shared helpers and axis flags**

Change imports to include:

```python
SERVO_PAN_INVERTED,
SERVO_TILT_INVERTED,
map_ball_to_servos,
```

**Step 2: Add short tracking-loss tuning constants near `TEST_SERVO_DURATION`**

```python
TRACK_CONFIRM_FRAMES = 2
LOST_CONFIRM_FRAMES = 3
HOLD_NO_DETECT_SEC = 0.4
TRACK_ALPHA = 0.4
RECENTER_ALPHA = 0.08
```

**Step 3: Add detection counters and last-seen timestamp state**

Initialize before loop:

```python
consecutive_detect = 0
consecutive_miss = 0
last_seen_ts = 0.0
```

**Step 4: Replace inline target mapping in ball-detected branch**

```python
target_pan, target_tilt = map_ball_to_servos(cx, cy, fw, fh)
pan = int(last_pan + (target_pan - last_pan) * TRACK_ALPHA)
tilt = int(last_tilt + (target_tilt - last_tilt) * TRACK_ALPHA)
```

Log should include flags and mode:

```python
"[TEST-SERVO] ... mode=tracking inv_pan=%s inv_tilt=%s ..."
```

using `SERVO_PAN_INVERTED` and `SERVO_TILT_INVERTED`.

**Step 5: Replace immediate recenter in no-ball branch with hold + gradual recenter**

Behavior:
- If `consecutive_miss < LOST_CONFIRM_FRAMES` OR `(now - last_seen_ts) < HOLD_NO_DETECT_SEC` -> keep last pan/tilt (hold).
- Else -> gradual recenter with `RECENTER_ALPHA`.

**Step 6: Run lint and unit tests**

Run:
- `ruff check test_servos.py hardware.py tests/test_servo_mapping.py`
- `python -m unittest tests.test_servo_mapping -v`

Expected: no lint errors; unit tests still pass.

**Step 7: Commit test-servo behavior changes**

```bash
git add test_servos.py
git commit -m "fix: stabilize servo tracking with hold-before-recenter"
```

---

## Task 4: Apply same pan mapping + short loss hold in main state machine

**Files:**
- Modify: `main.py`

**Step 1: Import shared pan helper**

Add to imports:

```python
map_x_to_pan,
```

**Step 2: Add approach-loss tuning constants near state setup**

```python
APPROACH_LOST_CONFIRM_FRAMES = 3
APPROACH_HOLD_SEC = 0.4
```

**Step 3: Track last-seen and miss counters in main loop state**

Add variables near `state = State.SEARCHING`:

```python
approach_last_seen_ts = 0.0
approach_miss_count = 0
```

**Step 4: Replace inline pan mapping with helper in `SEARCHING` and `APPROACHING`**

Replace:

```python
pan = max(PAN_MIN, min(PAN_MAX, int(cx / fw * 180)))
```

with:

```python
pan = map_x_to_pan(cx, fw)
```

**Step 5: In `APPROACHING`, hold briefly on temporary loss before resetting to `SEARCHING`**

When `ball` is present:
- reset `approach_miss_count`
- set `approach_last_seen_ts = time.time()`

When `ball` is absent:
- increment `approach_miss_count`
- if still within hold conditions, keep current pan and continue loop without immediate state reset
- only reset to `SEARCHING` after hold timeout and miss threshold are both exceeded

**Step 6: Run lint and syntax checks**

Run:
- `ruff check main.py hardware.py test_servos.py tests/test_servo_mapping.py`
- `python -m compileall main.py test_servos.py hardware.py`

Expected: no lint/syntax errors.

**Step 7: Commit main integration changes**

```bash
git add main.py
git commit -m "fix: unify servo pan mapping and transient-loss handling in main flow"
```

---

## Task 5: Verification on robot hardware

**Files:**
- Modify: none

**Step 1: Run static quadrant validation in servo test mode**

Run: `python main.py --test-servo`

Expected:
- Ball at left side -> pan moves toward left physical direction.
- Ball at right side -> pan moves toward right physical direction.
- Ball at top/bottom -> tilt moves toward ball direction.

**Step 2: Run dynamic tracking validation**

Run: `python main.py --test-servo`

Expected:
- Fewer immediate `Sin pelota - centrando` transitions after short misses.
- Smooth reacquisition when occlusion is brief (0.2-0.4s).

**Step 3: Run autonomous consistency validation**

Run: `python main.py --no-ultrasonic --no-line-follower`

Expected:
- `SEARCHING/APPROACHING` pan direction matches `--test-servo` direction behavior.

**Step 4: Commit verification notes (if keeping logs in docs)**

```bash
git add docs/plans/2026-04-10-servo-tracking-direction-bug-design.md
git commit -m "docs: record servo tracking bugfix validation outcomes"
```
