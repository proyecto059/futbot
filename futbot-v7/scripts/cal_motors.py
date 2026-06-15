"""Interactive motor calibration — verifies that move_forward/reverse/turn_left/turn_right
produce the expected physical motion on the assembled 2-wheel chassis.

Run on the Raspberry Pi with the robot on the floor (NOT in hand):

    python scripts/cal_motors.py

For each primitive the script burstes the motors for 1 s and asks the user to
confirm the observed direction. At the end it prints a summary so the user
can decide whether the wheel wiring or the sign convention in
`differential()` needs to be flipped.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cam import SerialBus  # noqa: E402
from main import (  # noqa: E402
    move_forward,
    move_reverse,
    stop_robot,
    turn_left,
    turn_right,
)

TEST_SPEED = 120
BURST_MS = 1000
PAUSE_SEC = 1.5


def _prompt_confirm(expected):
    while True:
        answer = input(f"  ¿El robot hizo '{expected}'? [y/n]: ").strip().lower()
        if answer in ("y", "s", "si", "sí", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("    Responde y o n.")


def _run_primitive(bus, label, expected, fn):
    print(f"\n[{label}] enviando '{expected}' por {BURST_MS} ms a speed={TEST_SPEED}")
    input("  Presiona ENTER cuando el robot esté libre para moverse...")
    fn(bus, speed=TEST_SPEED, dur_ms=BURST_MS)
    time.sleep(BURST_MS / 1000 + 0.3)
    stop_robot(bus, dur_ms=200)
    return _prompt_confirm(expected)


def main():
    print("=== Calibración de motores (2 ruedas) ===")
    print("Pon el robot en el suelo con espacio alrededor. Speed de prueba:", TEST_SPEED)

    bus = SerialBus()
    results = {}
    try:
        for label, expected, fn in [
            ("FWD", "avanzar recto", move_forward),
            ("REV", "retroceder recto", move_reverse),
            ("LEFT", "girar a la izquierda", turn_left),
            ("RIGHT", "girar a la derecha", turn_right),
        ]:
            results[label] = _run_primitive(bus, label, expected, fn)
            time.sleep(PAUSE_SEC)
    finally:
        stop_robot(bus, dur_ms=200)
        bus.close()

    print("\n=== Resumen ===")
    for label, ok in results.items():
        print(f"  {label:<6} {'OK' if ok else 'FALLO'}")

    bad = [k for k, v in results.items() if not v]
    if not bad:
        print("\nTodas las primitivas físicas coinciden con los nombres. Wiring correcto.")
        return 0

    print("\nRevisar wiring / signos:")
    if "FWD" in bad and "REV" in bad:
        print("  - Ambos fwd/rev invertidos -> invertir signo global en differential().")
    if "LEFT" in bad and "RIGHT" in bad:
        print("  - Giros invertidos -> intercambiar las dos salidas de rueda (cables motor L/R) "
              "o invertir el signo de uno de los dos valores en differential().")
    if ("FWD" in bad) ^ ("REV" in bad):
        print("  - Solo una dirección lineal falla -> un motor tiene polaridad invertida.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
