# Husky.ino to Python Hybrid Vision Design

## Context

Migrate the behavior from `husky.ino` into root `main.py` using the vision pipeline from `cam.py` and hardware mapping from `test-robot/hardware.py`, with these constraints:

- No HUSKYLENS IDs.
- No servo tracking logic (camera fixed at center).
- Differential drive with two wheels only.
- Hybrid safety/engagement trigger: ultrasonic distance OR vision radius.

## Selected Approach

Chosen approach: simple finite-state machine inspired by the original `.ino` and existing `diag_center_kick.py` control.

States:

1. `SEARCH`
2. `CHASE`
3. `AVOID_MAP`

Why this approach:

- Keeps behavior close to `.ino` flow (`search -> follow -> back/map`).
- Easier to tune than fully continuous control.
- Cleaner than literal 1:1 function port of legacy sketch structure.

## Architecture

`main.py` orchestrates:

- `SerialBus` for motors (with centered fixed pan/tilt values).
- `SharedI2CBus` for ultrasonic sensor.
- Camera + detector from `cam.py` (`find_camera`, `create_detector`).

Each loop cycle:

1. Read frame and detect ball `(cx, cy, r)`.
2. Read ultrasonic every N frames.
3. Compute hybrid trigger:
   - `dist_mm <= DIST_TRIGGER_MM` OR `r >= RADIUS_TRIGGER`.
4. Dispatch to state behavior.

## Motion Model (2 Wheels)

Use differential commands only:

- Forward: `differential(+v, +v, cap)`
- Reverse: `differential(-v, -v, cap)`
- Turn left: `differential(-v, +v, cap)`
- Turn right: `differential(+v, -v, cap)`

No strafing or omni moves.

## State Behavior

### SEARCH

- If ball appears and hybrid trigger is inactive: go to `CHASE`.
- If no ball: rotate chassis in sweep pattern, alternating side.
- If hybrid trigger activates: go to `AVOID_MAP`.

### CHASE

- Compute steering from horizontal error:
  - `offset = frame_center_x - cx`
  - `rotation = offset * ROT_GAIN`
- Compute forward speed from ball radius and alignment.
- Convert to differential wheel speeds and send burst command.
- If ball missing briefly: keep soft last motion.
- If ball missing longer: return to `SEARCH`.
- If hybrid trigger activates: go to `AVOID_MAP`.

### AVOID_MAP

- Step 1: reverse for short fixed duration.
- Step 2: run short map sequence (turn + short forward steps), biasing turn direction using last known `cx` side.
- After each sub-step, attempt reacquire:
  - If ball returns and hybrid trigger clears: move to `CHASE`.
- If sequence completes without reacquire: return to `SEARCH`.

## Initial Parameters

- `SPEED_BASE = 180`
- `DIST_TRIGGER_MM = 180`
- `RADIUS_TRIGGER = 70`
- `RADIUS_CLOSE = 55`
- `CENTER_DEADBAND_PX = 35`
- `ROT_GAIN = 2.8`
- `SEARCH_TURN_SPEED = 90`
- `REVERSE_SPEED = 140`
- `REVERSE_SEC = 0.7`
- `MAP_TURN_SEC = 0.45`
- `MAP_FORWARD_SEC = 0.25`
- `MAP_MAX_STEPS = 5`
- `ULTRA_EVERY_N_FRAMES = 4`

## Error Handling

- Camera failures counted; abort safely after max threshold.
- Invalid ultrasonic read uses last valid value (or skips distance trigger for that cycle).
- Always stop motors and close hardware on interruption/exit.

## Logging

- Log state transitions.
- Log hybrid trigger cause: `dist`, `radius`, or `both`.
- Periodic summary with FPS, detection percentage, and transition counters.

## Validation Plan

1. Search-only behavior when no ball visible.
2. Chase behavior when ball appears.
3. Trigger by distance alone enters `AVOID_MAP`.
4. Trigger by radius alone enters `AVOID_MAP`.
5. Reacquire during map returns to `CHASE`; otherwise back to `SEARCH`.
