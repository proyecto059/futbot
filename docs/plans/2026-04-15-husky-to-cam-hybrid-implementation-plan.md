# Husky to Cam Hybrid Controller Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the root `main.py` demo loop with a 2-wheel robot controller that migrates `husky.ino` behavior using `cam.py` vision and `test-robot/hardware.py` motor/sensor mapping, with a hybrid trigger (ultrasonic OR ball radius).

**Architecture:** Build a small finite-state machine (`SEARCH`, `CHASE`, `AVOID_MAP`) in root `main.py`. Keep camera servos fixed at center and drive only via differential wheel commands. Use helper functions for trigger evaluation, chase command generation, and map/recovery sub-steps so behavior is testable without hardware.

**Tech Stack:** Python 3.11+, OpenCV (`cv2`), existing `cam.py` pipeline, `test-robot/hardware.py` (`SerialBus`, `SharedI2CBus`, `differential`, constants), `pytest`/`unittest`-style tests.

---

### Task 1: Add pure logic helpers with TDD

**Files:**
- Modify: `main.py`
- Create: `tests/test_main_hybrid_logic.py`

**Step 1: Write the failing tests**

Add tests for pure helpers in `tests/test_main_hybrid_logic.py`:

- `hybrid_trigger(dist, ball_radius, dist_trigger, radius_trigger)`
  - returns `(triggered, cause)` where cause is one of `dist`, `radius`, `both`, `none`
- `compute_chase_wheels(cx, radius, frame_width, speed_base, rot_gain, deadband_px, radius_close)`
  - returns `(v_left, v_right)`
- `choose_search_turn(last_cx, frame_center_x)`
  - returns `left` or `right`

Example test skeleton:

```python
def test_hybrid_trigger_by_distance_only():
    triggered, cause = hybrid_trigger(120, 30, 180, 70)
    assert triggered is True
    assert cause == "dist"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_hybrid_logic.py -v`
Expected: FAIL because helper functions do not exist yet.

**Step 3: Write minimal implementation**

Implement helpers in `main.py` with deterministic math and no hardware calls.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_hybrid_logic.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_main_hybrid_logic.py main.py
git commit -m "test: add hybrid trigger and chase helper logic coverage"
```

### Task 2: Implement movement primitives and state transitions

**Files:**
- Modify: `main.py`

**Step 1: Write the failing tests**

Extend `tests/test_main_hybrid_logic.py` with transition-level pure tests (no hardware):

- `next_state(current_state, ball_visible, hybrid_active, miss_count, miss_limit)`
- `avoid_map_turn_direction(last_cx, frame_center_x)`

Example:

```python
def test_next_state_chase_to_avoid_on_hybrid_trigger():
    assert next_state("CHASE", True, True, 0, 3) == "AVOID_MAP"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_hybrid_logic.py -v`
Expected: FAIL with missing symbols.

**Step 3: Write minimal implementation**

In `main.py` add:

- state constants/enums (`SEARCH`, `CHASE`, `AVOID_MAP`)
- transition helper(s)
- wheel command helpers using `differential`
  - `move_forward(...)`
  - `move_reverse(...)`
  - `turn_left(...)`
  - `turn_right(...)`
  - `stop_robot(...)`

Keep pan/tilt fixed (`PAN_CENTER`, `TILT_CENTER`) in all bursts.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_main_hybrid_logic.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/test_main_hybrid_logic.py main.py
git commit -m "feat: add hybrid FSM transitions and two-wheel movement helpers"
```

### Task 3: Replace runtime loop in root `main.py`

**Files:**
- Modify: `main.py`

**Step 1: Write the failing behavior test (minimal, unit-level)**

Add/extend tests to validate `AVOID_MAP` sequence planner returns bounded steps and exits to `SEARCH` when no reacquire.

```python
def test_avoid_map_sequence_is_bounded():
    steps = build_avoid_map_plan(last_cx=40, frame_center_x=160, max_steps=5)
    assert len(steps) <= 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_main_hybrid_logic.py -v`
Expected: FAIL because planner is missing.

**Step 3: Write minimal implementation**

Refactor `main.py` runtime:

- Initialize `SerialBus`, `SharedI2CBus`, camera and detector from `cam.py`
- Run FSM loop:
  - `SEARCH`: chassis turning sweep (no servo tracking)
  - `CHASE`: compute differential wheel speeds from ball center offset/radius
  - `AVOID_MAP`: reverse + map turn/forward micro-steps with optional early exit to `CHASE`
- Poll ultrasonic every `ULTRA_EVERY_N_FRAMES`
- Trigger `AVOID_MAP` when hybrid trigger is active
- Add structured logs for transitions and trigger cause
- Ensure cleanup on interrupt/error

**Step 4: Run validation tests**

Run:

- `pytest tests/test_main_hybrid_logic.py -v`
- `python -m py_compile main.py`

Expected:

- Unit tests PASS
- `py_compile` succeeds

**Step 5: Commit**

```bash
git add main.py tests/test_main_hybrid_logic.py
git commit -m "feat: migrate husky behavior to hybrid cam-based two-wheel controller"
```

### Task 4: Add lightweight operator documentation

**Files:**
- Modify: `README.md`

**Step 1: Write the failing docs check**

Manual check: README currently lacks run instructions for hybrid controller.

**Step 2: Verify baseline**

Run: `python -m py_compile main.py`
Expected: still passes before docs update.

**Step 3: Write minimal documentation**

Add README section:

- What `main.py` now does (SEARCH/CHASE/AVOID_MAP)
- Hybrid trigger definition (distance OR radius)
- Run command example
- Tuning constants location in `main.py`
- Hardware dependencies (`SerialBus`, `SharedI2CBus`, camera stream)

**Step 4: Verify final sanity**

Run:

- `pytest tests/test_main_hybrid_logic.py -v`
- `python -m py_compile main.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md
git commit -m "docs: describe hybrid two-wheel cam controller usage and tuning"
```

### Task 5: End-to-end verification checklist (no commit)

**Files:**
- No file edits required.

**Step 1: Run full relevant tests**

Run:

- `pytest tests/test_main_hybrid_logic.py -v`

Expected: PASS.

**Step 2: Dry runtime startup (if hardware available)**

Run: `python main.py`
Expected: initializes bus/camera, logs state transitions, exits cleanly with Ctrl+C.

**Step 3: Field behavior checks**

Manual checks:

- No ball -> SEARCH turning sweep
- Ball seen -> CHASE
- Ultrasonic close -> AVOID_MAP
- Large radius close shot scenario -> AVOID_MAP
- Reacquire in map -> CHASE else SEARCH

**Step 4: Capture tuning notes**

Record any required constant changes for your environment (lighting, camera FOV, distance sensor noise).

**Step 5: Optional release commit**

If you changed constants during testing:

```bash
git add main.py README.md
git commit -m "tune: adjust hybrid controller thresholds for field conditions"
```