# Attack Geometry Goal Celebration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Capture annotated ball-goal geometry, align dynamically before push, detect goals in either color goal, and celebrate scored goals with a 360 spin then stop.

**Architecture:** Keep geometry in pure chase helpers, keep visual goal bbox metadata in the vision DTO/operator, and keep physical motor behavior in the FSM. Build capture tooling first so every physical change can be inspected visually.

**Tech Stack:** Python, OpenCV, pytest, existing vision/chase/motor operators.

---

### Task 1: One-Shot Attack Geometry Capture

**Files:**
- Create: `scripts/capture_attack_geometry.py`
- Test: add focused tests if helper functions are extracted.

**Steps:**
- Create a script that starts `HybridVisionService`, captures a few frames, and saves the latest raw frame plus snapshot JSON.
- Add annotation code for ball circle, goal center lines, approximate goal masks/bboxes, and ball-to-target-goal vector.
- Save under `output/attack_geometry_<timestamp>/raw.jpg`, `annotated.jpg`, and `snapshot.json`.
- Run on Raspberry before motor trials.

### Task 2: Goal Bounding Box Metadata

**Files:**
- Modify: `src/vision/dto/goals_dto.py`
- Modify: `src/vision/operators/goal_color_detection_operator.py`
- Modify: `tests/test_vision_operators.py`

**Steps:**
- Add failing tests that blue/yellow detections include bbox and cy.
- Add optional fields `blue_bbox`, `yellow_bbox`, `blue_cy`, `yellow_cy`, `blue_pixels`, `yellow_pixels`.
- Compute bboxes from final cleaned masks.
- Verify existing goal tests still pass.

### Task 3: Pure Attack Geometry Helpers

**Files:**
- Create: `src/chase/attack_geometry.py`
- Create/modify: `tests/test_attack_geometry.py`

**Steps:**
- Add tests for `is_ball_inside_goal(ball, goal_bbox)` for blue and yellow.
- Add tests for push readiness when ball and goal are aligned vs misaligned.
- Implement pure helpers with no camera/motor dependencies.

### Task 4: Controller Alignment Mode

**Files:**
- Modify: `src/chase/ball_goal_controller.py`
- Modify: `tests/test_ball_goal_controller.py`

**Steps:**
- Add tests requiring `ALIGN_ARC` or `CHASE` while ball and goal are not push-ready.
- Keep both wheels moving forward during alignment arcs.
- Allow `PUSH` only when pure geometry helper says push-ready.

### Task 5: Goal Scored Celebration FSM

**Files:**
- Modify: `scripts/test_chase_dynamic.py`
- Test: pure helper tests in `tests/test_attack_geometry.py`; compile physical script.

**Steps:**
- Add `CELEBRATE_360` state.
- Track `goal_scored_streak` for either blue or yellow bbox overlap.
- On confirmed goal, spin in place for `SPIN_360_MS` and then send stop forever.
- Log `GOAL scored color=...` and `CELEBRATE_360` progress.

### Task 6: Verification And Physical Trial

**Files:**
- Runtime only.

**Steps:**
- Run focused tests and `py_compile`.
- Sync touched files to Raspberry.
- Capture annotated frame first and inspect `output/attack_geometry_*`.
- Only after capture looks correct, run a short motorized trial.
- Send explicit stop after every trial.
