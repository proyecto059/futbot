# Blue Goal Runtime Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the blue-goal dynamic chase run ignore tiny ball noise, push at realistic observed ball sizes, and avoid false goal celebrations.

**Architecture:** Keep changes in pure controller/helpers where possible, then wire the FSM to those helpers. The controller owns push thresholds, `attack_geometry` owns score gating, and `test_chase_dynamic.py` owns runtime defaults and push-state context. No motor behavior is run until local tests and compile checks pass.

**Tech Stack:** Python, pytest, Raspberry Pi `uv`, serial motor script.

---

### Task 1: Controller Push Threshold

**Files:**
- Modify: `src/chase/ball_goal_controller.py`
- Test: `tests/test_ball_goal_controller.py`

**Step 1: Write failing test**

Add a test for a log-like aligned blue-goal case: ball `cx=265.6`, `r=32.4`, goal `cx=280.0`. Expect `PUSH` and positive forward motion.

**Step 2: Run red test**

Run: `pytest -q tests/test_ball_goal_controller.py::test_log_aligned_blue_goal_pushes_at_observed_radius`
Expected: FAIL because default `goal_push_radius=45` keeps this as `CHASE`.

**Step 3: Implement minimal threshold change**

Set `goal_push_radius` default to `30.0`.

**Step 4: Run controller tests**

Run: `pytest -q tests/test_ball_goal_controller.py`
Expected: PASS.

### Task 2: Score Gating

**Files:**
- Modify: `src/chase/attack_geometry.py`
- Modify: `scripts/test_chase_dynamic.py`
- Test: `tests/test_attack_geometry.py`

**Step 1: Write failing tests**

Add tests for a helper `scored_goal_color_after_push(ball, goals, target_key, push_until, now)`:
- returns `None` when the ball overlaps the target goal but no push is active/recent;
- returns the target color when overlap exists and `push_until >= now`.

**Step 2: Run red tests**

Run: `pytest -q tests/test_attack_geometry.py::test_scored_goal_requires_active_push_context tests/test_attack_geometry.py::test_scored_goal_accepts_active_push_context`
Expected: FAIL because helper does not exist.

**Step 3: Implement helper**

Add `scored_goal_color_after_push()` that checks `push_until >= now` before delegating to `scored_goal_color()`.

**Step 4: Wire FSM**

Import the new helper in `scripts/test_chase_dynamic.py` and use it instead of `scored_goal_color(ball, goals_now, target_key)`.

**Step 5: Run tests**

Run: `pytest -q tests/test_attack_geometry.py`
Expected: PASS.

### Task 3: Runtime Ball Noise Default

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Step 1: Change default**

Change `BALL_VISIBLE_MIN_RADIUS` env default from `4.0` to `8.0`.

**Step 2: Verify syntax**

Run: `/usr/bin/python -m py_compile scripts/test_chase_dynamic.py`
Expected: PASS.

### Task 4: Goal Memory Side Flip Rejection

**Files:**
- Modify: `src/chase/visual_servo_controller.py`
- Test: `tests/test_visual_servo_controller.py`

**Step 1: Write failing tests**

Add a test where `last_cx=288`, `current_cx=31`, `last_ts=10.0`, `now=11.5`, `frame_width=320`. Expect memory to keep `288` and reject the opposite-side flip while memory is still fresh.

**Step 2: Run red test**

Run: `pytest -q tests/test_visual_servo_controller.py::test_goal_memory_rejects_fresh_opposite_side_flip`
Expected: FAIL if the current max-jump logic accepts after enough elapsed time.

**Step 3: Implement minimal side flip guard**

In `update_goal_memory()`, before max-jump acceptance, reject if both centers are on opposite sides of frame center and memory age is within `max_age_s`.

**Step 4: Run visual servo tests**

Run: `pytest -q tests/test_visual_servo_controller.py`
Expected: PASS.

### Task 5: Verification and Raspberry Trial

**Files:**
- No code edits unless verification fails.

**Step 1: Run focused local verification**

Run: `pytest -q tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_attack_geometry.py tests/test_capture_attack_geometry.py tests/test_vision_operators.py`
Expected: PASS.

**Step 2: Compile changed Python files**

Run: `/usr/bin/python -m py_compile src/chase/ball_goal_controller.py src/chase/visual_servo_controller.py src/chase/attack_geometry.py scripts/test_chase_dynamic.py scripts/capture_attack_geometry.py`
Expected: PASS.

**Step 3: Sync changed files to Raspberry**

Use `rsync -avR` for touched files to `raspi@raspi.local:~/futbot-v2/`.

**Step 4: Stop API service**

Run over SSH: `systemctl --user stop futbot-api.service || true`.

**Step 5: Run bounded trial**

Run over SSH from `~/futbot-v2`: `ATTACK_BLUE=1 timeout -s INT 25s /home/raspi/.local/bin/uv run scripts/test_chase_dynamic.py`.

**Step 6: Send explicit stop**

Run a short SSH Python command that opens `/dev/ttyAMA0` at `1_000_000` and sends zero motor output via `BurstOperator`.

### Notes

- Do not commit unless explicitly requested.
- Do not use worktrees.
- The trial intentionally uses a timeout so the robot cannot run indefinitely.
