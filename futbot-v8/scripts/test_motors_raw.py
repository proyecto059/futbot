"""Test motores con nuevo mapeo."""

import sys
import time

sys.path.insert(0, "/home/raspi/futbot-v2/src")

from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import PAN_CENTER, TILT_CENTER
import serial

ser = serial.Serial("/dev/ttyAMA0", 1_000_000)
burst = BurstOperator(ser)
diff = DifferentialOperator()


def drive(v_left, v_right, dur_ms=1000):
    _, _, m3, m4 = diff.apply(v_left, v_right)
    burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)
    print(
        "  vL={:.0f} vR={:.0f} -> m3={:.0f} m4={:.0f}".format(v_left, v_right, m3, m4)
    )
    time.sleep(dur_ms / 1000.0 + 0.5)


def stop():
    burst.send(PAN_CENTER, TILT_CENTER, 300, 0.0, 0.0, 0.0, 0.0)
    time.sleep(0.5)


print()
print("=" * 50)
print("TEST: m3=-v_right (DER fisica), m4=-v_left (IZQ fisica)")
print("=" * 50)
print()

print("1. ADELANTE (vL=80, vR=80):")
drive(80, -80)
stop()

print("2. ATRAS (vL=-80, vR=-80):")
drive(-80, 80)
stop()

print("3. GIRAR DERECHA (vL rapido, vR lento):")
drive(130, 30)
stop()

print("4. GIRAR IZQUIERDA (vL lento, vR rapido):")
drive(-30, -130)
stop()

print("5. SOLO IZQUIERDA HACIA DELANTE (vL=80, vR=0):")
drive(80, 0)
stop()

print("6. SOLO DERECHA HACIA ATRAS (vL=0, vR=80):")
drive(0, 80)
stop()

ser.close()
print("Done.")
