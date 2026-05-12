# Smooth Chase Miss Tolerance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce chase zigzag by keeping `TRACK` active through short HSV ball dropouts.

**Architecture:** Add a small pure helper in `chase.visual_servo_controller` that decides whether tracking should continue during consecutive missed frames. Use that helper in `scripts/test_chase_dynamic.py` so brief misses reuse the last valid forward/turn command with decay, while longer loss still transitions into `PREDICT` and search.

**Tech Stack:** Python, pytest, existing vision/chase operators.

---

### Task 1: Add Miss Tolerance Helper

**Files:**
- Modify: `src/chase/visual_servo_controller.py`
- Modify: `tests/test_visual_servo_controller.py`

**Step 1: Write the failing test**

Add tests for a pure helper named `should_hold_track_on_miss(miss_streak, max_miss_frames=8)`:

```python
def test_hold_track_on_short_ball_miss():
    assert should_hold_track_on_miss(1, max_miss_frames=8) is True
    assert should_hold_track_on_miss(8, max_miss_frames=8) is True


def test_stop_holding_track_after_long_ball_miss():
    assert should_hold_track_on_miss(9, max_miss_frames=8) is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_visual_servo_controller.py::test_hold_track_on_short_ball_miss tests/test_visual_servo_controller.py::test_stop_holding_track_after_long_ball_miss -v`

Expected: FAIL because `should_hold_track_on_miss` does not exist.

**Step 3: Write minimal implementation**

Add:

```python
def should_hold_track_on_miss(miss_streak: int, max_miss_frames: int = 8) -> bool:
    return 0 < miss_streak <= max_miss_frames
```

**Step 4: Run test to verify it passes**

Run the same focused pytest command.

Expected: PASS.

### Task 2: Use Miss Tolerance In Chase FSM

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Step 1: Import helper and add constants**

Import `should_hold_track_on_miss` from `chase.visual_servo_controller`.

Add constants near existing chase tuning:

```python
TRACK_MISS_HOLD_FRAMES = int(os.environ.get("TRACK_MISS_HOLD_FRAMES", "8"))
TRACK_MISS_HOLD_SPEED_SCALE = float(os.environ.get("TRACK_MISS_HOLD_SPEED_SCALE", "0.75"))
TRACK_MISS_HOLD_TURN_SCALE = float(os.environ.get("TRACK_MISS_HOLD_TURN_SCALE", "0.55"))
```

**Step 2: Keep TRACK through short misses**

In the `TRACK` state, replace immediate transition to `PREDICT` on a missing ball with:

```python
miss_streak += 1
if should_hold_track_on_miss(miss_streak, TRACK_MISS_HOLD_FRAMES):
    decay = max(0.25, 1.0 - miss_streak / float(TRACK_MISS_HOLD_FRAMES + 1))
    v_cmd = last_valid_v * TRACK_MISS_HOLD_SPEED_SCALE * decay
    turn_cmd = last_valid_w * TRACK_MISS_HOLD_TURN_SCALE * decay
    vL = v_cmd + turn_cmd
    vR = -(v_cmd - turn_cmd)
    drive(vL, vR, 80)
else:
    state = PREDICT
    loss_start_t = now
```

Preserve existing `PREDICT`/`RECOVER` behavior after the tolerance expires.

**Step 3: Run focused tests locally**

Run: `pytest tests/test_ball_fusion_operator.py tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_vision_operators.py -v`

Expected: PASS.

**Step 4: Sync and verify on Raspberry**

Run: `rsync -avR scripts/test_chase_dynamic.py src/chase/visual_servo_controller.py tests/test_visual_servo_controller.py raspi@raspi.local:~/futbot-v2/.`

Run: `ssh raspi@raspi.local 'cd ~/futbot-v2 && PYTHONPATH=src /home/raspi/.local/bin/uv run pytest tests/test_ball_fusion_operator.py tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_vision_operators.py -v'`

Expected: PASS.

### Task 3: Hardware Trial

**Files:**
- Output: `output/test_goal_blue_3/test_chase_dynamic_attack_blue.log`

**Step 1: Run short trial**

Run: `ssh raspi@raspi.local 'cd ~/futbot-v2 && ATTACK_BLUE=1 BALL_VISIBLE_MIN_RADIUS=8.0 timeout --signal=INT 25s /home/raspi/.local/bin/uv run python scripts/test_chase_dynamic.py' > output/test_goal_blue_3/test_chase_dynamic_attack_blue.log 2>&1`

Expected: Log shows fewer immediate `RECOVER`/`MAP` transitions after single missed detections.

**Step 2: Inspect behavior**

Check whether the robot approaches the ball with less zigzag. If it still zigzags, use the log to decide whether the remaining cause is line false positives, HSV jumps, or controller turn gain.
