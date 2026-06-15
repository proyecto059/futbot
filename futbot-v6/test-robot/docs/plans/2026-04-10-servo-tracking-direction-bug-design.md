# Servo Tracking Direction Bugfix Design

## Context

The robot loses the ball during `--test-servo` because servo motion is sometimes opposite to the ball position in the image. Logs show that after detection, `pan`/`tilt` can move to extremes and detection is quickly lost, followed by immediate recentering.

Observed pattern:
- Ball detected at high/right image zones -> target servo commands continue moving away from stable tracking
- Detection drops -> loop recenters immediately (`Sin pelota - centrando`)
- Reacquisition becomes unstable because camera movement is too aggressive after short detection gaps

## Goal

Fix servo direction and recovery behavior so camera tracking remains stable in both:
- `--test-servo` (`test_servos.py`)
- Main state machine (`SEARCHING` / `APPROACHING` in `main.py`)

## Root Cause Hypothesis

Primary cause:
- Coordinate-to-servo mapping does not account for physical mount direction (pan and/or tilt inversion).

Secondary cause:
- Immediate recenter on first missed frame amplifies tracking loss.

## Approaches Considered

1. Axis calibration + hold-before-recenter (recommended)
   - Add explicit axis inversion config for pan/tilt.
   - Apply identical mapping logic in both servo test and main flow.
   - Add short hold window before recenter when detection is temporarily lost.

2. Hard invert values directly in-place
   - Fastest but brittle and harder to maintain.
   - Easy to drift between `test_servos.py` and `main.py`.

3. Full delta/PID-like controller
   - Most robust long-term but higher complexity and tuning cost.
   - Not required for this bugfix scope.

Chosen: Approach 1.

## Design

### 1) Shared Servo Mapping

Create a single helper for camera pixel -> servo angle mapping, with axis inversion controls.

Configuration (in shared module):
- `SERVO_PAN_INVERTED: bool`
- `SERVO_TILT_INVERTED: bool`

Mapping behavior:
- Compute normalized x/y from frame dimensions.
- Convert to 0..180 target angles.
- If inversion is enabled for an axis, map to `180 - value` for that axis.
- Clamp to valid servo range.

This helper is used by:
- `test_servos.py` when targeting the detected ball
- `main.py` where pan currently uses inline `int(cx / fw * 180)` calculations

### 2) Detection Loss Recovery

Add small stateful recovery logic to avoid overreacting to brief detection dropouts.

Behavior:
- On detection loss, hold last valid servo position for a short timeout (`HOLD_NO_DETECT_SEC`, ~0.4s).
- If detection returns during hold, continue tracking from last position.
- If detection remains absent after hold, recenter gradually (not instantly).

Stability guards:
- Require short consecutive detections to enter firm tracking (`TRACK_CONFIRM_FRAMES`, e.g. 2).
- Require short consecutive misses before declaring lost (`LOST_CONFIRM_FRAMES`, e.g. 3).

### 3) Consistency Across Modes

Apply same direction and recovery logic to:
- `--test-servo`
- Main flow servo aiming while searching/approaching

This removes mode-specific behavior differences and prevents regressions where tests pass but autonomous mode diverges.

### 4) Debug Visibility

Keep logs concise but sufficient to diagnose:
- target and commanded pan/tilt
- inversion flags
- mode: `tracking`, `hold`, `recenter`
- consecutive detect/miss counters

## Data Flow

Per frame:
1. Read frame
2. Detect ball
3. If detected:
   - update counters
   - compute shared mapped target (`cx`, `cy` -> `pan`, `tilt`)
   - smooth command toward target
4. If not detected:
   - update counters
   - hold last command for short timeout
   - then gradual recenter
5. Send servo command via `sbus.burst(...)`

## Error Handling

- If camera read fails: keep current retry behavior (short sleep/retry).
- Clamp all servo outputs to safe bounds.
- Preserve current safe stop/final recenter in `finally` blocks.

## Validation Plan (Approved)

1. Static direction test
   - Place ball in left/right/up/down quadrants.
   - Verify servo moves toward the ball in all quadrants.

2. Dynamic tracking test
   - Move ball slowly across frame for 20-30s.
   - Verify no strong oscillation and fewer immediate dropouts.

3. Occlusion/reacquire test
   - Hide ball for 0.2-0.4s, then re-show.
   - Verify hold behavior and fast reacquisition without instant recenter.
   - Hide >1s and verify gradual recenter.

4. Cross-mode consistency
   - Repeat checks in `--test-servo` and autonomous search/approach.
   - Verify same direction behavior in both paths.

Success criteria:
- No opposite-direction movement in pan/tilt.
- Reduced immediate `Sin pelota - centrando` after short misses.
- Stable reacquisition in both modes.

## Out of Scope

- Full PID tuning
- HSV re-calibration changes
- Wheel-motion behavior changes unrelated to servo tracking
