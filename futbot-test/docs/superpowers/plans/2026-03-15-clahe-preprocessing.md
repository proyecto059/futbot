# LAB+CLAHE Adaptive Illumination Preprocessing — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add adaptive LAB+CLAHE illumination normalization inside `detect_ball()` so the orange ball is reliably detected under variable lighting conditions at Copa FutBot MX 2026.

**Architecture:** CLAHE is applied on the L channel of LAB color space (not HSV V) before the existing GaussianBlur → HSV → inRange pipeline. It fires only when `np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD` AND `CLAHE_ENABLED=True`. The CLAHE object is cached at module level to avoid per-frame allocation. The AI/ONNX path is untouched.

**Tech Stack:** OpenCV (`cv2.createCLAHE`, `cv2.COLOR_BGR2LAB`), NumPy, pytest

---

## Chunk 1: Config + Failing Tests

### Task 1: Add CLAHE parameters to config.py

**Files:**
- Modify: `futbot-test/config.py:12-16`

- [ ] **Step 1: Add 4 CLAHE parameters after the HSV section**

In `config.py`, after line 16 (`MIN_BALL_RADIUS = 10`), insert:

```python
# Adaptive illumination (LAB+CLAHE) — applied inside detect_ball()
CLAHE_ENABLED = True          # kill switch: set False to disable entirely
CLAHE_CLIP_LIMIT = 2.5        # contrast limit (2.0=soft, 3.0=aggressive, 4.0=max)
CLAHE_TILE_GRID = 8           # used as tileGridSize=(N,N) — do NOT pass scalar directly
CLAHE_BRIGHTNESS_THRESHOLD = 130  # apply CLAHE when np.mean(frame) < this
```

- [ ] **Step 2: Verify config loads without error**

Run:
```bash
uv run python -c "from config import CLAHE_ENABLED, CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, CLAHE_BRIGHTNESS_THRESHOLD; print(CLAHE_ENABLED, CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, CLAHE_BRIGHTNESS_THRESHOLD)"
```
Expected output: `True 2.5 8 130`

---

### Task 2: Write failing tests for CLAHE behavior

**Files:**
- Modify: `futbot-test/tests/test_detector.py`

- [ ] **Step 1: Add import for `unittest.mock` and `detector` module at top of test file**

After the existing imports in `tests/test_detector.py`:
```python
from unittest.mock import patch
import detector
```

- [ ] **Step 2: Add 3 new test functions at the end of `tests/test_detector.py`**

```python
# ── CLAHE preprocessing tests ──────────────────────────────────────────────

def test_apply_clahe_increases_brightness_of_dark_frame():
    """_apply_clahe should raise mean brightness of a dark frame.

    Uses BGR (0, 50, 100) — channels differ so the LAB L histogram is
    non-flat and CLAHE can actually redistribute it. A fully gray frame
    (e.g. (30,30,30)) also works, but a uniform single-channel frame would not.
    """
    from detector import _apply_clahe
    # Dark orange-tinted frame: mean ~50, non-flat LAB L histogram
    dark_frame = np.full((240, 320, 3), (0, 50, 100), dtype=np.uint8)
    mean_before = float(np.mean(dark_frame))
    result = _apply_clahe(dark_frame)
    mean_after = float(np.mean(result))
    assert mean_after > mean_before


def test_detect_ball_applies_clahe_when_frame_is_dark():
    """detect_ball should call _apply_clahe when mean(frame) < threshold."""
    # Solid dark frame — mean ~30, well below CLAHE_BRIGHTNESS_THRESHOLD=130
    dark_frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
        detector.detect_ball(dark_frame)
        mock_clahe.assert_called_once()


def test_detect_ball_skips_clahe_when_frame_is_bright():
    """detect_ball should NOT call _apply_clahe when mean(frame) >= threshold."""
    # Bright frame — mean ~200, above CLAHE_BRIGHTNESS_THRESHOLD=130
    bright_frame = np.full((240, 320, 3), 200, dtype=np.uint8)
    with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
        detector.detect_ball(bright_frame)
        mock_clahe.assert_not_called()


def test_detect_ball_respects_clahe_enabled_flag():
    """When CLAHE_ENABLED=False, _apply_clahe must never be called."""
    dark_frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    with patch.object(detector, 'CLAHE_ENABLED', False):
        with patch.object(detector, '_apply_clahe', wraps=detector._apply_clahe) as mock_clahe:
            detector.detect_ball(dark_frame)
            mock_clahe.assert_not_called()
```

- [ ] **Step 3: Run tests to confirm they FAIL (implementation not done yet)**

Run:
```bash
uv run --extra dev python -m pytest tests/test_detector.py -v -k "clahe"
```
Expected: `4 failed` — test 1 fails with `ImportError: cannot import name '_apply_clahe'`; tests 2–4 fail with `AttributeError: <module 'detector'> does not have attribute '_apply_clahe'` (evaluated eagerly by `wraps=detector._apply_clahe` when the function doesn't exist yet)

---

## Chunk 2: Implementation

### Task 3: Implement CLAHE in detector.py

**Files:**
- Modify: `futbot-test/detector.py:4-9` (imports)
- Modify: `futbot-test/detector.py:11-16` (module-level cache)
- Modify: `futbot-test/detector.py:19-45` (detect_ball function)

- [ ] **Step 1: Extend imports in `detector.py`**

Change the existing import line (line 4-9) from:
```python
from config import (
    HSV_LOWER, HSV_UPPER, MIN_CONTOUR_AREA, MIN_BALL_RADIUS,
    MORPH_OPEN_SIZE, MORPH_DILATE_SIZE, ROI_SIZE, ROI_PADDING,
    FRAME_WIDTH, FRAME_HEIGHT,
    KALMAN_PROCESS_NOISE, KALMAN_MEASUREMENT_NOISE,
)
```
To:
```python
from config import (
    HSV_LOWER, HSV_UPPER, MIN_CONTOUR_AREA, MIN_BALL_RADIUS,
    MORPH_OPEN_SIZE, MORPH_DILATE_SIZE, ROI_SIZE, ROI_PADDING,
    FRAME_WIDTH, FRAME_HEIGHT,
    KALMAN_PROCESS_NOISE, KALMAN_MEASUREMENT_NOISE,
    CLAHE_ENABLED, CLAHE_CLIP_LIMIT, CLAHE_TILE_GRID, CLAHE_BRIGHTNESS_THRESHOLD,
)
```

- [ ] **Step 2: Add `_clahe` cache after the existing morphology kernels (after line 16)**

After `_kernel_dilate = cv2.getStructuringElement(...)`, add:
```python
# CLAHE object — created once at module load, reused every frame
_clahe = cv2.createCLAHE(
    clipLimit=CLAHE_CLIP_LIMIT,
    tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID),  # must be (N,N) tuple
)
```

- [ ] **Step 3: Add `_apply_clahe()` helper before `detect_ball()`**

Insert before `def detect_ball(...)`:
```python
def _apply_clahe(frame: np.ndarray) -> np.ndarray:
    """Normalize illumination via CLAHE on L channel of LAB color space."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
```

- [ ] **Step 4: Add conditional CLAHE call at the start of `detect_ball()`**

In `detect_ball()`, change:
```python
    blurred = cv2.GaussianBlur(frame, (11, 11), 0)
```
To:
```python
    if CLAHE_ENABLED and np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD:
        frame = _apply_clahe(frame)
    blurred = cv2.GaussianBlur(frame, (11, 11), 0)
```

- [ ] **Step 5: Run the 4 new CLAHE tests — all must PASS**

Run:
```bash
uv run --extra dev python -m pytest tests/test_detector.py -v -k "clahe"
```
Expected: `4 passed`

- [ ] **Step 6: Run the full test suite — all 20 tests must PASS**

Run:
```bash
uv run --extra dev python -m pytest tests/ -v
```
Expected: `20 passed` (16 existing across test_camera_mock.py×1, test_detector.py×6, test_game_logic.py×5, test_pid.py×4 — plus 4 new CLAHE tests)

- [ ] **Step 7: Commit**

```bash
git add config.py detector.py tests/test_detector.py
git commit -m "feat: add LAB+CLAHE adaptive illumination preprocessing in detect_ball()"
```

---

## Verification

After all tasks complete, confirm:

```bash
uv run --extra dev python -m pytest tests/ -v
# Expected: 20 passed

# Smoke-check CLAHE fires on a dark synthetic frame:
uv run python -c "
import numpy as np
import detector
dark = np.full((240, 320, 3), 30, dtype=np.uint8)
bright = np.full((240, 320, 3), 200, dtype=np.uint8)
print('mean dark:', np.mean(dark), '→ CLAHE fires:', np.mean(dark) < detector.CLAHE_BRIGHTNESS_THRESHOLD)
print('mean bright:', np.mean(bright), '→ CLAHE fires:', np.mean(bright) < detector.CLAHE_BRIGHTNESS_THRESHOLD)
"
# Expected:
# mean dark: 30.0 → CLAHE fires: True
# mean bright: 200.0 → CLAHE fires: False
```
