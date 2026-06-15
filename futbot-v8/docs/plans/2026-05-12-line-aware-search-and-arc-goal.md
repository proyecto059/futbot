# Line-Aware Search And Arc Goal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the robot avoid white lines without freezing, improve ball search, and delay push until ball-goal geometry supports a scoring arc.

**Architecture:** Keep safety decisions in the FSM/helper layer, search motion in `SearchOperator`, and scoring motion in `BallGoalController`. Add small pure helpers/tests first, then wire them into `scripts/test_chase_dynamic.py`.

**Tech Stack:** Python, pytest, existing vision/chase/motor operators.

---

### Task 1: Add Line-Cooldown Helper Tests

**Files:**
- Modify: `tests/test_visual_servo_controller.py`
- Modify: `src/chase/visual_servo_controller.py`

**Steps:**
- Add a test showing active line detection without visible ball still requests a hold.
- Add a test showing line cooldown without visible ball does not request a full hold.
- Run: `pytest -q tests/test_visual_servo_controller.py::test_hold_without_ball_near_active_line tests/test_visual_servo_controller.py::test_line_cooldown_allows_safe_search_motion`
- Expected before implementation: the cooldown test fails.
- Change `should_hold_without_ball_near_line()` so it returns true only for active line detection without a visible ball, not cooldown alone.
- Run: `pytest -q tests/test_visual_servo_controller.py`

### Task 2: Add Line-Aware Search Tests

**Files:**
- Modify: `tests/test_search_operator.py`
- Modify: `src/chase/search_operator.py`

**Steps:**
- Add tests for a line on the left: field search should turn/arc right and avoid forward-only motion.
- Add tests for a line on the right: field search should turn/arc left and avoid forward-only motion.
- Add tests for line cooldown with unknown line center: scan in place instead of forward.
- Run: `pytest -q tests/test_search_operator.py` and verify new tests fail.
- Add `line_aware_field_search_step(step_index, line_cx, frame_w)`.
- Keep existing `field_search_step()` behavior unchanged when no line cooldown is active.
- Run: `pytest -q tests/test_search_operator.py`.

### Task 3: Add Ball-Goal Alignment Tests

**Files:**
- Modify: `tests/test_ball_goal_controller.py`
- Modify: `src/chase/ball_goal_controller.py`

**Steps:**
- Add test: close ball left and goal right stays `CHASE`, keeps forward motion, and turns in a goal-biased arc instead of `PUSH`.
- Add test: close ball right and goal left stays `CHASE`, keeps forward motion, and turns in a goal-biased arc instead of `PUSH`.
- Add test: close ball aligned with goal still enters `PUSH`.
- Run: `pytest -q tests/test_ball_goal_controller.py` and verify the misaligned close-ball tests fail.
- Add a `push_alignment_dx` threshold to `BallGoalController`.
- Gate goal push on `abs(ball_cx - goal_cx) <= push_alignment_dx`.
- For close misaligned balls, blend turn toward goal while staying in `CHASE`.
- Run: `pytest -q tests/test_ball_goal_controller.py`.

### Task 4: Wire Line-Aware Search Into Physical FSM

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Steps:**
- Track `last_line_cx` when line is detected.
- After line escape, set `state = FIELD_SEARCH` rather than `LOCAL_REACQUIRE` unless recent ball memory is still fresh.
- Replace the cooldown full stop with safe search motion by relying on the updated hold helper.
- In `FIELD_SEARCH`, call `line_aware_field_search_step()` while `line_cooldown > 0`; otherwise call `field_search_step()`.
- Log line-aware search steps clearly, e.g. `FIELD_SEARCH line_cooldown paso=... dir=...`.
- Run: `python -m py_compile scripts/test_chase_dynamic.py src/chase/search_operator.py src/chase/ball_goal_controller.py src/chase/visual_servo_controller.py`.

### Task 5: Focused Verification And Raspberry Trial

**Files:**
- Runtime only.

**Steps:**
- Run: `pytest -q tests/test_search_operator.py tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py`.
- Run: `python -m py_compile scripts/test_chase_dynamic.py src/chase/search_operator.py src/chase/ball_goal_controller.py src/chase/visual_servo_controller.py`.
- Sync touched files to Raspberry Pi with `rsync -avR`.
- Stop API: `ssh raspi@raspi.local 'systemctl --user stop futbot-api.service'`.
- Run a short physical trial with `320x240`, `BALL_CONFIRM_FRAMES=3`, `PUSH_CONFIRM_FRAMES=5`, and `SEARCH_MAX_INITIAL_BALL_RADIUS=45`.
- Send explicit stop with `motors.operators.burst_operator.BurstOperator` and `motors.utils.motor_constants` imports.
- Copy log locally.
- Check for: no repeated stationary `LINE hold` loop, search movement during line cooldown, `CHASE` for misaligned close ball, and `PUSH commit` only after alignment.
