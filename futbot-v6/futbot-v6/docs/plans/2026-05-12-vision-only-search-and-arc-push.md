# Vision-Only Search And Arc Push Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the robot search intelligently with camera-only state, then chase faster when the ball is far and push continuously in an arc toward the target goal.

**Architecture:** Keep vision detection conservative and move search intelligence into `SearchOperator` plus the physical FSM. `BallGoalController` remains the pure controller for visible-ball motion, with distance-scaled speed and goal-biased arc push.

**Tech Stack:** Python, pytest, existing chase/vision/motor operators.

---

### Task 1: Add Pure Search Behavior Tests

**Files:**
- Modify: `tests/test_search_operator.py`
- Modify: `src/chase/search_operator.py`

**Steps:**
- Add tests for local reacquire: last seen right turns/searches right, last seen left searches left, centered far ball advances briefly, expired/empty memory falls back to scan.
- Run `pytest -q tests/test_search_operator.py` and verify failures.

### Task 2: Implement SearchOperator Memory Steps

**Files:**
- Modify: `src/chase/search_operator.py`

**Steps:**
- Add `local_reacquire_step(last_cx, last_r, frame_w)`.
- Add `field_search_step(step_index)` with scan/forward/alternating turns.
- Keep old `recover_step` and `map_step` wrappers for compatibility.
- Run `pytest -q tests/test_search_operator.py`.

### Task 3: Add Controller Speed/Push Tests

**Files:**
- Modify: `tests/test_ball_goal_controller.py`
- Modify: `src/chase/ball_goal_controller.py`

**Steps:**
- Add tests: far centered ball is faster than near centered ball; far side ball still advances in an arc; close ball with goal right/left pushes with goal-biased turn.
- Run focused tests and verify failures for speed curve if needed.

### Task 4: Tune BallGoalController

**Files:**
- Modify: `src/chase/ball_goal_controller.py`

**Steps:**
- Increase far speed and keep near speed lower.
- Make speed decrease continuously as radius grows.
- Preserve min forward wheel motion during arcs.
- Keep `PUSH` goal-biased and continuous.
- Run `pytest -q tests/test_ball_goal_controller.py`.

### Task 5: Remove Ultrasonic And Update FSM Search States

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Steps:**
- Remove `UltrasonicService` import, construction, polling, and `AVOID` transitions.
- Add `LOCAL_REACQUIRE` and `FIELD_SEARCH` state names.
- Route `PREDICT` timeout to `LOCAL_REACQUIRE` if memory is fresh, otherwise `FIELD_SEARCH`.
- Use `SearchOperator.local_reacquire_step()` and `field_search_step()` for motion.
- Keep line safety and push commit.
- Run `python -m py_compile scripts/test_chase_dynamic.py`.

### Task 6: Verify And Sync

**Files:**
- Runtime sync to Raspberry Pi only after tests pass.

**Steps:**
- Run `pytest -q tests/test_search_operator.py tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py`.
- Run `python -m py_compile scripts/test_chase_dynamic.py src/chase/search_operator.py src/chase/ball_goal_controller.py`.
- Sync modified files to Raspberry.
- Run a short motor-free vision check first.
- Run a short physical trial only when requested.
