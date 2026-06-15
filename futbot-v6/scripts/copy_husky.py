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
            ball = tick.get("ball") if tick is not None else None
        except Exception as e:
            print(f"  pausaDeteccion: vision.tick() error: {e}")
            time.sleep(0.01)
            continue
        if ball is not None:
            cx = ball.get("cx", 0)
            cy = ball.get("cy", 0)
            print(f"  ball found during pause at ({cx}, {cy})")
            avanzar()
            persona_vista = True
            return True
        time.sleep(0.01)
    return False


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


def mapeoArea(rc):
    """Alternating left/right scan turns, checking for ball reappearance.

    Direction is determined by rc (last known ball x-center):
      rc < 150  → start with LEFT turn
      rc >= 150 → start with RIGHT turn

    Each call does up to 3 scan turns (800ms each) before returning.
    After 5 accumulated turns (global num_vueltas), retreats and resets.
    Detection during pauses aborts scan early (ball found).
    """
    global num_vueltas

    print(f"mapeoArea: rc={rc}  vueltas={num_vueltas}")
    direction_right = rc >= 150

    def spin(direction_right_turn):
        """Execute one scan turn (800ms) in the given direction."""
        if direction_right_turn:
            print("  turn RIGHT")
            send_motors(SPEED_LOW, SPEED_LOW, 800)
        else:
            print("  turn LEFT")
            send_motors(-SPEED_LOW, -SPEED_LOW, 800)

    for i in range(3):
        if i == 1:
            direction_right = not direction_right  # second turn goes opposite

        num_vueltas += 1
        spin(direction_right)
        if pausaDeteccion(800):
            return
        parar()

        if pausaDeteccion(300):
            return

        if num_vueltas >= 5:
            print("  max turns reached → retroceder")
            retroceder()
            num_vueltas = 0
            return

        if i == 1:
            direction_right = not direction_right  # restore original for third

    print("mapeoArea complete")


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
