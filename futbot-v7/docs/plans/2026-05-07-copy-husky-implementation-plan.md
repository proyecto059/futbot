# copy_husky.py Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create `scripts/copy_husky.py` — a pure-Python port of `husky.ino` person-following logic using `HybridVisionService` for ball detection and the correct motor mapping from `test_motors_raw.py`.

**Architecture:** Single script importing `HybridVisionService` (replaces HuskyLens) and raw motor operators (`BurstOperator` + `DifferentialOperator`) for low-level UART control. No `MotorService` facade — direct operator usage matches `test_motors_raw.py` pattern. Ball radius replaces ultrasonic distance. All husky.ino behaviors preserved: avanzar, retroceder, recuperarPersonaInteligente, mapeoArea, pausaDeteccion.

**Tech Stack:** Python 3, `HybridVisionService` (OpenCV + ONNX), `BurstOperator`/`DifferentialOperator` (serial UART), `threading.Lock` for motor safety.

---

### Task 1: Skeleton — imports, constants, init, helpers

**Files:**
- Create: `scripts/copy_husky.py`

**Step 1: Create the skeleton with imports, constants, init, and helper functions**

```python
"""copy_husky.py — Port of husky.ino to pure Python using src/vision/ and src/motors/.

HuskyLens ID mapping:
  ID=1 (person)       → ball detected
  ID=2 (obstacle)     → robot detected
  distance < 15cm     → ball['r'] >= BALL_TOO_CLOSE_R (70px)
  result.xCenter      → ball['cx']

Motor mapping (from test_motors_raw.py):
  m3 = -v_right  → right physical wheel
  m4 = -v_left   → left physical wheel
  m1 = m2 = 0.0  (always)
"""

import sys
import time
import threading

sys.path.insert(0, "/home/raspi/futbot-v2/src")
sys.stdout.reconfigure(line_buffering=True)

import serial
from vision import HybridVisionService
from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import (
    PAN_CENTER,
    TILT_CENTER,
    SERIAL_PORT,
    SERIAL_BAUD,
)

# ---------- constants ----------
SPEED = 80
SPEED_LOW = SPEED - 30
BALL_TOO_CLOSE_R = 70  # ball radius px (replaces DIST_MIN=15cm)

# ---------- init ----------
vision = HybridVisionService()
ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD)
burst = BurstOperator(ser)
diff = DifferentialOperator()
_lock = threading.Lock()

# ---------- state ----------
persona_vista = False
last_rc = 160  # default center of frame
num_vueltas = 0


def send_motors(v_left, v_right, dur_ms):
    """Send differential drive command with correct mapping."""
    _, _, m3, m4 = diff.apply(v_left, v_right)
    with _lock:
        burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)
    print(f"  motors: vL={v_left:+.0f} vR={v_right:+.0f}  m3={m3:+.0f} m4={m4:+.0f}  dur={dur_ms}ms")
```

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add copy_husky.py skeleton with imports and motor helpers"
```

---

### Task 2: Movement primitives (avanzar, retroceder, parar, buscarpersona)

**Files:**
- Modify: `scripts/copy_husky.py` — append after `send_motors()`

**Step 1: Add the four movement primitives**

```python
def avanzar():
    """Drive straight forward (both wheels forward)."""
    print(">>> avanzar")
    send_motors(SPEED, -SPEED, 1400)


def retroceder():
    """Drive straight backward."""
    print(">>> retroceder")
    send_motors(-SPEED, SPEED, 600)


def parar():
    """Stop all motors with a safety pause."""
    print(">>> parar")
    send_motors(0.0, 0.0, 1000)


def buscarpersona():
    """Spin in place to search for the ball."""
    print(">>> buscarpersona (spin)")
    send_motors(SPEED, SPEED, 200)
```

**Step 2: Verify syntax**
Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add movement primitives to copy_husky.py"
```

---

### Task 3: Vision detection helper (pausaDeteccion)

**Files:**
- Modify: `scripts/copy_husky.py` — append after movement primitives

**Step 1: Add the interruptible detection helper**

```python
def pausaDeteccion(tiempo_ms):
    """Check for ball detection during a pause window.

    Returns True if ball found (and triggers avanzar), False otherwise.
    """
    nonlocal persona_vista
    start = time.monotonic()
    deadline = start + tiempo_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            tick = vision.tick()
        except Exception:
            time.sleep(0.01)
            continue
        ball = tick.get("ball")
        if ball is not None:
            print(f"  ball found during pause at ({ball['cx']}, {ball['cy']})")
            avanzar()
            persona_vista = True
            return True
        time.sleep(0.01)
    return False
```

Wait — `nonlocal` won't work at module level. Let me adjust the approach. Use a global instead, or pass the state variable.

Actually, let me reconsider: `persona_vista` is already a module-level variable. The function uses it directly. No `nonlocal` needed.

```python
def pausaDeteccion(tiempo_ms):
    """Check for ball detection during a pause window.

    Returns True if ball found (and triggers avanzar), False otherwise.
    """
    global persona_vista
    start = time.monotonic()
    deadline = start + tiempo_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            tick = vision.tick()
        except Exception:
            time.sleep(0.01)
            continue
        ball = tick.get("ball")
        if ball is not None:
            print(f"  ball found during pause at ({ball['cx']}, {ball['cy']})")
            avanzar()
            persona_vista = True
            return True
        time.sleep(0.01)
    return False
```

**Step 2: Verify syntax**
Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add pausaDeteccion helper to copy_husky.py"
```

---

### Task 4: Recovery logic (recuperarPersonaInteligente)

**Files:**
- Modify: `scripts/copy_husky.py` — append after `pausaDeteccion`

**Step 1: Add the intelligent recovery function**

```python
def recuperarPersonaInteligente(rc):
    """Turn toward last known ball position when lost.

    Zones (based on frame width 320):
      rc < 100   → last seen on LEFT  → turn left
      100-200    → last seen CENTER   → drive forward
      rc > 200   → last seen on RIGHT → turn right
    """
    global persona_vista

    if not persona_vista:
        print("  never saw ball, skipping recovery")
        return

    print(f"recuperarPersonaInteligente: rc={rc}")

    if rc < 100:
        print("  last position: LEFT → turning left")
        send_motors(-SPEED_LOW, -SPEED_LOW, 1000)
    elif rc <= 200:
        print("  last position: CENTER → advancing")
        send_motors(SPEED, -SPEED, 1000)
    else:
        print("  last position: RIGHT → turning right")
        send_motors(SPEED_LOW, SPEED_LOW, 1000)

    persona_vista = False
```

**Step 2: Verify syntax**
Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add recuperarPersonaInteligente to copy_husky.py"
```

---

### Task 5: Area scanning (mapeoArea)

**Files:**
- Modify: `scripts/copy_husky.py` — append after `recuperarPersonaInteligente`

**Step 1: Add the area scanning / zigzag search function**

```python
def mapeoArea(rc):
    """Alternating left/right scan turns, checking for ball reappearance.

    Max 5 turns total. If ball found during any pause, returns early.
    After 5 turns with no detection, retreats and resets counter.
    """
    global num_vueltas

    print(f"mapeoArea: rc={rc}  vueltas={num_vueltas}")

    direction_right = rc >= 150  # True = turn right, False = turn left

    def turn(direction_right):
        """Execute one scan turn (800ms) in the given direction."""
        if direction_right:
            print("  turn RIGHT")
            send_motors(SPEED_LOW, SPEED_LOW, 800)
        else:
            print("  turn LEFT")
            send_motors(-SPEED_LOW, -SPEED_LOW, 800)

    turn_funcs = [
        lambda: turn(direction_right),       # turn 1: original direction
        lambda: turn(not direction_right),   # turn 2: opposite
        lambda: turn(direction_right),       # turn 3: original again
    ]

    for turn_fn in turn_funcs:
        num_vueltas += 1
        turn_fn()
        if pausaDeteccion(300):
            return
        parar()

    if num_vueltas >= 5:
        print("  max turns reached → retroceder")
        retroceder()
        num_vueltas = 0
```

**Step 2: Verify syntax**
Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add mapeoArea scanning logic to copy_husky.py"
```

---

### Task 6: Main FSM loop

**Files:**
- Modify: `scripts/copy_husky.py` — append `main()` function and `if __name__ == "__main__"` guard

**Step 1: Add the main FSM loop**

```python
def main():
    global persona_vista, last_rc, num_vueltas

    print("=" * 50)
    print("copy_husky.py — port of husky.ino using vision module")
    print("=" * 50)
    print(f"  SPEED={SPEED}  SPEED_LOW={SPEED_LOW}  BALL_TOO_CLOSE_R={BALL_TOO_CLOSE_R}")
    print(f"  Camera: {vision.frame_width}px")
    print(f"  Serial: {SERIAL_PORT} @ {SERIAL_BAUD} baud")
    print("=" * 50)
    print()

    try:
        while True:
            # --- acquire vision ---
            try:
                tick = vision.tick()
            except Exception as e:
                print(f"vision.tick() error: {e}")
                time.sleep(0.05)
                continue

            ball = tick.get("ball")
            robots = tick.get("robots", [])

            has_ball = ball is not None
            has_robots = len(robots) > 0
            too_close = has_ball and ball["r"] >= BALL_TOO_CLOSE_R

            rc = ball["cx"] if has_ball else last_rc

            print(f"\n--- frame ---")
            print(f"  ball={'yes' if has_ball else 'no'}  robots={'yes' if has_robots else 'no'}  too_close={'yes' if too_close else 'no'}  rc={rc}")
            if has_ball:
                print(f"  ball: cx={ball['cx']} cy={ball['cy']} r={ball['r']:.1f} conf={ball['conf']:.2f} src={ball['source']}")

            # --- FSM (mirrors husky.ino loop) ---
            if has_ball and has_robots and too_close:
                print("STATE: ball + robots + too_close → retroceder + mapeoArea")
                retroceder()
                mapeoArea(rc)

            elif has_ball:
                print("STATE: ball found → avanzar")
                persona_vista = True
                avanzar()
                time.sleep(1.4)

            elif has_robots and too_close:
                print("STATE: robots + too_close → retroceder + mapeoArea")
                retroceder()
                mapeoArea(rc)

            elif has_robots:
                print("STATE: robots only → mapeoArea")
                mapeoArea(rc)

            else:
                print("STATE: nothing detected → recover + scan")
                recuperarPersonaInteligente(rc)
                mapeoArea(rc)

            last_rc = rc

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt — shutting down...")
    finally:
        print("stopping motors...")
        send_motors(0.0, 0.0, 300)
        vision.close()
        ser.close()
        print("Done.")


if __name__ == "__main__":
    main()
```

**Step 2: Verify syntax**
Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add scripts/copy_husky.py
git commit -m "feat: add main FSM loop to copy_husky.py"
```

---

### Task 7: Final verification — syntax check and dry-run review

**Step 1: Full syntax validation**

Run: `python3 -c "import ast; ast.parse(open('scripts/copy_husky.py').read()); print('Syntax OK')"`

**Step 2: Check for import issues (dry run, imports only)**

Run: `python3 -c "import sys; sys.path.insert(0,'src'); import ast, textwrap; content=open('scripts/copy_husky.py').read(); tree=ast.parse(content); print('AST valid. Lines:', len(content.splitlines()))"`

**Step 3: Commit (if any cleanup needed)**

```bash
git add scripts/copy_husky.py
git commit -m "chore: finalize copy_husky.py"
```

---

### Task 8: Smoke test on Raspberry Pi

**Step 1: Run on the robot with camera connected**

Run: `python3 scripts/copy_husky.py`
Expected:
- Camera initializes, serial opens
- Robot moves when ball is detected
- Ctrl+C stops motors cleanly

**Step 2: Test scenarios**

| Action | Expected behavior |
|--------|-------------------|
| Place ball in front | Robot advances forward |
| Remove ball | Robot scans left/right |
| Bring ball very close | Robot retreats |
| Move ball to right side | Robot turns right to find it |
| Ctrl+C | Motors stop, clean exit |

**Step 3: Commit (if any burn-in fixes needed)**

```bash
git add scripts/copy_husky.py
git commit -m "fix: burn-in fixes for copy_husky.py"
```

---

## Notes

- **No test file needed** — this is a hardware-dependent script. Syntax validation + smoke test on the actual robot is sufficient.
- The `last_rc` default is `160` (center of 320px frame). This means initial recovery/search starts by looking center/forward.
- `send_motors` uses `threading.Lock` to prevent concurrent serial writes.
- The `delay(1400)` after `avanzar()` is preserved from husky.ino — gives time for the ball to be re-acquired after moving.
- The vision `tick()` returns a dict (not `VisionOutputDto`), so access fields with `tick.get("ball")`, `ball["cx"]`, etc.
