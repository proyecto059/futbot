"""Calibration: chase with trial tracking.

Place ball at specific positions. Script tracks convergence per trial.
Reports: initial θ, initial r, time to KICK, final θ.
"""
import sys
import time

sys.path.insert(0, "/home/raspi/futbot-v2/src")
sys.stdout.reconfigure(line_buffering=True)

from vision import HybridVisionService
from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import PAN_CENTER, TILT_CENTER
import serial

FWD = 100
TURN_GAIN = 30
DRIFT_COMP = 12
FADE_FACTOR = 4.0
DEAD_ZONE = 0.08
MAX_TURN_RATIO = 0.70
KICK_R = 100
BURST_MS = 80
TRIAL_LOSS_S = 2.0
TRIAL_TIMEOUT_S = 15.0

ser = serial.Serial("/dev/ttyAMA0", 1_000_000)
burst = BurstOperator(ser)
diff_op = DifferentialOperator()


def drive(vL, vR, dur_ms):
    _, _, m3, m4 = diff_op.apply(vL, vR)
    burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)


print("Iniciando vision...", flush=True)
vision = HybridVisionService()
time.sleep(3)
frame_w = vision.frame_width
half = frame_w / 2
print("Listo. Frame={} half={}".format(frame_w, half), flush=True)
print("=" * 60, flush=True)
print("Coloca la pelota y espera. CTRL-C para parar.", flush=True)
print("=" * 60, flush=True)

tick = 0
kick_count = 0
in_trial = False
trial_start = 0.0
trial_init_theta = 0.0
trial_init_r = 0.0
trial_num = 0
last_seen_t = 0.0
ball_absent_t = 0.0
ball_was_absent = True
theta_samples = []

try:
    while True:
        snap = vision.tick()
        ball = snap.get("ball")
        now = time.monotonic()

        if ball is not None and ball["r"] >= 12:
            src = ball.get("source", "?")
            if src in ("hsv", "yolo"):
                cx = ball["cx"]
                r = ball["r"]
                theta = (cx - half) / half

                if abs(theta) < DEAD_ZONE:
                    theta = 0.0

                eff_theta = theta
                if abs(theta) > DEAD_ZONE:
                    eff_theta = (1.0 if theta > 0 else -1.0) * (abs(theta) ** 0.6)

                turn = TURN_GAIN * eff_theta
                max_turn = FWD * MAX_TURN_RATIO
                turn = max(-max_turn, min(max_turn, turn))

                fade = max(0.0, 1.0 - abs(theta) * FADE_FACTOR)
                drift = DRIFT_COMP * fade

                vL = FWD + turn
                vR_base = FWD - turn
                vR = -vR_base + drift

                if not in_trial or ball_was_absent:
                    trial_num += 1
                    in_trial = True
                    trial_start = now
                    trial_init_theta = theta
                    trial_init_r = r
                    theta_samples = []
                    kick_count = 0
                    side = "LEFT" if theta < 0 else "RIGHT" if theta > 0 else "CENTER"
                    print(
                        "\n>>> TRIAL #{} START side={} θ0={:+.3f} r0={:.0f}".format(
                            trial_num, side, theta, r
                        ),
                        flush=True,
                    )

                theta_samples.append(theta)
                last_seen_t = now
                ball_was_absent = False

                if r >= KICK_R:
                    kick_count += 1
                    if kick_count >= 3:
                        vL = 160
                        vR = -160
                        tag = "KICK"
                    else:
                        tag = "KICK?"
                else:
                    kick_count = 0
                    tag = ""

                drive(vL, vR, BURST_MS)

                elapsed = now - trial_start

                if kick_count >= 3 and tag == "KICK":
                    min_t = min(theta_samples) if theta_samples else 0
                    max_t = max(theta_samples) if theta_samples else 0
                    print(
                        "\n<<< TRIAL #{} KICK! t={:.1f}s θ0={:+.3f}→{:+.3f} "
                        "r0={:.0f} θ_range=[{:+.3f},{:+.3f}] samples={}".format(
                            trial_num,
                            elapsed,
                            trial_init_theta,
                            theta,
                            trial_init_r,
                            min_t,
                            max_t,
                            len(theta_samples),
                        ),
                        flush=True,
                    )
                    in_trial = False
                    kick_count = 0
                    theta_samples = []

                if tick % 5 == 0:
                    print(
                        "  t={:.1f} θ={:+.3f} r={:.0f} fade={:.2f} "
                        "drift={:.1f} vL={:.0f} vR={:.0f} {}".format(
                            elapsed, theta, r, fade, drift, vL, vR, tag
                        ),
                        flush=True,
                    )

                if in_trial and elapsed > TRIAL_TIMEOUT_S:
                    print(
                        "\n<<< TRIAL #{} TIMEOUT {:.0f}s θ={:+.3f} r={:.0f}".format(
                            trial_num, elapsed, theta, r
                        ),
                        flush=True,
                    )
                    in_trial = False
                    theta_samples = []
            else:
                last_seen_t = now
        else:
            if in_trial:
                elapsed = now - trial_start
                absent = now - last_seen_t
                if absent > TRIAL_LOSS_S:
                    min_t = min(theta_samples) if theta_samples else 0
                    max_t = max(theta_samples) if theta_samples else 0
                    print(
                        "\n<<< TRIAL #{} LOST t={:.1f}s absent={:.1f}s "
                        "θ0={:+.3f} r0={:.0f} θ_range=[{:+.3f},{:+.3f}]".format(
                            trial_num,
                            elapsed,
                            absent,
                            trial_init_theta,
                            trial_init_r,
                            min_t,
                            max_t,
                        ),
                        flush=True,
                    )
                    in_trial = False
                    theta_samples = []
            ball_was_absent = True

        tick += 1
        time.sleep(0.01)

except KeyboardInterrupt:
    pass
finally:
    burst.send(PAN_CENTER, TILT_CENTER, 200, 0.0, 0.0, 0.0, 0.0)
    time.sleep(0.2)
    vision.close()
    ser.close()
    print("\nDone. {} trials.".format(trial_num), flush=True)
