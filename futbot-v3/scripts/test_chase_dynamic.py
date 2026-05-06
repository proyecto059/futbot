"""Visual Servoing Controller - Chase continuo sin maquina de estados.

Cada tick (~10ms) recalcula vL/vR usando:
  - Error angular: theta = (cx - center) / center
  - Error de distancia: Z_error = (1/r) - (1/r_desired)
  - PI para angulo, P para distancia
  - Cinematica diferencial para mover

Sin zones, sin turn_gains hardcodeados.
"""

import sys
import time

sys.path.insert(0, "/home/raspi1/futbot-v3/src")
sys.stdout.reconfigure(line_buffering=True)

from vision import HybridVisionService
from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import PAN_CENTER, TILT_CENTER
from chase.visual_servo_controller import VisualServoController
import serial


class Kalman1D:
    def __init__(self, q: float = 0.5, r: float = 4.0) -> None:
        self.q = q
        self.r = r
        self.x = 0.0
        self.p = 1.0

    def update(self, measurement: float) -> float:
        self.p += self.q
        k = self.p / (self.p + self.r)
        self.x += k * (measurement - self.x)
        self.p *= 1.0 - k
        return self.x


ser = serial.Serial("/dev/ttyAMA0", 1_000_000)
burst = BurstOperator(ser)
diff_op = DifferentialOperator()

print("Iniciando vision...", flush=True)
vision = HybridVisionService()
time.sleep(3)
frame_w = vision.frame_width
half = frame_w / 2
print("Listo. Frame={} centro={}".format(frame_w, half), flush=True)

controller = VisualServoController(
    center_x=half,
    kp_theta=70.0,
    kp_dist=62.0,
    v_min=62.0,
    base_forward=62.0,
    turn_ratio_max=0.60,
    turn_ratio_boost_gain=0.40,
    min_alignment_speed_ratio=0.30,
    alignment_slowdown_gain=0.80,
    min_wheel_forward=14.0,
)
kalman_cx = Kalman1D(q=2.6, r=1.0)
kalman_r = Kalman1D(q=0.9, r=1.5)

last_v_left = 0.0
last_v_right = 0.0
last_turn = 0.0
miss_streak = 0
hold_frames = 8
hold_min_decay = 0.05
turn_rate_limit = 5.5
turn_abs_limit = 36.0
cache_turn_scale = 0.35
cache_speed_scale = 0.55

tick = 0
tick_start = time.monotonic()
try:
    while True:
        snap = vision.tick()
        ball = snap.get("ball")

        if ball is None:
            if miss_streak < hold_frames:
                decay = max(hold_min_decay, 1.0 - (miss_streak / hold_frames))
                hold_v_left = last_v_left * decay
                hold_v_right = last_v_right * decay
                _, _, m3_hold, m4_hold = diff_op.apply(hold_v_left, hold_v_right)
                burst.send(PAN_CENTER, TILT_CENTER, 80, 0.0, 0.0, m3_hold, m4_hold)
                if tick % 30 == 0:
                    print("--- sin pelota (hold {:.2f}) ---".format(decay), flush=True)
            else:
                burst.send(PAN_CENTER, TILT_CENTER, 80, 0.0, 0.0, 0.0, 0.0)
                if tick % 30 == 0:
                    print("--- sin pelota ---", flush=True)
            miss_streak += 1
            last_turn *= 0.6
            tick += 1
            time.sleep(0.01)
            continue

        miss_streak = 0

        now = time.monotonic()
        dt = now - tick_start if tick_start else 0.01
        tick_start = now

        cx_raw = ball["cx"]
        r_raw = ball["r"]
        source = ball.get("source", "hsv")

        cx = kalman_cx.update(cx_raw)
        r = kalman_r.update(r_raw)

        vL, vR = controller.compute(cx, r, dt)
        v_cmd = (vL - vR) * 0.5
        turn_cmd = (vL + vR) * 0.5

        if source == "cache":
            v_cmd *= cache_speed_scale
            turn_cmd *= cache_turn_scale

        turn_cmd = max(-turn_abs_limit, min(turn_abs_limit, turn_cmd))
        delta_turn = turn_cmd - last_turn
        delta_turn = max(-turn_rate_limit, min(turn_rate_limit, delta_turn))
        turn_cmd = last_turn + delta_turn

        vL = v_cmd + turn_cmd
        vR = -(v_cmd - turn_cmd)

        last_turn = turn_cmd
        last_v_left = vL
        last_v_right = vR

        _, _, m3, m4 = diff_op.apply(vL, vR)
        burst.send(PAN_CENTER, TILT_CENTER, 80, 0.0, 0.0, m3, m4)

        if tick % 10 == 0:
            dist_e = (controller.f_eff / r - controller.f_eff / controller.r_desired) / (controller.f_eff / controller.r_desired) if r > 0 else 0
            v_proxy = (vL - vR) * 0.5
            turn_proxy = (vL + vR) * 0.5
            if abs(turn_proxy) < 3:
                direction = "RECTO"
            elif turn_proxy < 0:
                direction = "GIRA-IZQ"
            else:
                direction = "GIRA-DER"
            print(
                "src={} r={:.0f} cx={:.1f} r_s={:.1f} theta={:+.2f} dist={:+.2f} "
                "v={:.0f} w={:+.0f} vL={:.0f} vR={:.0f} {}".format(
                    source,
                    r_raw,
                    cx,
                    r,
                    (cx - half) / half,
                    dist_e,
                    v_proxy,
                    turn_proxy,
                    vL,
                    vR,
                    direction,
                ),
                flush=True,
            )

        tick += 1
        time.sleep(0.01)

except KeyboardInterrupt:
    pass
finally:
    burst.send(PAN_CENTER, TILT_CENTER, 200, 0.0, 0.0, 0.0, 0.0)
    time.sleep(0.2)
    vision.close()
    ser.close()
    print("Done.", flush=True)
