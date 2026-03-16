# Design: LAB+CLAHE Adaptive Illumination Preprocessing

**Date:** 2026-03-15
**Context:** Copa FutBot MX 2026 — open category, orange golf ball (~42mm), variable indoor lighting, RPi3 target

---

## Problem

`detect_ball()` uses fixed HSV thresholds `(5,120,120)–(20,255,255)`. Under variable lighting (shadows, venue changes, different fields) the V and S channels of the orange ball shift enough to fall outside the threshold, causing missed detections. The ball has no IR marker; detection is color+shape only.

## Solution

Apply **LAB + CLAHE(L)** normalization inside `detect_ball()` before the existing GaussianBlur → HSV → inRange pipeline. CLAHE operates on the L (lightness) channel of LAB color space, which separates illumination from color better than HSV's V channel, making the orange hue stable across lighting changes.

Apply conditionally: only when `np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD`. This skips the ~1.2ms cost when illumination is already adequate.

## Pipeline

```
detect_ball(frame)
  ├─ if np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD:
  │    BGR → LAB → split → CLAHE(L) → merge → LAB → BGR
  ├─ GaussianBlur (existing)
  ├─ BGR → HSV → inRange (existing)
  ├─ morphology open + dilate (existing)
  └─ contour → minEnclosingCircle filter (existing)

detect_ball_ai(frame)          ← unchanged, ONNX normalizes internally
```

## Changes

### `config.py` — 4 new parameters
```python
CLAHE_CLIP_LIMIT = 2.5          # contrast limit (2.0=soft, 3.0=aggressive)
CLAHE_TILE_GRID = 8             # used as tileGridSize=(N,N) — do NOT pass scalar directly
CLAHE_BRIGHTNESS_THRESHOLD = 130  # apply CLAHE when mean(frame) < this; typical indoor ~80-150
CLAHE_ENABLED = True            # set False to disable entirely at match day
```

`CLAHE_BRIGHTNESS_THRESHOLD = 130`: indoor competition fields typically have mean brightness 80–150 depending on venue lighting. The default 130 targets genuinely dark frames while skipping CLAHE on well-lit fields (mean > 130). Raise toward 200 in dark venues; lower toward 80 in bright venues.

### `detector.py` — module-level CLAHE cache + conditional apply
```python
# module level (created once)
# tileGridSize takes a (int, int) tuple — CLAHE_TILE_GRID is a scalar, expand here
_clahe = cv2.createCLAHE(
    clipLimit=CLAHE_CLIP_LIMIT,
    tileGridSize=(CLAHE_TILE_GRID, CLAHE_TILE_GRID)
)

def _apply_clahe(frame: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = _clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

def detect_ball(frame):
    if CLAHE_ENABLED and np.mean(frame) < CLAHE_BRIGHTNESS_THRESHOLD:
        frame = _apply_clahe(frame)
    blurred = cv2.GaussianBlur(frame, (11, 11), 0)
    # ... rest unchanged
```

## Performance (RPi3 estimate)

| Condition | Overhead |
|---|---|
| Bright frame (skip) | ~0.02ms (`np.mean`) |
| Dark frame (apply) | ~1.2ms |
| Existing HSV cost | ~1ms |
| Budget per frame | 33ms |

## What Does NOT Change

- `camera.py` — resize to 320×240 already implemented
- AI/ONNX path — no changes, model handles its own normalization
- `main.py`, `tracker.py`, `game_logic.py` — no changes

## Competition Tuning

Adjust via config before each match:
- `CLAHE_ENABLED = False` — kill switch, disables entirely (CLAHE never fires)
- `CLAHE_CLIP_LIMIT` — raise for darker venues (≤4.0), lower for bright fields
- `CLAHE_BRIGHTNESS_THRESHOLD` — raise toward 200 to apply CLAHE more often; lower toward 80 to apply only in very dark venues

## Testing

- Existing 16 tests must continue passing
- Add test: dark frame using BGR `(0, 40, 80)` (HSV V=80, below threshold of 120 → fails without CLAHE) → after CLAHE, orange blob detectable
- Add test: bright frame (mean ~200) → `CLAHE_BRIGHTNESS_THRESHOLD=130` → CLAHE skipped → `_apply_clahe` not called
- Add test: `CLAHE_ENABLED=False` → CLAHE never fires regardless of brightness
