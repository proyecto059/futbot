# Tracking Improvements: Feed-Forward + Kalman + Adaptive Gain

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve ball detection during robot rotation from 45% to 65%+ by adding fast recenter, time-based feed-forward, adaptive gain, and Kalman prediction.

**Architecture:** 4 incremental improvements to `ServoBallTracker` in `test_servos.py` + caller changes in `test_servo_motors.py`. Each is independently testable on robot via `--test-servo-motors`.

**Tech Stack:** Python 3, OpenCV KalmanFilter (`cv2.KalmanFilter`), existing servo/motor framework.

**Baseline:** 45% total (left45:57%, right45:62%, pause2:44%, pause4:71%)

---

### Task 1: Fast Recenter Post-Rotation

**Problem:** After `center1`/`center2` (with feed-forward), pan is ~25 deg off-center. `recenter_alpha=0.1` takes ~3s to recover, but pause phases only last 2s -> pause2 regressed from 70% to 44%.

**Files:**
- Modify: `test_servos.py` - `ServoBallTracker.__init__()` and `update()`

**Step 1: Add state tracking to `__init__`**

In `ServoBallTracker.__init__()`, after `self.sweep_dir = 1` (line 185), add:

```python
self.frames_since_rotation = 0
```

**Step 2: Update `frames_since_rotation` in `update()`**

At the top of `update()`, right after `has_rotation = abs(rotation_ff) > 0.01` (line 190), add:

```python
if has_rotation:
    self.frames_since_rotation = 0
else:
    self.frames_since_rotation += 1
```

**Step 3: Add adaptive recenter alpha method**

Add a method to the `ServoBallTracker` class:

```python
def _recenter_alpha(self):
    if self.frames_since_rotation < 5:
        return 0.4
    if self.frames_since_rotation < 15:
        return 0.2
    return self.recenter_alpha
```

**Step 4: Replace `self.recenter_alpha` with `self._recenter_alpha()` in recenter path**

In the recenter branch (lines ~347-354), change:

```python
self.pan = recenter_step(self.pan, PAN_CENTER, self.recenter_alpha)
self.tilt = recenter_step(self.tilt, TILT_CENTER, self.recenter_alpha)
```

to:

```python
alpha = self._recenter_alpha()
self.pan = recenter_step(self.pan, PAN_CENTER, alpha)
self.tilt = recenter_step(self.tilt, TILT_CENTER, alpha)
```

**Step 5: Deploy and test on robot**

```bash
scp test_servos.py raspi@raspi.local:~/test-robot/
ssh raspi@raspi.local "cd ~/test-robot && export PATH=\$HOME/.local/bin:\$PATH && uv run python main.py --test-servo-motors 2>&1"
```

**Expected:** pause2 recovers faster -> 44% to ~55-60%. pause1/3 may improve slightly too.

**Commit:** `feat: fast recenter post-rotation (adaptive alpha)`

---

### Task 2: Time-Based Feed-Forward

**Problem:** `ROTATION_FF_DEG_PER_FRAME = 6.0` assumes constant frame rate. At 13 FPS vs 16 FPS, the compensation per frame differs significantly, causing over/under-compensation.

**Files:**
- Modify: `test_servo_motors.py` - replace constant with rate-based calculation

**Step 1: Add new constant in `test_servo_motors.py`**

Replace line 22:
```python
ROTATION_FF_DEG_PER_FRAME = 6.0
```
with:
```python
ROTATION_RATE_DEG_PER_SEC = 90.0
```

**Step 2: Add `last_frame_time` tracking in the main loop**

In `run_test_servo_motors()`, after `t0 = time.time()` (line 71), add:

```python
last_frame_time = t0
```

Inside the loop, after `now = time.time()` (line 88), add:

```python
dt = now - last_frame_time
last_frame_time = now
```

**Step 3: Compute time-based `rot_ff`**

Replace the `rot_ff` calculation block (lines 109-114):

```python
if phase_name in ("left45", "center2"):
    rot_ff = ROTATION_RATE_DEG_PER_SEC * dt
elif phase_name in ("right45", "center1"):
    rot_ff = -ROTATION_RATE_DEG_PER_SEC * dt
else:
    rot_ff = 0.0
```

**Step 4: Deploy and test**

```bash
scp test_servo_motors.py raspi@raspi.local:~/test-robot/
ssh raspi@raspi.local "cd ~/test-robot && export PATH=\$HOME/.local/bin:\$PATH && uv run python main.py --test-servo-motors 2>&1"
```

**Expected:** More consistent compensation regardless of FPS jitter. left45/right45 should stabilize around same %.

**Commit:** `feat: time-based feed-forward instead of per-frame constant`

---

### Task 3: Adaptive Gain During Rotation

**Problem:** `PAN_GAIN = 0.02` and `max_track_delta = 25` are fixed. During rotation the ball moves ~40px/frame but the servo only corrects ~2 deg per frame - too slow to keep up.

**Files:**
- Modify: `test_servos.py` - `ServoBallTracker.update()` tracking section

**Step 1: Add adaptive gain constants at top of `test_servos.py`**

After `RADIUS_CONSISTENCY_MAX = 2.0` (line 36), add:

```python
PAN_GAIN_ROTATION = 0.04
MAX_TRACK_DELTA_ROTATION = 30
```

**Step 2: Modify tracking section to use adaptive gain**

In the tracking branch of `update()`, replace the fixed gain section (lines ~280-295):

```python
if SERVO_PAN_INVERTED:
    pan_delta = -PAN_GAIN * offset_x
else:
    pan_delta = PAN_GAIN * offset_x

if SERVO_TILT_INVERTED:
    tilt_delta = TILT_GAIN * offset_y
else:
    tilt_delta = -TILT_GAIN * offset_y

pan_delta = max(
    -self.max_track_delta, min(self.max_track_delta, pan_delta)
)
tilt_delta = max(
    -self.max_track_delta, min(self.max_track_delta, tilt_delta)
)
```

with:

```python
pan_gain = PAN_GAIN_ROTATION if has_rotation else PAN_GAIN
max_delta = MAX_TRACK_DELTA_ROTATION if has_rotation else self.max_track_delta

if SERVO_PAN_INVERTED:
    pan_delta = -pan_gain * offset_x
else:
    pan_delta = pan_gain * offset_x

if SERVO_TILT_INVERTED:
    tilt_delta = TILT_GAIN * offset_y
else:
    tilt_delta = -TILT_GAIN * offset_y

pan_delta = max(-max_delta, min(max_delta, pan_delta))
tilt_delta = max(-max_delta, min(max_delta, tilt_delta))
```

**Step 3: Deploy and test**

```bash
scp test_servos.py raspi@raspi.local:~/test-robot/
ssh raspi@raspi.local "cd ~/test-robot && export PATH=\$HOME/.local/bin:\$PATH && uv run python main.py --test-servo-motors 2>&1"
```

**Expected:** left45/right45 improve from ~57-62% to ~65-70%. The servo responds faster to ball movement during rotation.

**Commit:** `feat: adaptive pan gain and max delta during rotation`

---

### Task 4: Kalman Filter Prediction

**Problem:** When ball is lost for 1-3 frames during rotation, the servo freezes (hold mode). A Kalman filter maintains velocity state and extrapolates position during gaps, keeping the servo moving toward where the ball should be.

**Files:**
- Modify: `test_servos.py` - add `BallKalmanFilter` class and integrate into `ServoBallTracker`

**Step 1: Add `import numpy as np` at top of `test_servos.py`**

The file already imports `cv2` but needs numpy for KalmanFilter arrays:

```python
import numpy as np
```

**Step 2: Add `BallKalmanFilter` class before `ServoBallTracker`**

Add after the `should_validate_detection` function (before line 130):

```python
class BallKalmanFilter:
    def __init__(self):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0]], np.float32
        )
        self.kf.transitionMatrix = np.array(
            [[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]],
            np.float32,
        )
        self.kf.processNoiseCov = np.diag([4, 4, 1, 1]).astype(np.float32)
        self.kf.measurementNoiseCov = np.diag([10, 10]).astype(np.float32)
        self.initialized = False

    def init(self, cx, cy):
        self.kf.statePost = np.array(
            [[cx], [cy], [0], [0]], np.float32
        )
        self.initialized = True

    def predict(self):
        if not self.initialized:
            return None
        p = self.kf.predict()
        return int(p[0]), int(p[1])

    def correct(self, cx, cy):
        if not self.initialized:
            self.init(cx, cy)
            return cx, cy
        meas = np.array([[np.float32(cx)], [np.float32(cy)]])
        c = self.kf.correct(meas)
        return int(c[0]), int(c[1])

    def reset(self):
        self.initialized = False
```

**Step 3: Add Kalman filter to `ServoBallTracker.__init__()`**

After `self.sweep_dir = 1`, add:

```python
self.kf = BallKalmanFilter()
self.kf_pred = None
```

**Step 4: Feed Kalman on detection**

In the `update()` method, **when ball is detected** (the `if ball:` branch), after the EMA update block and before the tracking logic, add Kalman correction:

```python
kf_cx, kf_cy = self.kf.correct(cx, cy)
self.kf_pred = (kf_cx, kf_cy)
```

**Step 5: Use Kalman prediction when ball is lost**

In the `else:` branch (ball lost), at the start, add prediction:

```python
pred = self.kf.predict()
if pred is not None:
    self.kf_pred = pred
```

Then, in the `should_keep_lock_on_miss` True branch (hold mode), if we have a prediction and we are NOT rotating, use the predicted position to drive the servo:

Replace the hold block:
```python
if should_keep_lock_on_miss(
    self.consecutive_miss,
    hold_window_active,
    self.lost_confirm_frames,
):
    mode = "hold"
    if has_rotation:
        self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + rotation_ff)))
```

with:

```python
if should_keep_lock_on_miss(
    self.consecutive_miss,
    hold_window_active,
    self.lost_confirm_frames,
):
    mode = "hold"
    if has_rotation:
        self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + rotation_ff)))
    elif self.kf_pred is not None and self.consecutive_miss <= 5:
        pred_cx, pred_cy = self.kf_pred
        offset_x = pred_cx - self.fcx
        if abs(offset_x) > self.track_deadband_px:
            if SERVO_PAN_INVERTED:
                pan_delta = -PAN_GAIN * offset_x
            else:
                pan_delta = PAN_GAIN * offset_x
            pan_delta = max(
                -self.max_track_delta,
                min(self.max_track_delta, pan_delta),
            )
            self.pan = max(
                PAN_MIN, min(PAN_MAX, int(self.pan + pan_delta))
            )
            mode = "kf_track"
```

**Step 6: Reset Kalman when lock is lost**

In the lock-expired branch where `self.tracking_locked = False`, add:

```python
self.kf.reset()
self.kf_pred = None
```

**Step 7: Deploy and test**

```bash
scp test_servos.py raspi@raspi.local:~/test-robot/
ssh raspi@raspi.local "cd ~/test-robot && export PATH=\$HOME/.local/bin:\$PATH && uv run python main.py --test-servo-motors 2>&1"
```

**Expected:** Detection during rotation improves significantly (57% -> 70%+). Pause phases recover faster because servo keeps moving in the right direction during 1-3 frame gaps.

**Commit:** `feat: Kalman filter prediction for ball tracking during rotation`

---

## Validation Criteria

After all 4 tasks, the target metrics are:

| Phase | Before | Target |
|-------|--------|--------|
| left45 | 57% | **65%+** |
| right45 | 62% | **65%+** |
| pause1 | 1% | **10%+** |
| pause2 | 44% | **60%+** |
| center1 | 12% | **20%+** |
| center2 | 18% | **25%+** |
| **Total** | **45%** | **60%+** |

After each task, deploy and run `--test-servo-motors` on the robot. If any task causes regression, revert and retune parameters before proceeding.

## Key Parameters to Tune

| Parameter | Default | Notes |
|-----------|---------|-------|
| `ROTATION_RATE_DEG_PER_SEC` | 90.0 | Robot rotation speed. Can calibrate empirically. |
| `PAN_GAIN_ROTATION` | 0.04 | 2x base gain during rotation |
| `MAX_TRACK_DELTA_ROTATION` | 30 | Larger steps allowed during rotation |
| Kalman Q (process noise) | diag(4,4,1,1) | Higher = trusts measurement more |
| Kalman R (measurement noise) | diag(10,10) | Higher = trusts prediction more |
| Fast recenter alpha | 0.4 (first 5 frames) | Aggressive snap-back post-rotation |
