"""Visual Servoing Controller - FSM completa con busqueda estilo husky.ino.

Estados:
    TRACK   → chase con VisualServoController + Kalman + predictor + histeresis
    PREDICT → coast con BallPredictor (perdida reciente, 0.3s)
    RECOVER → giro inteligente segun ultima posicion (recuperarPersonaInteligente)
    MAP     → zigzag alternado con deteccion interrumpible (mapeoArea)
    AVOID   → retroceso por obstaculo ultrasonico

Override de kick: si el ultrasonico detecta <250mm pero la pelota esta visible
y cerca (radius >= 50px), suprime AVOID y avanza recto para patear.
"""

import os
import sys
import time

sys.path.insert(0, "/home/raspi/futbot-v2/src")
sys.stdout.reconfigure(line_buffering=True)

from vision import HybridVisionService
from ultrasonic import UltrasonicService
from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import PAN_CENTER, TILT_CENTER
from chase.ball_goal_controller import BallGoalController
from chase.visual_servo_controller import (
    BallPredictor,
    effective_goal_radius,
    is_confirmed_line,
    is_trackable_ball,
    Kalman1D,
    should_accept_goal_edge_ball,
    should_attack_through_line,
    should_hold_without_ball_near_line,
    should_hold_track_on_miss,
    TurnHysteresis,
)
from chase.search_operator import SearchOperator
import serial

TRACK = "TRACK"
PREDICT = "PREDICT"
RECOVER = "RECOVER"
MAP = "MAP"
AVOID = "AVOID"
WARMUP = "WARMUP"

WARMUP_TIMEOUT = 5.0
ATTACK_BLUE = os.environ.get("ATTACK_BLUE", "1").strip().lower() not in {"0", "false", "no"}
DIST_TRIGGER_MM = 250
RECOVER_MS = 1000
MAP_TURN_MS = 1200
MAP_PAUSE_MS = 300
AVOID_MS = 600
AVOID_SPEED = 110
M4_TRIM = float(os.environ.get("M4_TRIM", "1.0"))
BALL_VISIBLE_MIN_RADIUS = float(os.environ.get("BALL_VISIBLE_MIN_RADIUS", "8.0"))
GOAL_EDGE_BALL_MIN_RADIUS = float(os.environ.get("GOAL_EDGE_BALL_MIN_RADIUS", "5.0"))
TRACK_MISS_HOLD_FRAMES = int(os.environ.get("TRACK_MISS_HOLD_FRAMES", "8"))
TRACK_MISS_HOLD_SPEED_SCALE = float(os.environ.get("TRACK_MISS_HOLD_SPEED_SCALE", "0.75"))
TRACK_MISS_HOLD_TURN_SCALE = float(os.environ.get("TRACK_MISS_HOLD_TURN_SCALE", "0.55"))
LINE_STREAK_MIN = 2
LINE_RETREAT_SPEED = 150
LINE_RETREAT_MS = 400
LINE_TURN_MS = 300
LINE_COOLDOWN_FRAMES = 60


ser = serial.Serial("/dev/ttyAMA0", 1_000_000)
burst = BurstOperator(ser)
diff_op = DifferentialOperator()


def drive(vL, vR, dur_ms):
    _, _, m3, m4 = diff_op.apply(vL, vR)
    m4 *= M4_TRIM
    burst.send(PAN_CENTER, TILT_CENTER, dur_ms, 0.0, 0.0, m3, m4)

print("Iniciando sensores...", flush=True)
vision = HybridVisionService()
ultrasonic = UltrasonicService()
time.sleep(3)
frame_w = vision.frame_width
half = frame_w / 2
print("Listo. Frame={} centro={}".format(frame_w, half), flush=True)

controller = BallGoalController(frame_width=frame_w)

kalman_cx = Kalman1D(q=2.6, r=1.0)
kalman_r = Kalman1D(q=0.9, r=1.5)
predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
search = SearchOperator()

last_v_left = 0.0
last_v_right = 0.0
last_turn = 0.0
prev_hys_sign = 0
miss_streak = 0

predict_timeout_s = 0.50

predict_turn_abs_limit = 55.0
cache_turn_scale = 0.30
cache_speed_scale = 0.80
prediction_speed_scale = 0.70
prediction_turn_scale = 0.50

tick = 0
tick_start = time.monotonic()
fps_start = time.monotonic()
fps_count = 0
state = WARMUP
warmup_start = time.monotonic()
loss_start_t = 0.0
last_valid_w = 0.0
last_valid_v = 0.0

last_valid_cx = 0.0
last_seen_t = 0.0

search_phase_start = 0.0
search_step_index = 0
num_vueltas = 0
search_burst_sent = False
search_phase = "turn"
recover_done = False

last_ultra_read = 0.0
ultra_dist_mm = None
ultra_history = []
ULTRA_EVERY_SEC = 0.2

line_streak = 0
line_cooldown = 0
line_phase = ""
line_phase_start = 0.0
kick_streak = 0
last_kick_r = 0.0
ball_streak = 0
last_goal_cx = None
last_goal_ts = 0.0

try:
    while True:
        snap = vision.tick()
        ball = snap.get("ball")
        now = time.monotonic()

        if now - last_ultra_read >= ULTRA_EVERY_SEC:
            dto = ultrasonic.tick()
            if dto.distance_mm is not None:
                ultra_history.append(dto.distance_mm)
                if len(ultra_history) > 5:
                    ultra_history.pop(0)
            last_ultra_read = now

        if ball is None:
            source = "none"
            cx = None
            r = None
        else:
            source = ball.get("source", "hsv")
            cx = ball["cx"]
            r = ball["r"]

        target_key = "blue" if ATTACK_BLUE else "yellow"
        target_goal_cx_now = snap.get("goals", {}).get("{}_cx".format(target_key))

        if is_trackable_ball(
            ball,
            min_radius=BALL_VISIBLE_MIN_RADIUS,
        ) or should_accept_goal_edge_ball(
            ball,
            goal_cx=target_goal_cx_now,
            min_radius=GOAL_EDGE_BALL_MIN_RADIUS,
        ):
            ball_streak += 1
        else:
            ball_streak = 0

        ball_visible = ball_streak >= 1

        if line_cooldown > 0:
            line_cooldown -= 1
            line_streak = 0

        line_blocking = False

        if line_phase == "retreat":
            if now - line_phase_start >= LINE_RETREAT_MS / 1000.0:
                if line_cx is not None and line_cx < half:
                    drive(110, 55, LINE_TURN_MS)
                else:
                    drive(-55, -110, LINE_TURN_MS)
                if tick % 5 == 0:
                    print(
                        "--- LINE turn dir={} ---".format(
                            "right" if (line_cx is not None and line_cx < half)
                            else "left"
                        ),
                        flush=True,
                    )
                line_phase = "turn"
                line_phase_start = now

        elif line_phase == "turn":
            if now - line_phase_start >= LINE_TURN_MS / 1000.0:
                line_phase = "escape"
                line_phase_start = now
                if tick % 5 == 0:
                    print("--- LINE escape stop/no-forward ---", flush=True)

        elif line_phase == "escape":
            if now - line_phase_start >= 0.05:
                line_cooldown = LINE_COOLDOWN_FRAMES
                line_streak = 0
                line_phase = ""
                state = RECOVER
                search_phase_start = now
                search_burst_sent = False
                recover_done = False
                miss_streak = 0

        if line_cooldown <= 0 and line_phase == "":
            line_snap = snap.get("line", {})
            line_detected = bool(line_snap.get("detected", False))
            line_cx = line_snap.get("cx")
            line_pixels = line_snap.get("pixels", 0)
            if line_detected:
                line_streak += 1
                if tick % 5 == 0:
                    print(
                        "--- LINE streak={} cx={} pixels={} ---".format(
                            line_streak,
                            line_cx if line_cx is not None else "none",
                            line_pixels,
                        ),
                        flush=True,
                    )
            else:
                line_streak = 0

            line_confirmed = is_confirmed_line(line_streak, LINE_STREAK_MIN)
            if line_confirmed:
                if should_attack_through_line(
                    ball,
                    goal_cx=target_goal_cx_now,
                    line_detected=True,
                    min_radius=BALL_VISIBLE_MIN_RADIUS,
                ):
                    if tick % 5 == 0:
                        print(
                            "--- LINE suppressed: ball+goal attack cx={} goal={} ---".format(
                                cx,
                                int(target_goal_cx_now),
                            ),
                            flush=True,
                        )
                    line_streak = 0
                else:
                    line_blocking = True
                    print(
                        "--- LINE DETECTED retreating {}ms ---".format(
                            LINE_RETREAT_MS
                        ),
                        flush=True,
                    )
                    drive(-LINE_RETREAT_SPEED, LINE_RETREAT_SPEED, LINE_RETREAT_MS)
                    line_phase = "retreat"
                    line_phase_start = now

        should_avoid = (
            len(ultra_history) >= 5
            and (sum(ultra_history) / len(ultra_history)) <= DIST_TRIGGER_MM
            and not ball_visible
        )
        ultra_dist_mm = (
            int(sum(ultra_history) / len(ultra_history))
            if len(ultra_history) >= 5
            else None
        )

        if should_avoid and ball_visible and r is not None and r >= 25:
            should_avoid = False

        if should_avoid and state not in (AVOID, WARMUP):
            if tick % 30 == 0:
                print(
                    "--- OBSTACULO dist={}mm entrando AVOID ---".format(
                        ultra_dist_mm
                    ),
                    flush=True,
                )
            state = AVOID
            search_phase_start = now
            search_burst_sent = False
            line_phase = ""

        if line_phase:
            tick += 1
            time.sleep(0.01)
            continue

        if should_hold_without_ball_near_line(
            ball_visible,
            bool(snap.get("line", {}).get("detected", False)),
            line_cooldown,
        ):
            burst.send(PAN_CENTER, TILT_CENTER, 80, 0.0, 0.0, 0.0, 0.0)
            if tick % 10 == 0:
                print(
                    "--- LINE hold: no ball, no blind search ---",
                    flush=True,
                )
            tick += 1
            time.sleep(0.01)
            continue

        if ball_visible and not line_phase:
            miss_streak = 0
            if state in (PREDICT, RECOVER, MAP, AVOID, WARMUP):
                if tick % 10 == 0:
                    print(
                        "--- pelota recuperada src={} r={:.0f} → TRACK ---".format(
                            source, r
                        ),
                        flush=True,
                    )
                state = TRACK
                loss_start_t = 0.0
                num_vueltas = 0
                search_step_index = 0
                prev_hys_sign = 0
                last_turn = 0

        if state == WARMUP:
            elapsed_warmup = now - warmup_start
            if ball_visible or elapsed_warmup >= WARMUP_TIMEOUT:
                reason = "ball" if ball_visible else "timeout"
                print(
                    "--- WARMUP done t={:.1f}s ({}) -> RECOVER ---".format(
                        elapsed_warmup, reason
                    ),
                    flush=True,
                )
                state = RECOVER
                search_phase_start = now
                search_burst_sent = False
                recover_done = False

        elif state == TRACK:
            if ball_visible and not line_phase:
                dt = now - tick_start if tick_start else 0.01
                tick_start = now

                cx_raw = ball["cx"]
                r_raw = ball["r"]

                cx_f = kalman_cx.update(cx_raw)
                r_f = kalman_r.update(r_raw)

                jump_rejected = False
                if last_valid_cx > 0 and source != "cache":
                    age = now - last_seen_t
                    max_jump = 120.0 + 300.0 * age
                    if abs(cx_f - last_valid_cx) > max_jump:
                        jump_rejected = True

                if source in ("hsv", "yolo") and not jump_rejected:
                    predictor.update(cx_f, r_f, now)
                    last_valid_cx = cx_f
                    last_seen_t = now

                theta_raw = (cx_f - half) / half
                theta_filtered = hysteresis.filter(theta_raw)
                cx_filtered = half + half * theta_filtered

                if not jump_rejected:
                    _, r_eff = predictor.predict(0.0)
                else:
                    _, r_eff = cx_f, r_f
                r_eff = effective_goal_radius(r_raw, r_eff)

                goals = snap.get("goals", {})
                goal_cx = goals.get("{}_cx".format(target_key))
                if goal_cx is not None:
                    last_goal_cx = goal_cx
                    last_goal_ts = now
                elif now - last_goal_ts > 2.0:
                    last_goal_cx = None

                command = controller.compute(
                    ball_cx=cx_filtered,
                    ball_r=r_eff,
                    goal_cx=last_goal_cx,
                    line_detected=line_blocking,
                )
                vL = command.v_left
                vR = command.v_right
                v_cmd = (vL - vR) * 0.5
                turn_cmd = (vL + vR) * 0.5

                if source == "cache":
                    v_cmd *= cache_speed_scale
                    turn_cmd *= cache_turn_scale
                vL = v_cmd + turn_cmd
                vR = -(v_cmd - turn_cmd)

                last_valid_v = v_cmd
                last_valid_w = turn_cmd
                last_turn = turn_cmd
                last_v_left = vL
                last_v_right = vR

                if tick % 10 == 0:
                    print(
                        "src={} r={:.0f} cx={:.1f} r_s={:.1f} theta={:+.2f} "
                        "v={:.0f} w={:+.0f} vL={:.0f} vR={:.0f} mode={} "
                        "hys={} goal={}".format(
                            source,
                            r_raw,
                            cx_filtered,
                            r_eff,
                            theta_filtered,
                            v_cmd,
                            turn_cmd,
                            vL,
                            vR,
                            command.mode,
                            hysteresis,
                            "%.0f" % last_goal_cx if last_goal_cx is not None else "none",
                        ),
                        flush=True,
                    )

                drive(vL, vR, 80)
            else:
                if last_valid_v > 0 or last_valid_w != 0:
                    miss_streak += 1
                    if should_hold_track_on_miss(
                        miss_streak,
                        max_miss_frames=TRACK_MISS_HOLD_FRAMES,
                    ):
                        decay = max(
                            0.25,
                            1.0 - miss_streak / float(TRACK_MISS_HOLD_FRAMES + 1),
                        )
                        v_cmd = last_valid_v * TRACK_MISS_HOLD_SPEED_SCALE * decay
                        turn_cmd = last_valid_w * TRACK_MISS_HOLD_TURN_SCALE * decay
                        vL = v_cmd + turn_cmd
                        vR = -(v_cmd - turn_cmd)
                        drive(vL, vR, 80)
                        if tick % 10 == 0:
                            print(
                                "--- TRACK hold miss={} v={:.0f} w={:+.0f} ---".format(
                                    miss_streak,
                                    v_cmd,
                                    turn_cmd,
                                ),
                                flush=True,
                            )
                    else:
                        state = PREDICT
                        loss_start_t = now
                else:
                    state = RECOVER
                    search_phase_start = now
                    search_burst_sent = False
                    recover_done = False

        elif state == PREDICT:
            elapsed = now - loss_start_t
            if elapsed < predict_timeout_s:
                decay = max(0.3, 1.0 - elapsed / predict_timeout_s)
                pred_v = last_valid_v * decay * prediction_speed_scale
                pred_w = last_valid_w * decay * prediction_turn_scale
                pred_w = max(
                    -predict_turn_abs_limit * 0.4,
                    min(predict_turn_abs_limit * 0.4, pred_w),
                )
                vL = pred_v + pred_w
                vR = -(pred_v - pred_w)
                drive(vL, vR, 80)
                if tick % 15 == 0:
                    print(
                        "--- perdida PREDICT t={:.2f}s ---".format(elapsed), flush=True
                    )
            else:
                state = RECOVER
                search_phase_start = now
                search_burst_sent = False
                recover_done = False

            miss_streak += 1
            last_turn *= 0.6

        elif state == RECOVER:
            if not recover_done:
                if not search_burst_sent:
                    direction, vL, vR = search.recover_step(
                        last_valid_cx, frame_w
                    )
                    drive(vL, vR, RECOVER_MS)
                    search_burst_sent = True
                    search_phase_start = now
                    if tick % 5 == 0:
                        print(
                            "--- RECOVER dir={} last_cx={:.0f} ---".format(
                                direction, last_valid_cx
                            ),
                            flush=True,
                        )

                if now - search_phase_start >= RECOVER_MS / 1000.0:
                    recover_done = True
                    state = MAP
                    search_phase = "turn"
                    search_step_index = 0
                    num_vueltas = 0
                    search_burst_sent = False
                    search_phase_start = now

            miss_streak += 1
            last_turn *= 0.6

        elif state == MAP:
            if search_phase == "turn":
                if not search_burst_sent:
                    direction, vL, vR = search.map_step(
                        search_step_index, last_valid_cx, frame_w
                    )
                    drive(vL, vR, MAP_TURN_MS)
                    search_burst_sent = True
                    search_phase_start = now
                    if tick % 10 == 0:
                        print(
                            "--- MAP paso={} dir={} vueltas={} ---".format(
                                search_step_index, direction, num_vueltas
                            ),
                            flush=True,
                        )

                if now - search_phase_start >= MAP_TURN_MS / 1000.0:
                    burst.send(
                        PAN_CENTER, TILT_CENTER, 100, 0.0, 0.0, 0.0, 0.0
                    )
                    search_phase = "pause"
                    search_phase_start = now

            elif search_phase == "pause":
                if now - search_phase_start >= MAP_PAUSE_MS / 1000.0:
                    search_step_index += 1
                    num_vueltas += 1
                    search_burst_sent = False
                    search_phase = "turn"
                    search_phase_start = now

                    if num_vueltas >= 5:
                        if tick % 5 == 0:
                            print(
                                "--- MAP agotado vueltas={} → AVOID ---".format(
                                    num_vueltas
                                ),
                                flush=True,
                            )
                        state = AVOID
                        search_phase_start = now
                        search_burst_sent = False

            miss_streak += 1
            last_turn *= 0.6

        elif state == AVOID:
            if not search_burst_sent:
                drive(-AVOID_SPEED, AVOID_SPEED, AVOID_MS)
                search_burst_sent = True
                search_phase_start = now
                print(
                    "--- AVOID retrocediendo {}ms ---".format(AVOID_MS),
                    flush=True,
                )

            if now - search_phase_start >= AVOID_MS / 1000.0:
                state = MAP
                search_phase = "turn"
                search_step_index = 0
                num_vueltas = 0
                search_burst_sent = False
                search_phase_start = now
                if tick % 5 == 0:
                    print("--- AVOID completo → RECOVER ---", flush=True)

            miss_streak += 1
            last_turn *= 0.6

        if tick % 30 == 0:
            goals = snap.get("goals", {})
            line_diag = snap.get("line", {})
            print(
                "goals yellow={} blue={} line_det={} line_pix={}".format(
                    goals.get("yellow", False),
                    goals.get("blue", False),
                line_diag.get("detected", False),
                line_diag.get("pixels", 0),
            ),
            flush=True,
        )
        if tick % 30 == 0:
            hsv_dbg = snap.get("debug", {}).get("hsv", {})
            print(
                "HSV mode={} v_median={} hue_center={:.1f} exp={}".format(
                    hsv_dbg.get("mode", "?"),
                    hsv_dbg.get("v_median", "?"),
                    float(hsv_dbg.get("hue_center", 0)),
                    hsv_dbg.get("exposure", "?"),
                ),
                flush=True,
            )

        fps_count += 1
        if now - fps_start >= 1.0:
            fps = fps_count / (now - fps_start)
            fps_count = 0
            fps_start = now
            print(
                "loop_fps={:.1f} state={} ball={} line={} goal={}".format(
                    fps,
                    state,
                    "yes" if ball_visible else "no",
                    "yes" if snap.get("line", {}).get("detected", False) else "no",
                    "yes" if last_goal_cx is not None else "no",
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
    ultrasonic.close()
    vision.close()
    ser.close()
    print("Done.", flush=True)
