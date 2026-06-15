# ALIGN_ARC Behind-Ball Route Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `ALIGN_ARC` use the same behind-ball route geometry shown in attack geometry overlays.

**Architecture:** Keep geometry pure and reuse `behind_ball_point()` plus `route_curve_points()` from `src/chase/attack_geometry.py`. Extend `BallGoalController.compute()` with optional `ball_cy`, `goal_cy`, and `frame_height`; when all are present, aim at an early route-curve lookahead point and move slowly instead of pivoting in place. Keep the old pivot-only behavior as the fallback when Y geometry is unavailable.

**Tech Stack:** Python, pytest, OpenCV only in capture/runtime scripts.

---

### Task 1: Route-Driven Controller Tests

**Files:**
- Modify: `tests/test_ball_goal_controller.py`

**Step 1: Write the failing saved-capture route test**

Add a test using ball `(96, 85)`, goal `(14.8, 72.8)`, and frame `320x240`. Expect `ALIGN_ARC`, positive forward speed, and positive turn because the current overlay curve initially bows right before reaching the behind point.

**Step 2: Write the fallback safety test**

Add a test that omits `ball_cy`/`goal_cy`. Expect the existing conservative pivot behavior: `ALIGN_ARC` and no forward motion.

**Step 3: Run tests to verify the new route test fails**

Run: `pytest -q tests/test_ball_goal_controller.py`

Expected: FAIL because `compute()` does not accept route geometry inputs yet.

### Task 2: Minimal Controller Integration

**Files:**
- Modify: `src/chase/ball_goal_controller.py`

**Step 1: Import geometry helpers**

Import `behind_ball_point` and `route_curve_points` from `chase.attack_geometry`.

**Step 2: Extend constructor defaults**

Add conservative route parameters:
- `frame_height=240.0`
- `align_arc_route_speed=55.0`
- `align_arc_route_bend=55.0`
- `align_arc_route_lookahead=0.28`

Keep `align_arc_speed=0.0` as fallback pivot speed.

**Step 3: Extend `compute()` inputs**

Add keyword-only optional arguments:
- `ball_cy: float | None = None`
- `goal_cy: float | None = None`
- `frame_height: float | None = None`

Existing callers continue to work unchanged.

**Step 4: Use route lookahead inside `ALIGN_ARC`**

When `ball_cy` and `goal_cy` are present:
- compute `behind = behind_ball_point(ball_cx, ball_cy, goal_cx, goal_cy)`
- compute curve from `(center_x, frame_height - 1)` to `behind`
- select a lookahead point from the early curve
- derive `align_theta` from lookahead X relative to center
- command `align_arc_route_speed` with `keep_forward=True`

When geometry is missing, preserve the current pivot-only logic.

**Step 5: Run controller tests**

Run: `pytest -q tests/test_ball_goal_controller.py`

Expected: PASS.

### Task 3: Runtime Wiring

**Files:**
- Modify: `scripts/test_chase_dynamic.py`

**Step 1: Track stable goal Y**

Add `last_goal_cy = None`. Read `target_goal_cy_raw = goals_now.get(f"{target_key}_cy")`. Update `last_goal_cy` only when the goal memory accepts the current goal or when no previous Y is available for a remembered goal.

**Step 2: Pass Y geometry to the controller**

Read `cy_raw = ball.get("cy")` in the TRACK block and pass `ball_cy=cy_raw`, `goal_cy=last_goal_cy`, and `frame_height=vision.frame_height` to `controller.compute()`.

**Step 3: Verify syntax and focused behavior**

Run: `/usr/bin/python -m py_compile src/chase/ball_goal_controller.py scripts/test_chase_dynamic.py`

Expected: PASS.

Run: `pytest -q tests/test_ball_goal_controller.py tests/test_attack_geometry.py`

Expected: PASS.

### Notes

- Do not commit unless explicitly requested.
- Do not run motors as part of this plan.
- Keep `ALIGN_ARC` fallback conservative when route geometry is missing.
