"""Visual Servoing Controller - FSM completa con busqueda estilo husky.ino.

Estados:
    TRACK   → chase con VisualServoController + Kalman + predictor + histeresis
    PREDICT → coast con BallPredictor (perdida reciente, 0.3s)
    LOCAL_REACQUIRE → busqueda corta usando ultima posicion visual de pelota
    FIELD_SEARCH    → cobertura por sectores cuando no hay memoria confiable
"""

import os
import sys
import time

sys.path.insert(0, "/home/raspi/futbot-v2/src")
sys.stdout.reconfigure(line_buffering=True)

from vision import HybridVisionService
from motors.operators.burst_operator import BurstOperator
from motors.operators.differential_operator import DifferentialOperator
from motors.utils.motor_constants import PAN_CENTER, TILT_CENTER
from chase.ball_goal_controller import BallGoalController
from chase.attack_geometry import scored_goal_color_after_push
from chase.visual_servo_controller import (
    BallPredictor,
    effective_goal_radius,
    is_confirmed_ball_streak,
    is_confirmed_line,
    is_trackable_ball,
    Kalman1D,
    should_accept_ball_in_attack_context,
    should_accept_goal_edge_ball,
    should_accept_goal_in_attack_context,
    should_allow_initial_track,
    should_allow_push_commit,
    should_accept_tracked_ball_measurement,
    should_attack_through_line,
    should_commit_push,
    should_continue_dribble_prediction,
    should_continue_dribble_push,
    should_hold_without_ball_near_line,
    should_hold_track_on_miss,
    should_goal_guided_coast,
    should_reset_track_after_jump_rejections,
    should_use_goal_memory_for_attack,
    update_goal_flip_candidate,
    update_goal_memory,
    update_goal_y_memory,
    update_confirmation_streak,
    TurnHysteresis,
)
from chase.search_operator import SearchOperator
import serial

TRACK = "TRACK"
PREDICT = "PREDICT"
LOCAL_REACQUIRE = "LOCAL_REACQUIRE"
FIELD_SEARCH = "FIELD_SEARCH"
WARMUP = "WARMUP"
CELEBRATE_360 = "CELEBRATE_360"
STOPPED = "STOPPED"

WARMUP_TIMEOUT = 5.0
ATTACK_BLUE = os.environ.get("ATTACK_BLUE", "1").strip().lower() not in {"0", "false", "no"}
LOCAL_REACQUIRE_MS = int(os.environ.get("LOCAL_REACQUIRE_MS", "650"))
LOCAL_MEMORY_SEC = float(os.environ.get("LOCAL_MEMORY_SEC", "1.4"))
FIELD_SEARCH_MOVE_MS = int(os.environ.get("FIELD_SEARCH_MOVE_MS", "750"))
FIELD_SEARCH_PAUSE_MS = int(os.environ.get("FIELD_SEARCH_PAUSE_MS", "180"))
M4_TRIM = float(os.environ.get("M4_TRIM", "1.0"))
BALL_VISIBLE_MIN_RADIUS = float(os.environ.get("BALL_VISIBLE_MIN_RADIUS", "5.5"))
BALL_CONFIRM_FRAMES = int(os.environ.get("BALL_CONFIRM_FRAMES", "3"))
PUSH_CONFIRM_FRAMES = int(os.environ.get("PUSH_CONFIRM_FRAMES", "5"))
SEARCH_MAX_INITIAL_BALL_RADIUS = float(os.environ.get("SEARCH_MAX_INITIAL_BALL_RADIUS", "45.0"))
GOAL_EDGE_BALL_MIN_RADIUS = float(os.environ.get("GOAL_EDGE_BALL_MIN_RADIUS", "8.0"))
TRACK_MISS_HOLD_FRAMES = int(os.environ.get("TRACK_MISS_HOLD_FRAMES", "8"))
TRACK_MISS_HOLD_SPEED_SCALE = float(os.environ.get("TRACK_MISS_HOLD_SPEED_SCALE", "0.75"))
TRACK_MISS_HOLD_TURN_SCALE = float(os.environ.get("TRACK_MISS_HOLD_TURN_SCALE", "0.55"))
PUSH_COMMIT_MS = int(os.environ.get("PUSH_COMMIT_MS", "600"))
DRIBBLE_AFTER_PUSH_MS = int(os.environ.get("DRIBBLE_AFTER_PUSH_MS", "1200"))
DRIBBLE_MIN_RADIUS = float(os.environ.get("DRIBBLE_MIN_RADIUS", "14.0"))
DRIBBLE_PREDICT_MAX_AGE = float(os.environ.get("DRIBBLE_PREDICT_MAX_AGE", "0.45"))
GOAL_COAST_MAX_BALL_AGE = float(os.environ.get("GOAL_COAST_MAX_BALL_AGE", "0.8"))
GOAL_COAST_MAX_GOAL_AGE = float(os.environ.get("GOAL_COAST_MAX_GOAL_AGE", "1.2"))
GOAL_COAST_MIN_BALL_RADIUS = float(os.environ.get("GOAL_COAST_MIN_BALL_RADIUS", "10.0"))
GOAL_COAST_MAX_SPEED = float(os.environ.get("GOAL_COAST_MAX_SPEED", "70.0"))
GOAL_COAST_MAX_TURN = float(os.environ.get("GOAL_COAST_MAX_TURN", "30.0"))
GOAL_CONFIRM_FRAMES = int(os.environ.get("GOAL_CONFIRM_FRAMES", "5"))
SPIN_360_MS = int(os.environ.get("SPIN_360_MS", "4000"))
SPIN_360_SPEED = float(os.environ.get("SPIN_360_SPEED", "120"))
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
jump_reject_streak = 0

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
last_valid_r = 0.0
last_seen_t = 0.0

search_phase_start = 0.0
search_step_index = 0
search_burst_sent = False
search_phase = "move"

line_streak = 0
line_cooldown = 0
line_phase = ""
line_phase_start = 0.0
last_line_cx = None
kick_streak = 0
last_kick_r = 0.0
ball_streak = 0
last_goal_cx = None
last_goal_cy = None
last_goal_ts = 0.0
pending_goal_flip_cx = None
pending_goal_flip_count = 0
pending_goal_flip_ts = 0.0
push_until = 0.0
dribble_until = 0.0
last_push_v_left = 0.0
last_push_v_right = 0.0
goal_scored_streak = 0
goal_scored_color = None
celebrate_start = 0.0

try:
    while True:
        snap = vision.tick()
        ball = snap.get("ball")
        now = time.monotonic()

        if ball is None:
            source = "none"
            cx = None
            r = None
        else:
            source = ball.get("source", "hsv")
            cx = ball["cx"]
            r = ball["r"]

        target_key = "blue" if ATTACK_BLUE else "yellow"
        opponent_key = "yellow" if ATTACK_BLUE else "blue"
        goals_now = snap.get("goals", {})
        target_goal_visible = bool(goals_now.get(target_key, False))
        opponent_goal_visible = bool(goals_now.get(opponent_key, False))
        target_goal_cx_raw = goals_now.get("{}_cx".format(target_key))
        target_goal_cy_raw = goals_now.get("{}_cy".format(target_key))
        target_goal_bbox_raw = goals_now.get("{}_bbox".format(target_key))
        if not should_accept_goal_in_attack_context(
            target_goal_cx_raw,
            target_goal_bbox_raw,
            frame_w,
        ):
            target_goal_visible = False
            target_goal_cx_raw = None
            target_goal_cy_raw = None
        remembered_goal_cx, remembered_goal_ts, goal_accepted = update_goal_memory(
            target_goal_cx_raw,
            last_goal_cx,
            last_goal_ts,
            now,
            frame_w,
        )
        goal_conflict = False
        if target_goal_cx_raw is None or goal_accepted:
            pending_goal_flip_cx = None
            pending_goal_flip_count = 0
            pending_goal_flip_ts = 0.0
        elif not goal_accepted:
            goal_conflict = True
            (
                pending_goal_flip_cx,
                pending_goal_flip_count,
                pending_goal_flip_ts,
                goal_flip_accepted,
                ) = update_goal_flip_candidate(
                    target_goal_cx_raw,
                    remembered_goal_cx,
                    pending_goal_flip_cx,
                    pending_goal_flip_count,
                    pending_goal_flip_ts,
                    now,
                    frame_w,
                    remembered_ts=remembered_goal_ts,
                )
            if goal_flip_accepted:
                remembered_goal_cx = float(target_goal_cx_raw)
                remembered_goal_ts = now
                goal_accepted = True
                goal_conflict = False
                pending_goal_flip_cx = None
                pending_goal_flip_count = 0
                pending_goal_flip_ts = 0.0
                print(
                    "--- GOAL flip accepted raw={:.0f} ---".format(
                        float(target_goal_cx_raw),
                    ),
                    flush=True,
                )
        if (
            target_goal_cx_raw is not None
            and remembered_goal_cx is not None
            and not goal_accepted
            and tick % 10 == 0
        ):
            print(
                "--- GOAL jump rejected raw={:.0f} keep={:.0f} ---".format(
                    float(target_goal_cx_raw),
                    float(remembered_goal_cx),
                ),
                flush=True,
            )
        last_goal_cx = remembered_goal_cx
        last_goal_ts = remembered_goal_ts
        last_goal_cy = update_goal_y_memory(
            target_goal_cy_raw,
            last_goal_cy,
            remembered_goal_cx,
            goal_accepted,
        )
        use_goal_memory = should_use_goal_memory_for_attack(
            target_goal_visible,
            opponent_goal_visible,
            goal_conflict=goal_conflict,
        )
        target_goal_cx_now = last_goal_cx if use_goal_memory else None
        target_goal_cy_now = last_goal_cy if use_goal_memory else None

        if state not in (CELEBRATE_360, STOPPED):
            scored_color_now = scored_goal_color_after_push(
                ball,
                goals_now,
                target_key,
                push_until=push_until,
                now=now,
            )

            if scored_color_now is not None:
                if scored_color_now == goal_scored_color:
                    goal_scored_streak += 1
                else:
                    goal_scored_color = scored_color_now
                    goal_scored_streak = 1
            else:
                goal_scored_streak = 0
                goal_scored_color = None

        if state not in (CELEBRATE_360, STOPPED) and goal_scored_streak >= GOAL_CONFIRM_FRAMES:
            state = CELEBRATE_360
            celebrate_start = now
            push_until = 0.0
            dribble_until = 0.0
            print("--- GOAL scored color={} -> CELEBRATE_360 ---".format(goal_scored_color), flush=True)

        accept_ball_context = should_accept_ball_in_attack_context(
            ball,
            target_goal_visible=target_goal_visible,
            opponent_goal_visible=opponent_goal_visible,
        )
        if not accept_ball_context and ball is not None:
            ball_streak = 0
            miss_streak = 0
            jump_reject_streak = 0
            last_valid_w = 0.0
            last_valid_v = 0.0
            last_valid_cx = 0.0
            last_valid_r = 0.0
            last_seen_t = 0.0
            predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
            kalman_cx = Kalman1D(q=2.6, r=1.0)
            kalman_r = Kalman1D(q=0.9, r=1.5)
            hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
            if tick % 10 == 0:
                print(
                    "--- BALL rejected: opponent goal only cx={:.0f} r={:.0f} ---".format(
                        float(cx),
                        float(r),
                    ),
                    flush=True,
                )
        raw_ball_detected = accept_ball_context and (is_trackable_ball(
            ball,
            min_radius=BALL_VISIBLE_MIN_RADIUS,
        ) or should_accept_goal_edge_ball(
            ball,
            goal_cx=target_goal_cx_now,
            min_radius=GOAL_EDGE_BALL_MIN_RADIUS,
        ))
        ball_streak = update_confirmation_streak(ball_streak, raw_ball_detected)

        has_recent_memory = last_seen_t > 0.0 and (now - last_seen_t) <= LOCAL_MEMORY_SEC
        ball_confirmed = is_confirmed_ball_streak(
            ball_streak,
            min_frames=BALL_CONFIRM_FRAMES,
        )
        if state == TRACK or has_recent_memory:
            ball_visible = raw_ball_detected and ball_confirmed
        else:
            ball_visible = should_allow_initial_track(
                ball,
                streak=ball_streak,
                min_streak=BALL_CONFIRM_FRAMES,
                max_initial_radius=SEARCH_MAX_INITIAL_BALL_RADIUS,
            )
        push_commit_active = should_commit_push(now, push_until)

        if state == STOPPED:
            burst.send(PAN_CENTER, TILT_CENTER, 120, 0.0, 0.0, 0.0, 0.0)
            tick += 1
            time.sleep(0.05)
            continue

        if state == CELEBRATE_360:
            elapsed_ms = int((now - celebrate_start) * 1000.0)
            if elapsed_ms < SPIN_360_MS:
                drive(SPIN_360_SPEED, SPIN_360_SPEED, 80)
                if tick % 15 == 0:
                    print(
                        "--- CELEBRATE_360 color={} t={}ms/{}ms ---".format(
                            goal_scored_color,
                            elapsed_ms,
                            SPIN_360_MS,
                        ),
                        flush=True,
                    )
            else:
                burst.send(PAN_CENTER, TILT_CENTER, 200, 0.0, 0.0, 0.0, 0.0)
                state = STOPPED
                print("--- CELEBRATE_360 done -> STOPPED ---", flush=True)
            tick += 1
            time.sleep(0.01)
            continue

        if line_cooldown > 0 and not push_commit_active:
            line_cooldown -= 1
            line_streak = 0

        line_blocking = False
        dribble_prediction_active = should_continue_dribble_prediction(
            goal_cx=last_goal_cx,
            now=now,
            dribble_until=dribble_until,
            last_seen_t=last_seen_t,
            last_valid_r=last_valid_r,
            min_radius=DRIBBLE_MIN_RADIUS,
            max_age_s=DRIBBLE_PREDICT_MAX_AGE,
        )

        if push_commit_active:
            drive(last_push_v_left, last_push_v_right, 80)
            if tick % 10 == 0:
                remaining_ms = int(max(0.0, push_until - now) * 1000.0)
                print(
                    "--- PUSH commit remaining={}ms vL={:.0f} vR={:.0f} ---".format(
                        remaining_ms,
                        last_push_v_left,
                        last_push_v_right,
                    ),
                    flush=True,
                )
            tick += 1
            time.sleep(0.01)
            continue

        if line_phase == "retreat":
            if now - line_phase_start >= LINE_RETREAT_MS / 1000.0:
                if last_line_cx is not None and last_line_cx < half:
                    drive(110, 55, LINE_TURN_MS)
                else:
                    drive(-55, -110, LINE_TURN_MS)
                if tick % 5 == 0:
                    print(
                        "--- LINE turn dir={} ---".format(
                            "right" if (last_line_cx is not None and last_line_cx < half)
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
                state = LOCAL_REACQUIRE if has_recent_memory else FIELD_SEARCH
                search_phase_start = now
                search_burst_sent = False
                miss_streak = 0

        if line_cooldown <= 0 and line_phase == "":
            line_snap = snap.get("line", {})
            line_detected = bool(line_snap.get("detected", False))
            line_cx = line_snap.get("cx")
            line_cy = line_snap.get("cy")
            line_pixels = line_snap.get("pixels", 0)
            if line_detected:
                if line_cx is not None:
                    last_line_cx = line_cx
                line_streak += 1
                if tick % 5 == 0:
                    print(
                        "--- LINE streak={} cx={} pixels={} ---".format(
                            line_streak,
                            "{:.0f} cy={:.0f}".format(line_cx, line_cy)
                            if line_cx is not None and line_cy is not None
                            else line_cx if line_cx is not None else "none",
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
                    allow_dribble_prediction=dribble_prediction_active and use_goal_memory,
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

        if line_phase:
            tick += 1
            time.sleep(0.01)
            continue

        if should_hold_without_ball_near_line(
            ball_visible,
            bool(snap.get("line", {}).get("detected", False)),
            line_cooldown,
            allow_dribble_prediction=dribble_prediction_active and use_goal_memory,
            goal_cx=target_goal_cx_now,
            hold_ball_without_goal=True,
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
            if state in (PREDICT, LOCAL_REACQUIRE, FIELD_SEARCH, WARMUP):
                if tick % 10 == 0:
                    print(
                        "--- pelota recuperada src={} r={:.0f} → TRACK ---".format(
                            source, r
                        ),
                        flush=True,
                    )
                state = TRACK
                loss_start_t = 0.0
                search_step_index = 0
                prev_hys_sign = 0
                last_turn = 0

        if state == WARMUP:
            elapsed_warmup = now - warmup_start
            if ball_visible or elapsed_warmup >= WARMUP_TIMEOUT:
                reason = "ball" if ball_visible else "timeout"
                print(
                    "--- WARMUP done t={:.1f}s ({}) -> FIELD_SEARCH ---".format(
                        elapsed_warmup, reason
                    ),
                    flush=True,
                )
                state = FIELD_SEARCH
                search_phase_start = now
                search_burst_sent = False
                search_phase = "move"

        elif state == TRACK:
            tracked_ball_visible = ball_visible
            reset_ball_filter = False
            if ball_visible:
                raw_jump = abs(float(ball["cx"]) - float(last_valid_cx)) if last_valid_cx > 0.0 else 0.0
                weak_last_lock = 0.0 < float(last_valid_r) < DRIBBLE_MIN_RADIUS
                dribble_reacquire = (
                    dribble_prediction_active
                    and raw_jump > frame_w * 0.25
                    and float(ball.get("r", 0.0)) >= BALL_VISIBLE_MIN_RADIUS
                )
                tracked_ball_visible = should_accept_tracked_ball_measurement(
                    ball,
                    last_cx=last_valid_cx,
                    last_seen_t=last_seen_t,
                    now=now,
                    frame_width=frame_w,
                    last_r=last_valid_r,
                    allow_large_jump=dribble_reacquire,
                    large_jump_min_radius=BALL_VISIBLE_MIN_RADIUS,
                )
                reset_ball_filter = tracked_ball_visible and (weak_last_lock or dribble_reacquire) and raw_jump > frame_w * 0.25
                if tracked_ball_visible:
                    jump_reject_streak = 0
                else:
                    jump_reject_streak += 1
                if not tracked_ball_visible and tick % 10 == 0:
                    print(
                        "--- BALL jump rejected raw={:.0f} keep={:.0f} age={:.2f}s ---".format(
                            float(cx),
                            float(last_valid_cx),
                            now - last_seen_t if last_seen_t > 0.0 else 0.0,
                        ),
                        flush=True,
                    )
                if not tracked_ball_visible and should_reset_track_after_jump_rejections(jump_reject_streak):
                    coast_goal_cx = target_goal_cx_now if target_goal_cx_now is not None else last_goal_cx
                    coast_goal_cy = target_goal_cy_now if target_goal_cx_now is not None else last_goal_cy
                    line_now = line_blocking or bool(snap.get("line", {}).get("detected", False))
                    goal_coast = should_goal_guided_coast(
                        last_ball_seen_t=last_seen_t,
                        last_ball_r=last_valid_r,
                        goal_cx=coast_goal_cx,
                        goal_seen_t=last_goal_ts,
                        now=now,
                        line_detected=line_now,
                        max_ball_age_s=GOAL_COAST_MAX_BALL_AGE,
                        max_goal_age_s=GOAL_COAST_MAX_GOAL_AGE,
                        min_ball_radius=GOAL_COAST_MIN_BALL_RADIUS,
                    )
                    if goal_coast:
                        coast_ball_cx = last_valid_cx if last_valid_cx > 0.0 else half
                        coast_ball_r = max(last_valid_r, GOAL_COAST_MIN_BALL_RADIUS)
                        command = controller.compute(
                            ball_cx=coast_ball_cx,
                            ball_cy=None,
                            ball_r=coast_ball_r,
                            goal_cx=coast_goal_cx,
                            goal_cy=coast_goal_cy,
                            line_detected=False,
                            continue_push=False,
                        )
                        v_cmd = max(0.0, min((command.v_left - command.v_right) * 0.5, GOAL_COAST_MAX_SPEED))
                        turn_cmd = (command.v_left + command.v_right) * 0.5
                        turn_cmd = max(-GOAL_COAST_MAX_TURN, min(GOAL_COAST_MAX_TURN, turn_cmd))
                        vL = v_cmd + turn_cmd
                        vR = -(v_cmd - turn_cmd)
                        last_valid_v = v_cmd
                        last_valid_w = turn_cmd
                        last_turn = turn_cmd
                        last_v_left = vL
                        last_v_right = vR
                        miss_streak = 0
                        ball_streak = 0
                        jump_reject_streak = 0
                        predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                        kalman_cx = Kalman1D(q=2.6, r=1.0)
                        kalman_r = Kalman1D(q=0.9, r=1.5)
                        hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                        drive(vL, vR, 80)
                        if tick % 5 == 0:
                            print(
                                "--- BALL track reset -> GOAL_COAST goal={:.0f} last_ball={:.0f} r={:.1f} v={:.0f} w={:+.0f} ---".format(
                                    float(coast_goal_cx),
                                    float(coast_ball_cx),
                                    float(coast_ball_r),
                                    v_cmd,
                                    turn_cmd,
                                ),
                                flush=True,
                            )
                        tick += 1
                        time.sleep(0.01)
                        continue

                    last_valid_w = 0.0
                    last_valid_v = 0.0
                    last_valid_cx = 0.0
                    last_valid_r = 0.0
                    last_seen_t = 0.0
                    miss_streak = 0
                    ball_streak = 0
                    jump_reject_streak = 0
                    predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                    kalman_cx = Kalman1D(q=2.6, r=1.0)
                    kalman_r = Kalman1D(q=0.9, r=1.5)
                    hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                    burst.send(PAN_CENTER, TILT_CENTER, 80, 0.0, 0.0, 0.0, 0.0)
                    if tick % 5 == 0:
                        print("--- BALL track reset after jump rejects ---", flush=True)
                    state = FIELD_SEARCH
                    search_phase_start = now
                    search_burst_sent = False
                    search_phase = "move"
                    tick += 1
                    time.sleep(0.01)
                    continue
            if (tracked_ball_visible or dribble_prediction_active) and not line_phase:
                dt = now - tick_start if tick_start else 0.01
                tick_start = now

                if tracked_ball_visible:
                    command_source = source
                    cx_raw = ball["cx"]
                    cy_raw = ball.get("cy")
                    r_raw = ball["r"]

                    if reset_ball_filter:
                        kalman_cx = Kalman1D(q=2.6, r=1.0)
                        kalman_r = Kalman1D(q=0.9, r=1.5)
                        predictor = BallPredictor(max_horizon_s=0.15, blend=0.55)
                        hysteresis = TurnHysteresis(enter_threshold=0.10, exit_threshold=0.04, sticky_frames=4)
                        if tick % 10 == 0:
                            label = "dribble reacquire" if dribble_reacquire else "weak-lock reacquire"
                            print(
                                "--- BALL {} raw={:.0f} old={:.0f} ---".format(
                                    label,
                                    float(cx_raw),
                                    float(last_valid_cx),
                                ),
                                flush=True,
                            )

                    cx_f = kalman_cx.update(cx_raw)
                    r_f = kalman_r.update(r_raw)

                    if source in ("hsv", "yolo"):
                        predictor.update(cx_f, r_f, now)
                        last_valid_cx = cx_f
                        last_seen_t = now
                else:
                    command_source = "predict"
                    pred_cx, pred_r = predictor.predict(now - last_seen_t)
                    cx_f = pred_cx if pred_cx > 0.0 else last_valid_cx
                    r_f = max(pred_r, last_valid_r)
                    cx_raw = cx_f
                    cy_raw = None
                    r_raw = r_f

                theta_raw = (cx_f - half) / half
                theta_filtered = hysteresis.filter(theta_raw)
                cx_filtered = half + half * theta_filtered

                if tracked_ball_visible:
                    _, r_eff = predictor.predict(0.0)
                else:
                    _, r_eff = cx_f, r_f
                r_eff = effective_goal_radius(r_raw, r_eff)
                if dribble_prediction_active:
                    r_eff = max(r_eff, last_valid_r)

                continue_dribble = dribble_prediction_active or should_continue_dribble_push(
                    ball_visible=tracked_ball_visible,
                    ball=ball,
                    goal_cx=target_goal_cx_now,
                    now=now,
                    dribble_until=dribble_until,
                    min_radius=DRIBBLE_MIN_RADIUS,
                )

                command = controller.compute(
                    ball_cx=cx_filtered,
                    ball_cy=cy_raw,
                    ball_r=r_eff,
                    goal_cx=target_goal_cx_now,
                    goal_cy=target_goal_cy_now,
                    line_detected=line_blocking,
                    continue_push=continue_dribble,
                )
                vL = command.v_left
                vR = command.v_right
                v_cmd = (vL - vR) * 0.5
                turn_cmd = (vL + vR) * 0.5
                command_mode = command.mode

                push_confirmed = should_allow_push_commit(
                    ball_streak,
                    min_streak=PUSH_CONFIRM_FRAMES,
                )
                if command.mode == "PUSH" and command.reason != "dribble" and not push_confirmed:
                    v_cmd = min(v_cmd, controller.near_speed)
                    turn_cmd *= 0.75
                    command_mode = "CHASE_CONFIRM"
                elif command.mode == "PUSH" and command.reason == "dribble":
                    command_mode = "DRIBBLE_PUSH"

                if source == "cache":
                    v_cmd *= cache_speed_scale
                    turn_cmd *= cache_turn_scale
                vL = v_cmd + turn_cmd
                vR = -(v_cmd - turn_cmd)

                last_valid_v = v_cmd
                last_valid_w = turn_cmd
                last_valid_r = r_eff
                last_turn = turn_cmd
                last_v_left = vL
                last_v_right = vR
                if command.mode == "PUSH" and command.reason != "dribble" and push_confirmed:
                    push_until = now + PUSH_COMMIT_MS / 1000.0
                    dribble_until = push_until + DRIBBLE_AFTER_PUSH_MS / 1000.0
                    last_push_v_left = vL
                    last_push_v_right = vR

                if tick % 10 == 0:
                    print(
                        "src={} r={:.0f} cx={:.1f} r_s={:.1f} theta={:+.2f} "
                        "v={:.0f} w={:+.0f} vL={:.0f} vR={:.0f} mode={} "
                        "hys={} goal={}".format(
                            command_source,
                            r_raw,
                            cx_filtered,
                            r_eff,
                            theta_filtered,
                            v_cmd,
                            turn_cmd,
                            vL,
                            vR,
                            command_mode,
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
                    state = FIELD_SEARCH
                    search_phase_start = now
                    search_burst_sent = False
                    search_phase = "move"

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
                if now - last_seen_t <= LOCAL_MEMORY_SEC:
                    state = LOCAL_REACQUIRE
                else:
                    state = FIELD_SEARCH
                search_phase_start = now
                search_burst_sent = False
                search_phase = "move"

            miss_streak += 1
            last_turn *= 0.6

        elif state == LOCAL_REACQUIRE:
            if not search_burst_sent:
                memory_cx = last_valid_cx if now - last_seen_t <= LOCAL_MEMORY_SEC else None
                direction, vL, vR = search.local_reacquire_step(
                    memory_cx,
                    last_valid_r,
                    frame_w,
                )
                drive(vL, vR, LOCAL_REACQUIRE_MS)
                search_burst_sent = True
                search_phase_start = now
                if tick % 5 == 0:
                    print(
                        "--- LOCAL_REACQUIRE dir={} last_cx={:.0f} last_r={:.1f} ---".format(
                            direction,
                            memory_cx if memory_cx is not None else -1,
                            last_valid_r,
                        ),
                        flush=True,
                    )

            if now - search_phase_start >= LOCAL_REACQUIRE_MS / 1000.0:
                state = FIELD_SEARCH
                search_phase = "move"
                search_step_index = 0
                search_burst_sent = False
                search_phase_start = now

            miss_streak += 1
            last_turn *= 0.6

        elif state == FIELD_SEARCH:
            if search_phase == "move":
                if not search_burst_sent:
                    current_line_detected = bool(snap.get("line", {}).get("detected", False))
                    if line_cooldown > 0 or current_line_detected:
                        direction, vL, vR = search.line_aware_field_search_step(
                            search_step_index,
                            last_line_cx,
                            frame_w,
                        )
                    else:
                        direction, vL, vR = search.field_search_step(search_step_index)
                    drive(vL, vR, FIELD_SEARCH_MOVE_MS)
                    search_burst_sent = True
                    search_phase_start = now
                    if tick % 10 == 0:
                        print(
                            "--- FIELD_SEARCH{} paso={} dir={} ---".format(
                                " line_aware" if (line_cooldown > 0 or current_line_detected) else "",
                                search_step_index,
                                direction,
                            ),
                            flush=True,
                        )

                if now - search_phase_start >= FIELD_SEARCH_MOVE_MS / 1000.0:
                    burst.send(PAN_CENTER, TILT_CENTER, 100, 0.0, 0.0, 0.0, 0.0)
                    search_phase = "pause"
                    search_phase_start = now

            elif search_phase == "pause":
                if now - search_phase_start >= FIELD_SEARCH_PAUSE_MS / 1000.0:
                    search_step_index += 1
                    search_burst_sent = False
                    search_phase = "move"
                    search_phase_start = now

            miss_streak += 1
            last_turn *= 0.6

        if tick % 30 == 0:
            goals = snap.get("goals", {})
            line_diag = snap.get("line", {})
            print(
                "goals yellow={} blue={} line_det={} line_pix={} line_cy={}".format(
                    goals.get("yellow", False),
                    goals.get("blue", False),
                line_diag.get("detected", False),
                line_diag.get("pixels", 0),
                line_diag.get("cy", None),
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
    vision.close()
    ser.close()
    print("Done.", flush=True)
