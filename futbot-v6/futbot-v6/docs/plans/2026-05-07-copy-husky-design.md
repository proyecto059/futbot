# copy_husky.py Design

**Date:** 2026-05-07
**Topic:** Port `husky.ino` Arduino person-following logic to pure Python using `src/vision/` and `src/motors/`

## Overview

`scripts/copy_husky.py` duplicates the behavior of `husky.ino` using the vision module (`HybridVisionService`) instead of HuskyLens, and the correct motor mapping from `test_motors_raw.py`. No ultrasonic sensor — proximity is determined by ball radius in pixels.

## HuskyLens → Vision Mapping

| HuskyLens | Vision equivalent |
|-----------|-------------------|
| ID=1 (person to chase) | Ball detected (`ball is not None`) |
| ID=2 (obstacle) | Robot detected (`len(robots) > 0`) |
| `result.xCenter` (center X) | `ball['cx']` |
| Distance < 15cm | `ball['r'] >= 70px` |
| Nobody detected | `ball is None and no robots` |

## Motor Mapping

From `test_motors_raw.py` and `DifferentialOperator`:

```
m3 = -v_right  → right physical wheel
m4 = -v_left   → left physical wheel
m1 = m2 = 0.0  (always unused)
```

Forward:  `v_left=SPEED,  v_right=-SPEED`
Backward: `v_left=-SPEED, v_right=SPEED`

## Architecture

```
copy_husky.py
├── HybridVisionService (src/vision)        ← replaces HuskyLens
├── BurstOperator + DifferentialOperator    ← low-level motor control
├── serial port (/dev/ttyAMA0 @ 1M baud)
│
├── send_motors(v_left, v_right, dur_ms)    ← helper
├── avanzar / retroceder / parar            ← movement primitives
├── buscarpersona                           ← spin search
├── recuperarPersonaInteligente(rc)         ← turn toward last known cx
├── mapeoArea(rc)                           ← alternating L/R scan, max 5 turns
├── pausaDeteccion(tiempo_ms)              ← detect ball during pauses
└── main()                                  ← infinite loop FSM
```

## Constants

```python
SPEED = 80              # base motor speed
BALL_TOO_CLOSE_R = 70   # ball radius px (replaces DIST_MIN=15cm)
FRAME_WIDTH = 320        # camera width
```

## Behavior Loop (FSM)

```
loop:
  tick = vision.tick()
  ball = tick['ball']
  robots = tick['robots']
  has_ball = ball is not None
  has_robots = len(robots) > 0
  too_close = has_ball and ball['r'] >= BALL_TOO_CLOSE_R
  rc = ball['cx'] if has_ball else last_rc

  if has_ball and has_robots and too_close:
    retroceder(); mapeoArea(rc)

  elif has_ball:
    avanzar(); delay(1400)

  elif has_robots and too_close:
    retroceder(); mapeoArea(rc)

  elif has_robots:
    mapeoArea(rc)

  else:  # nothing detected
    recuperarPersonaInteligente(rc); mapeoArea(rc)
```

## Movement Primitives

| Primitive | v_left | v_right | dur_ms |
|-----------|--------|---------|--------|
| avanzar | SPEED | -SPEED | 1400 |
| retroceder | -SPEED | SPEED | 600 |
| parar | 0 | 0 | 300 |
| buscarpersona | SPEED | SPEED | 200 |

## recuperarPersonaInteligente(rc)

Uses last known `ball['cx']` to decide which direction the target was lost:

- `rc < 100` (left) → turn left: `(-SPEED_LOW, -SPEED_LOW, 1000)`
- `100 <= rc <= 200` (center) → forward: `(SPEED, -SPEED, 1000)`
- `rc > 200` (right) → turn right: `(SPEED_LOW, SPEED_LOW, 1000)`

Where `SPEED_LOW = SPEED - 30`.

## mapeoArea(rc)

Alternating left/right scan turns, checking for ball reappearance during pauses. Max 5 turns before retreating:

```
direction = left if rc < 150 else right

for each turn (max 5):
  spin 800ms (direction) → pause/detect 300ms → if ball found: return
  spin 800ms (opposite)  → pause/detect 300ms → if ball found: return
  spin 800ms (direction) → pause/detect 300ms → if ball found: return

if 5+ turns: retroceder(); reset counter
```

Turn left:  `(-SPEED_LOW, -SPEED_LOW)`
Turn right: `(SPEED_LOW, SPEED_LOW)`

## pausaDeteccion(tiempo_ms)

During mapeoArea pauses, check `vision.tick()` for ball reappearance. If ball found → `avanzar()` and return `True`.

## Error Handling

- Vision `tick()` failures caught per-frame, skipped with a short sleep — non-fatal
- `KeyboardInterrupt` → clean shutdown: stop all motors, close vision, close serial
- `rc` defaults to `160` (center of frame) when no ball has ever been seen

## Testing

- Run on Raspberry Pi with camera connected, robot on the floor
- Place ball in front: robot should advance toward it
- Remove ball: robot should scan left/right to find it
- Bring ball very close: robot should retreat and scan
- Ctrl+C should stop all motors cleanly
