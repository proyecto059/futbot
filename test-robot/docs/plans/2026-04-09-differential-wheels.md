# Differential Wheels Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace mecanum omnidirectional kinematics with standard 4-wheel differential drive, adapt all tests and state machine accordingly, add --gol-giro and --gol-avanzar tests.

**Architecture:** Remove mecanum() function and replace with differential() that maps left/right wheel speeds to 4 motors (m1+m3=left, m2+m4=right). Adapt main.py state machine to use only forward/backward/turn/spin movements. Adapt test files to differential-compatible movements.

**Tech Stack:** Python 3.11, pyserial, smbus2, opencv-python-headless, numpy

---

## Task 1: Replace mecanum kinematics in hardware.py

**Files:**
- Modify: `hardware.py` (lines with MEC_A, MEC_B constants and mecanum function)

**Step 1: Remove mecanum constants and function**

In `hardware.py`:
- Remove lines: `MEC_A = 67`, `MEC_B = 59`
- Remove the entire `mecanum()` function (approx lines 173-186)
- Add the following in its place:

```python
def differential(v_left, v_right, cap=DEFAULT_SPEED):
    mx = max(abs(v_left), abs(v_right))
    if mx > cap:
        s = cap / mx
        v_left *= s
        v_right *= s
    return (-v_left, v_right, -v_left, v_right)
```

**Step 2: Verify no other references to mecanum in hardware.py**

Run: `grep -n "mecanum\|MEC_A\|MEC_B" hardware.py`
Expected: No matches

---

## Task 2: Adapt test_motors.py

**Files:**
- Modify: `test_motors.py`

**Step 1: Replace imports**

Change:
```python
from hardware import PAN_CENTER, TILT_CENTER, log, mecanum
```
To:
```python
from hardware import PAN_CENTER, TILT_CENTER, log, differential
```

**Step 2: Update run_test() to use differential**

Replace the 3 test cases in `run_test()` with differential-appropriate ones:

```python
def run_test(sbus, speed):
    S = speed
    tests = [
        {
            "name": "ADELANTE (derecho)",
            "m": differential(S, S, S),
            "desc": "Robot debe avanzar recto hacia adelante",
        },
        {
            "name": "GIRO ANTICLOCKWISE (sobre su eje)",
            "m": differential(S, -S, S),
            "desc": "Robot debe girar a la izquierda sobre su eje",
        },
        {
            "name": "CURVA IZQUIERDA",
            "m": differential(S * 0.5, S, S),
            "desc": "Robot debe avanzar curvando hacia la izquierda",
        },
    ]
```

Also update the log messages — remove the vx/vy decomposition and vel/deg/omega params, show v_left/v_right instead.

**Step 3: Update run_diag_strafe() to run_diag_turns()**

Rename function to `run_diag_turns()`. Replace the 4 diagonal tests with turn-pattern tests:

```python
def run_diag_turns(sbus, speed):
    S = speed
    pause = 1.5
    tests = [
        {"label": "T1", "desc": "Solo ruedas izquierda adelante (vL=S, vR=0)", "m": differential(S, 0, S)},
        {"label": "T2", "desc": "Solo ruedas derecha adelante (vL=0, vR=S)", "m": differential(0, S, S)},
        {"label": "T3", "desc": "Izq adelante + Der atras (giro CW)", "m": differential(S, -S, S)},
        {"label": "T4", "desc": "Izq atras + Der adelante (giro CCW)", "m": differential(-S, S, S)},
    ]
```

**Step 4: Update run_diag_motors()**

No changes needed to `run_diag_motors()` — it tests individual motors with raw values, no mecanum dependency. Keep as-is.

---

## Task 3: Adapt test_omni.py → test_moves.py

**Files:**
- Modify: `test_omni.py`

**Step 1: Replace imports**

Change:
```python
from hardware import PAN_CENTER, TILT_CENTER, log, mecanum
```
To:
```python
from hardware import PAN_CENTER, TILT_CENTER, log, differential
```

**Step 2: Replace movements with differential-compatible ones**

Replace `run_all_omni()` with `run_all_moves()`:

```python
def run_all_moves(sbus, speed):
    S = speed
    moves = [
        ("Adelante", differential(S, S, S), 2.0),
        ("Atras", differential(-S, -S, S), 2.0),
        ("Giro CW (horario)", differential(S, -S, S), 2.0),
        ("Giro CCW (antihorario)", differential(-S, S, S), 2.0),
        ("Curva Izquierda", differential(S * 0.5, S, S), 3.0),
        ("Curva Derecha", differential(S, S * 0.5, S), 3.0),
    ]
    seqs = 3
    total = len(moves) + seqs
    n = 1

    for name, m, dur in moves:
        log.info("[MOVES] %d/%d: %s (%.1fs)", n, total, name, dur)
        sbus.burst(PAN_CENTER, TILT_CENTER, int(dur * 1000), *m)
        time.sleep(dur + 0.3)
        n += 1

    log.info("[MOVES] %d/%d: Zigzag (4 giros rapidos)", n, total)
    for j in range(4):
        m = differential(S, -S, S) if j % 2 == 0 else differential(-S, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 800, *m)
        time.sleep(1.0)
    n += 1

    log.info("[MOVES] %d/%d: Patron cuadrado (4 lados)", n, total)
    for sname, m in [
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
    ]:
        log.info("[MOVES]   Cuadrado: %s", sname)
        sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
        time.sleep(1.3)
    n += 1

    log.info("[MOVES] %d/%d: Espiral (curva progresiva)", n, total)
    for ratio in [1.0, 0.7, 0.5, 0.3]:
        m = differential(S * ratio, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 1500, *m)
        time.sleep(1.8)

    log.info("[MOVES] Secuencia completada (%d movimientos)", total)
```

---

## Task 4: Create test_gol.py

**Files:**
- Create: `test_gol.py`

**Step 1: Write test_gol.py with both --gol-giro and --gol-avanzar**

```python
import time

from hardware import (
    PAN_CENTER,
    TILT_CENTER,
    BALL_CLOSE_RADIUS,
    CENTER_THRESH,
    SPIN_360_SEC,
    detect_ball,
    differential,
    find_camera,
    log,
)


GOL_GIRO_ANGLE_SEC = 0.5
GOL_GIRO_ADVANCE_SEC = 1.5
GOL_AVANCE_BRAKE_SEC = 0.5
GOL_AVANCE_SHOT_SEC = 1.0
GOL_DURATION = 120.0


def run_gol_giro(sbus, speed):
    cap, fw = find_camera()
    if not cap:
        log.error("[GOL-GIRO] No se detecto camara. Abortando.")
        return
    fcx = fw // 2
    S = speed
    log.info("=" * 55)
    log.info("[GOL-GIRO] === TEST GOL CON GIRO (%.0fs max) ===", GOL_DURATION)
    log.info("[GOL-GIRO] Buscar pelota → avanzar → girar 45° → avanzar → golpear")
    log.info("=" * 55)
    t0 = time.time()
    phase = "search"
    t_phase = time.time()

    try:
        while time.time() - t0 < GOL_DURATION:
            if phase == "search":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                ball = detect_ball(frame)
                if ball:
                    cx, cy, r = ball
                    log.info("[GOL-GIRO] Pelota detectada cx=%d cy=%d r=%.0f", cx, cy, r)
                    phase = "approach"
                    t_phase = time.time()
                else:
                    time.sleep(0.05)

            elif phase == "approach":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                ball = detect_ball(frame)
                if ball:
                    cx, cy, r = ball
                    offset = abs(cx - fcx)
                    omega = max(-1.0, min(1.0, (cx - fcx) / fcx))
                    v_left = S * 0.6 * (1 + omega * 0.5)
                    v_right = S * 0.6 * (1 - omega * 0.5)
                    m = differential(v_left, v_right, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    if r >= BALL_CLOSE_RADIUS and offset < CENTER_THRESH:
                        log.info("[GOL-GIRO] Pelota cerca y centrada. Girando...")
                        sbus.stop()
                        phase = "turn"
                        t_phase = time.time()
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    phase = "search"

            elif phase == "turn":
                elapsed = time.time() - t_phase
                if elapsed < GOL_GIRO_ANGLE_SEC:
                    m = differential(-S * 0.5, S * 0.5, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] Giro completado. Avanzando para golpear...")
                    phase = "strike"
                    t_phase = time.time()

            elif phase == "strike":
                elapsed = time.time() - t_phase
                if elapsed < GOL_GIRO_ADVANCE_SEC:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] GOL! Celebrando giro 360...")
                    phase = "celebrate"
                    t_phase = time.time()

            elif phase == "celebrate":
                elapsed = time.time() - t_phase
                if elapsed < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] Celebracion completada!")
                    break

    except KeyboardInterrupt:
        log.info("[GOL-GIRO] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        log.info("[GOL-GIRO] === FIN ===")


def run_gol_avance(sbus, speed):
    cap, fw = find_camera()
    if not cap:
        log.error("[GOL-AVANCE] No se detecto camara. Abortando.")
        return
    fcx = fw // 2
    S = speed
    log.info("=" * 55)
    log.info("[GOL-AVANCE] === TEST GOL AVANZANDO (%.0fs max) ===", GOL_DURATION)
    log.info("[GOL-AVANCE] Buscar pelota → acercar lento → frenar → golpe")
    log.info("=" * 55)
    t0 = time.time()
    phase = "search"
    t_phase = time.time()

    try:
        while time.time() - t0 < GOL_DURATION:
            if phase == "search":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                ball = detect_ball(frame)
                if ball:
                    cx, cy, r = ball
                    log.info("[GOL-AVANCE] Pelota detectada cx=%d cy=%d r=%.0f", cx, cy, r)
                    phase = "approach"
                    t_phase = time.time()
                else:
                    time.sleep(0.05)

            elif phase == "approach":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                ball = detect_ball(frame)
                if ball:
                    cx, cy, r = ball
                    offset = abs(cx - fcx)
                    omega = max(-1.0, min(1.0, (cx - fcx) / fcx))
                    v_left = S * 0.5 * (1 + omega * 0.5)
                    v_right = S * 0.5 * (1 - omega * 0.5)
                    m = differential(v_left, v_right, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    if r >= BALL_CLOSE_RADIUS * 0.8 and offset < CENTER_THRESH:
                        log.info("[GOL-AVANCE] Cerca. Frenando...")
                        sbus.stop()
                        phase = "brake"
                        t_phase = time.time()
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    phase = "search"

            elif phase == "brake":
                elapsed = time.time() - t_phase
                if elapsed >= GOL_AVANCE_BRAKE_SEC:
                    log.info("[GOL-AVANCE] Golpe!")
                    phase = "strike"
                    t_phase = time.time()

            elif phase == "strike":
                elapsed = time.time() - t_phase
                if elapsed < GOL_AVANCE_SHOT_SEC:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-AVANCE] GOL! Celebrando giro 360...")
                    phase = "celebrate"
                    t_phase = time.time()

            elif phase == "celebrate":
                elapsed = time.time() - t_phase
                if elapsed < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-AVANCE] Celebracion completada!")
                    break

    except KeyboardInterrupt:
        log.info("[GOL-AVANCE] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        log.info("[GOL-AVANCE] === FIN ===")
```

---

## Task 5: Adapt main.py state machine

**Files:**
- Modify: `main.py`

**Step 1: Update imports**

Replace `mecanum` with `differential` in imports. Add imports for new test functions:

```python
from hardware import (
    ...,
    differential,  # replace mecanum
)
from test_gol import run_gol_giro, run_gol_avance
```

**Step 2: Add --gol-giro and --gol-avanzar arguments**

Add to argparse:
```python
ap.add_argument("--gol-giro", action="store_true", help="Test gol: avanzar → girar → avanzar")
ap.add_argument("--gol-avance", action="store_true", help="Test gol: acercar → frenar → golpe")
```

**Step 3: Add handler blocks for new tests**

After the --test-servo block, add:

```python
if args.gol_giro:
    try:
        run_gol_giro(sbus, S)
    except KeyboardInterrupt:
        log.info("Interrumpido por usuario (Ctrl+C)")
    finally:
        sbus.stop()
        sbus.close()
        log.info("TurboPi – Fin (gol-giro)")
    return

if args.gol_avance:
    try:
        run_gol_avance(sbus, S)
    except KeyboardInterrupt:
        log.info("Interrumpido por usuario (Ctrl+C)")
    finally:
        sbus.stop()
        sbus.close()
        log.info("TurboPi – Fin (gol-avance)")
    return
```

**Step 4: Update --all-omni to --all-moves**

Change flag name from `--all-omni` to `--all-moves`, update import from `run_all_omni` to `run_all_moves`.

**Step 5: Update --diag-strafe to --diag-turns**

Change flag name from `--diag-strafe` to `--diag-turns`, update import from `run_diag_strafe` to `run_diag_turns`.

**Step 6: Update APPROACHING state**

Replace:
```python
omega = max(-1.0, min(1.0, (cx - fcx) / fcx * 0.5))
m = mecanum(S * 0.6, 90, omega, S)
```
With:
```python
omega = max(-1.0, min(1.0, (cx - fcx) / fcx * 0.5))
v_left = S * 0.6 * (1 + omega)
v_right = S * 0.6 * (1 - omega)
m = differential(v_left, v_right, S)
```

**Step 7: Update AIMING state**

Replace the strafe movement with: advance forward, then turn 45°, then advance again:

```python
elif state == State.AIMING:
    dt = time.time() - t_aim
    if dt < 0.8:
        m = differential(S, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
        log.info("[AIMING] Avanzando recto (%.1f/0.8s)", dt)
        time.sleep(0.15)
    elif dt < 1.3:
        m = differential(-S * 0.5, S * 0.5, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
        log.info("[AIMING] Girando ~45° (%.1f/1.3s)", dt)
        time.sleep(0.15)
    elif dt < 2.8:
        m = differential(S, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
        log.info("[AIMING] Avanzando al arco (%.1f/2.8s)", dt)
        time.sleep(0.15)
    else:
        log.info("[AIMING] Posicion lista. Ejecutando tiro!")
        state = State.ANGULAR_SHOT
        t_shot = time.time()
```

**Step 8: Update ANGULAR_SHOT state**

Replace:
```python
m = mecanum(SHOT_SPEED, 45, 0)
```
With:
```python
m = differential(SHOT_SPEED, SHOT_SPEED, SHOT_SPEED)
```

**Step 9: Update SPINNING state**

Replace:
```python
sbus.burst(PAN_CENTER, TILT_CENTER, 200, -S, -S, -S, -S)
```
With:
```python
m = differential(S, -S, S)
sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
```

**Step 10: Update safety retreat**

Replace raw motor values with differential calls:

```python
m = differential(-RETREAT_SPEED, -RETREAT_SPEED, RETREAT_SPEED)
sbus.burst(pan, TILT_CENTER, int(RETREAT_SEC * 1000), *m)
```

---

## Task 6: Verify all references updated

**Step 1: Search for remaining mecanum references**

Run: `grep -rn "mecanum\|MEC_A\|MEC_B\|all_omni\|all-omni\|diag_strafe\|diag-strafe\|run_all_omni\|run_diag_strafe" --include="*.py" --exclude-dir=".backup" --exclude-dir=".ruff_cache" .`
Expected: No matches (except possibly in comments if desired)

**Step 2: Run ruff lint**

Run: `ruff check .`
Expected: No errors

---

## Task 7: Commit

```bash
git add hardware.py main.py test_omni.py test_motors.py test_gol.py docs/plans/2026-04-09-differential-wheels.md
git commit -m "refactor: replace mecanum omnidirectional with 4-wheel differential drive

- Replace mecanum() kinematics with differential() in hardware.py
- Adapt state machine: approach via curves, aim via advance+turn+advance
- Add --gol-giro (advance → turn → advance) and --gol-avance (approach → brake → strike)
- Rename --all-omni → --all-moves, --diag-strafe → --diag-turns
- Adapt all test movements to differential-compatible patterns"
```