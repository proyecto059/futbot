# Ball Goal Controller Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a robust continuous controller that follows the ball at real-time FPS, pushes toward the selected goal, and stops/escapes before crossing white lines.

**Architecture:** Add a pure `BallGoalController` for wheel decisions and keep `scripts/test_chase_dynamic.py` as hardware orchestration. Safety gates run before motor commands. Vision remains HSV-first with YOLO async fallback and target goal selected by `ATTACK_BLUE=1/0`.

**Tech Stack:** Python 3.11+, OpenCV, NumPy, pytest, Raspberry Pi 5 over SSH, `uv run python`.

**Constraints:** Do not use git worktrees. Do not create git commits.

---

### Task 1: Pure Ball-to-Goal Controller

**Files:**
- Create: `src/chase/ball_goal_controller.py`
- Test: create `tests/test_ball_goal_controller.py`

**Step 1: Write failing tests**

Cover these behaviors:

```python
def test_line_detected_returns_stop_or_escape_mode(): ...
def test_far_ball_right_returns_forward_arc_right(): ...
def test_far_ball_left_returns_forward_arc_left(): ...
def test_centered_far_ball_goes_forward(): ...
def test_close_centered_ball_with_blue_goal_right_biases_push_right(): ...
def test_close_centered_ball_with_yellow_goal_left_biases_push_left(): ...
def test_close_ball_without_goal_pushes_only_when_aligned(): ...
```

**Step 2: Run tests to verify RED**

Run: `pytest tests/test_ball_goal_controller.py -v`

Expected: import/module failure.

**Step 3: Implement minimal pure controller**

Create dataclasses:

```python
@dataclass(frozen=True)
class BallGoalCommand:
    v_left: float
    v_right: float
    mode: str
    reason: str
```

Implement `BallGoalController.compute(...)` with:
- hard line safety mode
- ball theta normalized by frame half-width
- forward reduced by `abs(theta)`
- turn proportional with minimum effective turn only outside deadband
- near-ball blend toward target `goal_cx`

**Step 4: Run tests to verify GREEN**

Run: `pytest tests/test_ball_goal_controller.py -v`

Expected: pass.

---

### Task 2: Wire Controller Into Dynamic Chase Script

**Files:**
- Modify: `scripts/test_chase_dynamic.py`
- Test: `tests/test_ball_goal_controller.py`

**Step 1: Add script-level pure helper test if needed**

Avoid importing `scripts/test_chase_dynamic.py` because it opens serial at import time.

**Step 2: Replace inline TRACK wheel math**

Use `BallGoalController.compute` from TRACK after vision snapshot parsing. Keep Kalman/predictor only for smoothing inputs, not for motor policy.

**Step 3: Move line safety before state transitions**

If `line.detected`, do not allow TRACK/PREDICT/PUSH; enter line escape immediately.

**Step 4: Run tests and compile**

Run: `pytest tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_vision_operators.py -v`
Run: `PYTHONPATH=src python -m py_compile scripts/test_chase_dynamic.py`

Expected: pass and no compile output.

---

### Task 3: FPS Diagnostics and Logging Hygiene

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Step 1: Add low-rate FPS counters**

Track loop iterations per second and print once per second with ball/goal/line state.

**Step 2: Reduce noisy logs**

Keep TRACK logs at low rate; keep line and state-transition logs immediate.

**Step 3: Verify compile**

Run: `PYTHONPATH=src python -m py_compile scripts/test_chase_dynamic.py`

Expected: no output.

---

### Task 4: Raspberry Verification

**Files:**
- Sync changed files only.

**Step 1: Copy files to Raspberry**

Use `scp` to `/tmp`, then `cp` into `~/futbot-v2`.

**Step 2: Run tests on Raspberry**

Run: `cd ~/futbot-v2 && PYTHONPATH=src /home/raspi/.local/bin/uv run pytest tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_vision_operators.py -v`

Expected: pass.

**Step 3: Measure static FPS**

Run a short `uv run python -c` sample that loops `vision.tick()` for 180 frames.

Expected: near current 80 FPS tick rate, no large regression.

**Step 4: Run short robot tests**

Run controlled 5-10s tests, stopping with SIGINT so `finally` stops motors.

Ask observer to confirm:
- ball right => forward arc right
- ball left => forward arc left
- centered => forward
- visible line => immediate escape/no crossing
- `ATTACK_BLUE=1` pushes toward blue; `ATTACK_BLUE=0` pushes toward yellow
