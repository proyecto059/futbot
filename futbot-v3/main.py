import os
import time


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


ULTRASONIC_ENABLED = _env_bool("ULTRASONIC", True)

LOG_EVERY = 10
PAN_CENTER = 70
TILT_CENTER = 45
DEFAULT_DIFF_CAP = 250.0

SEARCH = "SEARCH"
CHASE = "CHASE"
AVOID_MAP = "AVOID_MAP"

ULTRA_EVERY_N_FRAMES = 3
DIST_TRIGGER_MM = 250
KICK_RADIUS_PX = 50
CHASE_MISS_SECS = 1.5
CHASE_SMOOTH_SECS = 0.5
BALL_TOUCH_DIST_MM = 400
BALL_TOUCH_MAX_SECS = 3.0

ATTACK_BLUE = False

SEARCH_TURN_SPEED = 255
SEARCH_TURN_MS = 250
SEARCH_SCAN_SECS = 0.3
CHASE_SPEED_BASE = 120
CHASE_ROT_GAIN = 0.8
CHASE_DEADBAND_PX = 16
CHASE_BLIND_SPEED = 120
CHASE_BLIND_MS = 150
CHASE_BLIND_SCAN_SECS = 0.3
KICK_SPEED = 180
KICK_ROT_GAIN = 0.5
LINE_RETREAT_SPEED = 150
LINE_RETREAT_MS = 400
LINE_TURN_MS = 300
LINE_MIN_STREAK = 2

AVOID_REVERSE_SPEED = 110
AVOID_REVERSE_MS = 220
AVOID_TURN_SPEED = 115
AVOID_TURN_MS = 180
AVOID_FORWARD_SPEED = 105
AVOID_FORWARD_MS = 170
AVOID_MAX_STEPS = 5


def hybrid_trigger(dist, dist_trigger):
    dist_hit = dist is not None and dist <= dist_trigger
    return (True, "dist") if dist_hit else (False, "none")


def apply_ball_proximity_override(hybrid_active, cause, recent_ball, very_close):
    """If the ball is visible and the ultrasonic is triggered, assume the ultrasonic
    reading is the ball (not an obstacle) and suppress the avoid trigger."""
    if hybrid_active and recent_ball and very_close:
        return False, "ball_proximity"
    return hybrid_active, cause


def compute_chase_wheels(
    cx,
    radius,
    frame_width,
    speed_base,
    rot_gain,
    deadband_px,
    radius_close,
):
    if radius >= radius_close:
        return 0, 0

    error = cx - (frame_width / 2)
    rot = 0 if abs(error) <= deadband_px else rot_gain * error
    rot = max(-speed_base * 0.7, min(speed_base * 0.7, rot))
    return speed_base + rot, speed_base - rot


def compute_kick_wheels(goal_cx, frame_width, kick_speed, kick_rot_gain):
    if goal_cx is None:
        return kick_speed, kick_speed

    error = goal_cx - (frame_width / 2)
    rot = kick_rot_gain * error
    rot = max(-kick_speed * 0.7, min(kick_speed * 0.7, rot))
    return kick_speed + rot, kick_speed - rot


def choose_search_turn(last_cx, frame_center_x):
    if last_cx is None:
        return "left"
    if last_cx < frame_center_x:
        return "left"
    if last_cx == frame_center_x:
        return "right"
    return "right"


def avoid_map_turn_direction(last_cx, frame_center_x):
    return choose_search_turn(last_cx, frame_center_x)


def build_avoid_map_plan(last_cx, frame_center_x, max_steps=AVOID_MAX_STEPS):
    max_steps = max(1, int(max_steps))
    turn_dir = avoid_map_turn_direction(last_cx, frame_center_x)

    steps = [("reverse", AVOID_REVERSE_SPEED, AVOID_REVERSE_MS)]
    while len(steps) < max_steps:
        steps.append((f"turn_{turn_dir}", AVOID_TURN_SPEED, AVOID_TURN_MS))
        if len(steps) >= max_steps:
            break
        steps.append(("forward", AVOID_FORWARD_SPEED, AVOID_FORWARD_MS))
    return steps


def avoid_map_state_decision(ball_visible, hybrid_active, avoid_index, avoid_plan_len):
    if avoid_index >= avoid_plan_len:
        return SEARCH
    if hybrid_active:
        return AVOID_MAP
    if ball_visible:
        return CHASE
    return AVOID_MAP


def next_state(current_state, ball_visible, hybrid_active, miss_secs, miss_limit_secs):
    if current_state == SEARCH:
        return CHASE if ball_visible else SEARCH

    if current_state == CHASE:
        if hybrid_active:
            return AVOID_MAP
        if ball_visible:
            return CHASE
        return SEARCH if miss_secs >= miss_limit_secs else CHASE

    if current_state == AVOID_MAP:
        if hybrid_active:
            return AVOID_MAP
        return CHASE if ball_visible else SEARCH

    return SEARCH


def differential(v_left, v_right, cap=DEFAULT_DIFF_CAP):
    mx = max(abs(v_left), abs(v_right))
    if mx > cap:
        scale = cap / mx
        v_left *= scale
        v_right *= scale
    return (0.0, 0.0, v_left, -v_right)


def _burst_drive(bus, v_left, v_right, dur_ms):
    motors = differential(v_left, v_right)
    bus.burst(PAN_CENTER, TILT_CENTER, int(dur_ms), *motors)


def move_forward(bus, speed, dur_ms=300):
    _burst_drive(bus, speed, speed, dur_ms)


def move_reverse(bus, speed, dur_ms=300):
    _burst_drive(bus, -speed, -speed, dur_ms)


def turn_left(bus, speed, dur_ms=300):
    _burst_drive(bus, -speed, speed, dur_ms)


def turn_right(bus, speed, dur_ms=300):
    _burst_drive(bus, speed, -speed, dur_ms)


def stop_robot(bus, dur_ms=300):
    bus.burst(PAN_CENTER, TILT_CENTER, int(dur_ms), 0, 0, 0, 0)


def _log_transition(log, prev_state, new_state, reason):
    log.info("event=transition from=%s to=%s reason=%s", prev_state, new_state, reason)


def _log_hybrid_trigger(log, cause, dist_mm, radius):
    log.info(
        "event=hybrid_trigger cause=%s dist_mm=%s ball_radius=%.1f",
        cause,
        dist_mm if dist_mm is not None else "none",
        float(radius) if radius is not None else -1.0,
    )


def _run_step(bus, step_name, speed, dur_ms):
    if step_name == "reverse":
        move_reverse(bus, speed=speed, dur_ms=dur_ms)
    elif step_name == "forward":
        move_forward(bus, speed=speed, dur_ms=dur_ms)
    elif step_name == "turn_left":
        turn_left(bus, speed=speed, dur_ms=dur_ms)
    elif step_name == "turn_right":
        turn_right(bus, speed=speed, dur_ms=dur_ms)


def main():
    bus = None
    i2c = None
    vision = None

    # Imports perezosos: permiten que los tests importen funciones puras sin
    # necesitar cv2/onnxruntime/hardware presentes.
    try:
        from cam import SerialBus, SharedI2CBus, log
        from vision import HybridVisionService
        import cv2 as _cv2
    except Exception as exc:
        print(f"Failed importing runtime dependencies: {exc}")
        return

    try:
        bus = SerialBus()
        i2c = SharedI2CBus()

        # Un solo servicio cubre: captura (hilo OpenCV), YOLO (hilo), HSV,
        # goles, línea blanca y fusión con caché.
        vision = HybridVisionService()
        frame_width = vision.frame_width
        if frame_width <= 0:
            log.error("event=startup_failed reason=camera_unavailable")
            return

        state = SEARCH
        miss_count = 0
        miss_start = None
        frame_count = 0
        last_cx = None
        dist_mm = None
        avoid_plan = []
        avoid_index = 0
        last_search_turn_time = 0.0
        last_kick_log = 0.0
        last_ultra_log = 0.0
        last_chase_turn_time = 0.0
        last_ball_time = 0.0
        last_radius = None
        line_cooldown = 0
        line_streak = 0
        last_debug_frame = 0.0
        last_detector_debug_log = 0.0

        frame_center_x = frame_width / 2
        last_status_log = time.time()

        log.info(
            "event=controller_started state=%s attack_goal=%s ultrasonic=%s",
            state,
            "blue" if ATTACK_BLUE else "yellow",
            "on" if ULTRASONIC_ENABLED else "off",
        )

        while True:
            now = time.time()
            # tick() es non-blocking: un solo snapshot trae bola / robots /
            # goles / línea listos para consumir por el FSM. En el primer tick
            # tras boot puede venir con todos los campos vacíos (aún no hay
            # frame); el FSM lo interpreta como "sin visión" sin romperse.
            snap = vision.tick()
            frame_count += 1

            ball = snap.get("ball")
            ball_visible = ball is not None
            radius = None
            cx = None
            robot_count = len(snap.get("robots", []))

            goals = snap.get("goals", {})
            goal_yellow = bool(goals.get("yellow", False))
            goal_blue = bool(goals.get("blue", False))
            goal_target_cx = (
                goals.get("blue_cx") if ATTACK_BLUE else goals.get("yellow_cx")
            )

            if ball_visible:
                cx = ball["cx"]
                radius = ball["r"]
                last_cx = cx
                miss_count = 0
                miss_start = None
            else:
                miss_count += 1
                if miss_start is None:
                    miss_start = now

            # Dump periódico del último frame para debug visual.
            if now - last_debug_frame >= 5.0:
                frame = vision.last_frame()
                if frame is not None:
                    try:
                        _cv2.imwrite("/tmp/futbot_debug.jpg", frame)
                    except Exception:
                        pass
                last_debug_frame = now

            if ULTRASONIC_ENABLED and frame_count % ULTRA_EVERY_N_FRAMES == 0:
                dist_mm = i2c.read_ultrasonic()
                if now - last_ultra_log >= 2.0:
                    log.info(
                        "event=ultrasonic dist_mm=%s",
                        dist_mm if dist_mm is not None else "none",
                    )
                    last_ultra_log = now

            hybrid_active, cause = hybrid_trigger(
                dist_mm,
                DIST_TRIGGER_MM,
            )

            recent_ball = ball_visible or (now - last_ball_time < CHASE_SMOOTH_SECS)
            very_close = dist_mm is not None and dist_mm <= DIST_TRIGGER_MM
            hybrid_active, cause = apply_ball_proximity_override(
                hybrid_active, cause, recent_ball, very_close
            )

            if line_cooldown > 0:
                line_cooldown -= 1
                line_streak = 0
            else:
                line = snap.get("line", {})
                line_detected = bool(line.get("detected", False))
                line_cx = line.get("cx")
                line_pixels = int(line.get("pixels", 0))
                if line_detected:
                    line_streak += 1
                else:
                    line_streak = 0

                if line_streak >= LINE_MIN_STREAK:
                    log.warning(
                        "event=line_detected line_cx=%.1f pixels=%d state=%s streak=%d",
                        line_cx if line_cx is not None else -1,
                        line_pixels,
                        state,
                        line_streak,
                    )
                    move_reverse(bus, speed=LINE_RETREAT_SPEED, dur_ms=LINE_RETREAT_MS)
                    if line_cx is not None and line_cx < frame_center_x:
                        turn_right(bus, speed=SEARCH_TURN_SPEED, dur_ms=LINE_TURN_MS)
                    else:
                        turn_left(bus, speed=SEARCH_TURN_SPEED, dur_ms=LINE_TURN_MS)
                    state = SEARCH
                    last_search_turn_time = now
                    line_cooldown = 60
                    line_streak = 0
                    continue

            prev_state = state
            if state == AVOID_MAP:
                state = avoid_map_state_decision(
                    ball_visible=ball_visible,
                    hybrid_active=hybrid_active,
                    avoid_index=avoid_index,
                    avoid_plan_len=len(avoid_plan),
                )
            else:
                miss_secs = (now - miss_start) if miss_start is not None else 0.0
                state = next_state(
                    state, ball_visible, hybrid_active, miss_secs, CHASE_MISS_SECS
                )

            if state != prev_state:
                reason = (
                    "ball_reacquired"
                    if prev_state == AVOID_MAP and ball_visible
                    else "fsm"
                )
                _log_transition(log, prev_state, state, reason)
                if state == SEARCH:
                    last_search_turn_time = 0.0
                if state == CHASE:
                    last_chase_turn_time = 0.0
                if state == AVOID_MAP:
                    _log_hybrid_trigger(log, cause, dist_mm, radius)
                    avoid_plan = build_avoid_map_plan(
                        last_cx, frame_center_x, AVOID_MAX_STEPS
                    )
                    avoid_index = 0

            if state == SEARCH:
                if now - last_search_turn_time >= SEARCH_SCAN_SECS:
                    turn_dir = choose_search_turn(last_cx, frame_center_x)
                    if turn_dir == "left":
                        turn_left(bus, speed=SEARCH_TURN_SPEED, dur_ms=SEARCH_TURN_MS)
                    else:
                        turn_right(bus, speed=SEARCH_TURN_SPEED, dur_ms=SEARCH_TURN_MS)
                    last_search_turn_time = now
                else:
                    stop_robot(bus, dur_ms=100)

            elif state == CHASE:
                miss_secs = (now - miss_start) if miss_start is not None else 0.0
                if ball_visible:
                    last_ball_time = now
                    last_radius = radius
                    if radius is not None and radius >= KICK_RADIUS_PX:
                        ball_offset = abs(cx - frame_center_x)
                        if (
                            goal_target_cx is not None
                            and ball_offset < frame_width * 0.2
                        ):
                            v_left, v_right = compute_kick_wheels(
                                goal_target_cx, frame_width, KICK_SPEED, KICK_ROT_GAIN
                            )
                        else:
                            v_left, v_right = KICK_SPEED, KICK_SPEED
                        _burst_drive(bus, v_left=v_left, v_right=v_right, dur_ms=140)
                        if now - last_kick_log >= 1.0:
                            log.info(
                                "event=kick ball_radius=%.1f goal_visible=%s goal_cx=%s dist_mm=%s",
                                float(radius),
                                goal_target_cx is not None,
                                "%.1f" % goal_target_cx
                                if goal_target_cx is not None
                                else "none",
                                dist_mm if dist_mm is not None else "none",
                            )
                            last_kick_log = now
                    else:
                        v_left, v_right = compute_chase_wheels(
                            cx=cx,
                            radius=radius,
                            frame_width=frame_width,
                            speed_base=CHASE_SPEED_BASE,
                            rot_gain=CHASE_ROT_GAIN,
                            deadband_px=CHASE_DEADBAND_PX,
                            radius_close=KICK_RADIUS_PX,
                        )
                        _burst_drive(bus, v_left=v_left, v_right=v_right, dur_ms=140)

                elif now - last_ball_time < CHASE_SMOOTH_SECS:
                    if last_radius is not None and last_radius >= KICK_RADIUS_PX:
                        v_left, v_right = compute_kick_wheels(
                            goal_target_cx, frame_width, KICK_SPEED, KICK_ROT_GAIN
                        )
                    else:
                        v_left, v_right = compute_chase_wheels(
                            cx=last_cx,
                            radius=0,
                            frame_width=frame_width,
                            speed_base=CHASE_SPEED_BASE,
                            rot_gain=CHASE_ROT_GAIN,
                            deadband_px=CHASE_DEADBAND_PX,
                            radius_close=KICK_RADIUS_PX,
                        )
                    _burst_drive(bus, v_left=v_left, v_right=v_right, dur_ms=140)

                elif (
                    dist_mm is not None
                    and dist_mm <= BALL_TOUCH_DIST_MM
                    and miss_secs < BALL_TOUCH_MAX_SECS
                ):
                    move_forward(bus, speed=CHASE_SPEED_BASE, dur_ms=140)

                else:
                    if now - last_chase_turn_time >= CHASE_BLIND_SCAN_SECS:
                        turn_dir = choose_search_turn(last_cx, frame_center_x)
                        if turn_dir == "left":
                            turn_left(
                                bus, speed=CHASE_BLIND_SPEED, dur_ms=CHASE_BLIND_MS
                            )
                        else:
                            turn_right(
                                bus, speed=CHASE_BLIND_SPEED, dur_ms=CHASE_BLIND_MS
                            )
                        last_chase_turn_time = now
                    else:
                        stop_robot(bus, dur_ms=100)

            elif state == AVOID_MAP:
                if avoid_index < len(avoid_plan):
                    step_name, speed, dur_ms = avoid_plan[avoid_index]
                    _run_step(bus, step_name, speed, dur_ms)
                    avoid_index += 1
                else:
                    state = SEARCH

            if now - last_status_log >= 2.0:
                ball_source = ball["source"] if ball is not None else "none"
                log.info(
                    "event=status state=%s frame=%d miss=%d dist_mm=%s robots=%d goal_yellow=%s goal_blue=%s ball_src=%s",
                    state,
                    frame_count,
                    miss_count,
                    dist_mm if dist_mm is not None else "none",
                    robot_count,
                    goal_yellow,
                    goal_blue,
                    ball_source,
                )
                last_status_log = now

            if miss_count > 10 and now - last_detector_debug_log >= 3.0:
                debug = snap.get("debug", {})
                hsv_dbg = debug.get("hsv", {})
                yolo_dbg = debug.get("yolo", {})
                log.info(
                    "event=detector_debug miss=%d mode=%s v_median=%s hue_center=%.1f exposure=%s yolo_conf=%.2f yolo_ms=%.1f",
                    miss_count,
                    hsv_dbg.get("mode", "?"),
                    hsv_dbg.get("v_median", "?"),
                    float(hsv_dbg.get("hue_center", 0.0)),
                    hsv_dbg.get("exposure", "?"),
                    float(yolo_dbg.get("best_ball_conf", 0.0)),
                    float(yolo_dbg.get("inference_ms", 0.0)),
                )
                last_detector_debug_log = now

            time.sleep(0.01)

    except KeyboardInterrupt:
        if "log" in locals():
            log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        if "log" in locals():
            log.exception("event=runtime_error error=%s", exc)
        else:
            print(f"Runtime error: {exc}")
    finally:
        try:
            if bus is not None:
                stop_robot(bus, dur_ms=200)
        except Exception:
            pass
        try:
            if vision is not None:
                vision.close()
        except Exception:
            pass
        try:
            if i2c is not None:
                i2c.close()
        except Exception:
            pass
        try:
            if bus is not None:
                bus.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
