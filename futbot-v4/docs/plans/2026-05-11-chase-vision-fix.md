# Chase Vision Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix continuous ball chasing, improve ball/goal/white-line vision, and verify the robot follows the ball without crossing white lines.

**Architecture:** Keep the existing FSM and operators. Restore the existing `VisualServoController` as the single TRACK controller, then improve HSV-derived goal and line operators with minimal OpenCV filtering. Avoid broad rewrites and do not change the validated motor mapping.

**Tech Stack:** Python 3.11+, OpenCV, NumPy, pytest, Raspberry Pi 5 over SSH, `uv run python`.

**Constraint:** Do not create git commits.

---

### Task 1: Add Regression Tests for Wheel Decomposition

**Files:**
- Modify: `tests/test_visual_servo_controller.py`
- Reference: `src/chase/visual_servo_controller.py`

**Step 1: Write failing tests**

Add tests that encode the repo's signed wheel convention:

```python
def test_signed_wheels_decompose_forward_and_turn_right():
    v_left = 100.0
    v_right = -60.0

    forward = (v_left - v_right) * 0.5
    turn = (v_left + v_right) * 0.5

    assert forward == 80.0
    assert turn == 20.0


def test_controller_turns_right_for_ball_on_right_with_forward_motion():
    controller = build_controller()

    v_left, v_right = controller.compute(cx=220.0, r=42.0, dt=0.05)
    forward = (v_left - v_right) * 0.5
    turn = (v_left + v_right) * 0.5

    assert forward > 0.0
    assert turn > 0.0
```

**Step 2: Run tests**

Run: `pytest tests/test_visual_servo_controller.py -v`

Expected: pass or expose current mismatch.

---

### Task 2: Restore Continuous TRACK Control

**Files:**
- Modify: `scripts/test_chase_dynamic.py:329-424`

**Step 1: Replace inline TRACK wheel math**

Use `controller.compute(cx_filtered, r_eff, dt)` again, then decompose using:

```python
v_cmd = (vL - vR) * 0.5
turn_cmd = (vL + vR) * 0.5
```

Apply cache scaling and rate limiting to `v_cmd`/`turn_cmd`, then reconstruct:

```python
vL = v_cmd + turn_cmd
vR = -(v_cmd - turn_cmd)
```

**Step 2: Keep kick behavior minimal**

If the ball is close and aligned, push straight with `(150, -150)`. If a target goal is visible while close, add only a small correction toward the goal before pushing.

**Step 3: Fix diagnostics**

Print forward and turn with the same decomposition so live logs match actual motion.

**Step 4: Run relevant tests**

Run: `pytest tests/test_visual_servo_controller.py -v`

Expected: pass.

---

### Task 3: Improve White-Line Detection

**Files:**
- Modify: `src/vision/operators/white_line_detection_operator.py`
- Modify: `src/vision/utils/vision_constants.py`
- Test: create `tests/test_vision_operators.py`

**Step 1: Add tests**

Create synthetic frames:

```python
def test_white_line_detects_bottom_white_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[205:225, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is True
    assert 140 <= line.cx <= 180


def test_white_line_ignores_top_white_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[20:40, 40:280] = (255, 255, 255)

    line = WhiteLineDetectionOperator().detect(frame)

    assert line.detected is False
```

**Step 2: Implement minimal filter**

Use bottom ROI, HSV white mask, morphological close/open, and detect if white pixels exceed an absolute minimum and a ROI ratio minimum.

**Step 3: Run tests**

Run: `pytest tests/test_vision_operators.py -v`

Expected: pass.

---

### Task 4: Improve Goal Detection

**Files:**
- Modify: `src/vision/operators/goal_color_detection_operator.py`
- Modify: `src/vision/utils/vision_constants.py`
- Test: `tests/test_vision_operators.py`

**Step 1: Add tests**

Use synthetic blue/yellow rectangles plus small noise blobs. Assert centroid follows the large component, not all raw pixels.

**Step 2: Implement connected-component filter**

Clean mask with morphology, find external contours, keep components above minimum area, and calculate centroid from the filtered mask.

**Step 3: Run tests**

Run: `pytest tests/test_vision_operators.py -v`

Expected: pass.

---

### Task 5: Local Verification

**Files:**
- None unless tests fail.

**Step 1: Run all tests**

Run: `pytest -v`

Expected: all tests pass.

**Step 2: Check syntax for robot script**

Run: `python -m py_compile scripts/test_chase_dynamic.py`

Expected: no output.

---

### Task 6: Raspberry Verification

**Files:**
- None unless live evidence reveals a mismatch.

**Step 1: Copy/sync code if needed**

Use the repo's existing deployment/sync process if available, otherwise inspect before changing remote files.

**Step 2: Sample live vision**

Run a short `PYTHONPATH=src /home/raspi/.local/bin/uv run python -c ...` script over SSH to confirm ball, target goal, and line fields.

Expected with current setup: ball around right side (`cx > 160`) and blue goal visible if attacking blue.

**Step 3: Run short motion test**

Run `scripts/test_chase_dynamic.py` briefly and ask the human observer whether it turns toward the ball on the right and avoids white lines.

**Step 4: Iterate only if evidence contradicts expected behavior**

Return to root-cause investigation before further fixes.
