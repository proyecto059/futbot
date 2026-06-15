# Behind-Ball Route Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Visualize and use an explicit behind-ball route so the robot aims to position behind the ball before pushing toward the target goal.

**Architecture:** Add pure geometry helpers in `src/chase/attack_geometry.py`, then use those helpers in `scripts/capture_attack_geometry.py` to draw the intended route on saved captures. Keep controller changes small and test-driven: first make route visualization correct, then use the same geometry to gate aggressive chase later.

**Tech Stack:** Python, OpenCV, pytest.

---

### Task 1: Behind-Ball Geometry

**Files:**
- Modify: `src/chase/attack_geometry.py`
- Test: `tests/test_attack_geometry.py`

**Step 1: Write failing tests**

Add tests for `behind_ball_point()` and `is_robot_near_behind_point()` using saved capture geometry: ball `(96, 85)`, goal `(15, 73)`, expected behind point around `(140, 92)`.

**Step 2: Run tests**

Run: `pytest -q tests/test_attack_geometry.py`

Expected: FAIL because helpers do not exist.

**Step 3: Implement helpers**

Add pure geometry functions with no OpenCV dependency:
- `behind_ball_point(ball_cx, ball_cy, goal_cx, goal_cy, distance=45.0)`
- `is_robot_near_behind_point(robot_cx, robot_cy, behind_x, behind_y, tolerance=24.0)`

**Step 4: Verify**

Run: `pytest -q tests/test_attack_geometry.py`

Expected: PASS.

### Task 2: Route Overlay

**Files:**
- Modify: `scripts/capture_attack_geometry.py`
- Test: `tests/test_capture_attack_geometry.py`

**Step 1: Write failing test**

Add an overlay test that checks the behind-ball target is drawn to the right/down of the ball for the saved-capture geometry.

**Step 2: Run test**

Run: `pytest -q tests/test_capture_attack_geometry.py`

Expected: FAIL because overlay does not draw the behind target.

**Step 3: Implement overlay**

Draw:
- green arrow: ball to goal,
- magenta circle: behind-ball target,
- cyan arrow: image center to behind target.

**Step 4: Verify**

Run: `pytest -q tests/test_capture_attack_geometry.py`

Expected: PASS.

### Task 3: Saved Capture Verification

**Files:**
- No code changes unless tests fail.

**Step 1: Run focused suite**

Run: `pytest -q tests/test_attack_geometry.py tests/test_capture_attack_geometry.py tests/test_ball_goal_controller.py tests/test_visual_servo_controller.py tests/test_vision_operators.py`

Expected: PASS.

**Step 2: Regenerate annotated image from saved raw capture**

Use a local one-off Python command to call `annotate_attack_geometry()` on `output/attack_geometry_20260513_222121/raw.jpg` and `snapshot.json`, writing `output/attack_geometry_20260513_222121/route_annotated.jpg`.

**Step 3: Inspect `route_annotated.jpg`**

Expected: behind target appears to the right/down of the ball, and route arrow points toward it.

### Notes

- Do not commit unless explicitly requested.
- Do not run motors for this plan.
