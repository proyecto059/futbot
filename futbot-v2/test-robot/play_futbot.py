import random
import time

import cv2

from hardware import (
    OBSTACLE_MM,
    PAN_CENTER,
    SERVO_PAN_INVERTED,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
from test_servos import ServoBallTracker

KICK_PUSH = "push"
KICK_ANGLED = "angled"
KICK_SPIN = "spin"
KICK_RADIUS_THRESHOLD = 50.0
KICK_CENTER_THRESHOLD = 60
KICK_EDGE_MARGIN = 120
KICK_SPIN_RADIUS_THRESHOLD = 40.0
KICK_PAN_THRESHOLD = 8
PAN_APPROACH_THRESHOLD = 5
APPROACH_SPEED_RATIO = 0.6
SEARCH_SPIN_SPEED = 60.0
KICK_SHOT_SEC = 1.0
KICK_ANGLED_TURN_SEC = 0.4
KICK_SPIN_SEC = 0.6
RECOVERY_SEC = 1.0
RECOVERY_SPEED = 150.0
PLAY_DURATION = 300.0
SONIC_EVERY_N = 5
SEARCH_GRACE_SEC = 3.0
SEARCH_SPIN_SEC = 0.3
SEARCH_PAUSE_SEC = 0.4


def should_kick(result, ball, speed, fw):
    if ball is None or not result["tracking_locked"]:
        return None
    if result["ema_cx"] is None:
        return None
    if abs(result.get("pan", PAN_CENTER) - PAN_CENTER) >= KICK_PAN_THRESHOLD:
        return None
    _, _, radius = ball
    fcx = fw / 2.0
    offset = abs(result["ema_cx"] - fcx)
    at_edge = (
        result["ema_cx"] < KICK_EDGE_MARGIN or result["ema_cx"] > fw - KICK_EDGE_MARGIN
    )
    if radius >= KICK_RADIUS_THRESHOLD and offset < KICK_CENTER_THRESHOLD:
        if at_edge:
            return KICK_SPIN
        return random.choice([KICK_PUSH, KICK_ANGLED])
    if radius >= KICK_SPIN_RADIUS_THRESHOLD and at_edge:
        return KICK_SPIN
    return None


def run_play_futbot(sbus, ibus, speed):
    cap, fw, _ = find_camera()
    if not cap:
        log.error("[FUTBOT] No se detecto camara. Abortando.")
        return
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    S = speed
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)
    tracker = ServoBallTracker(
        fw, fh, sweep_enabled=True, max_track_delta=25, sweep_step=15
    )
    baseline = ibus.calibrate_line()
    log.info("=" * 55)
    log.info("[FUTBOT] === MODO FUTBOT (%.0fs max) ===", PLAY_DURATION)
    log.info("[FUTBOT] Buscar pelota -> acercar -> patear (push/angled/spin)")
    log.info("=" * 55)
    t0 = time.time()
    frame_count = 0
    detect_count = 0
    kick_count = 0
    last_fps_log = t0
    kick_active = False
    kick_type = None
    kick_phase = None
    kick_t0 = 0.0
    recovery_active = False
    recovery_t0 = 0.0
    ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
    search_spin_until = 0.0
    search_pause_until = 0.0
    last_detect_ts = t0

    try:
        while time.time() - t0 < PLAY_DURATION:
            elapsed = time.time() - t0
            line_changed_flag, cur_sensors = ibus.line_changed(baseline)
            if line_changed_flag:
                log.warning("[FUTBOT] Linea blanca! sensores=%s", cur_sensors)
                sbus.stop()
                time.sleep(0.2)
                m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, RECOVERY_SPEED)
                sbus.burst(PAN_CENTER, TILT_CENTER, int(RECOVERY_SEC * 1000), *m)
                time.sleep(RECOVERY_SEC + 0.2)
                kick_active = False
                recovery_active = False
                continue
            frame_count += 1
            if frame_count % SONIC_EVERY_N == 0:
                dist = ibus.read_ultrasonic()
                if dist < OBSTACLE_MM:
                    log.warning("[FUTBOT] Obstaculo %dmm! Retrocediendo", dist)
                    sbus.stop()
                    time.sleep(0.2)
                    m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, RECOVERY_SPEED)
                    sbus.burst(PAN_CENTER, TILT_CENTER, int(RECOVERY_SEC * 1000), *m)
                    time.sleep(RECOVERY_SEC + 0.2)
                    kick_active = False
                    recovery_active = False
                    continue
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            now = time.time()
            ball = detector.detect(frame, now)
            result = tracker.update(ball, now)
            if result["detected"]:
                detect_count += 1
                last_detect_ts = now
            if kick_active:
                dt = time.time() - kick_t0
                if kick_type == KICK_PUSH:
                    if dt < KICK_SHOT_SEC:
                        m = differential(S, S, S)
                        sbus.burst(result["pan"], result["tilt"], 200, *m)
                    else:
                        kick_active = False
                        recovery_active = True
                        recovery_t0 = time.time()
                        kick_count += 1
                        ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
                elif kick_type == KICK_ANGLED:
                    if kick_phase == "turn":
                        if dt < KICK_ANGLED_TURN_SEC:
                            m = differential(-S * 0.5, S * 0.5, S)
                            sbus.burst(result["pan"], result["tilt"], 200, *m)
                        else:
                            kick_phase = "strike"
                            kick_t0 = time.time()
                    else:
                        if dt < KICK_SHOT_SEC:
                            m = differential(S, S, S)
                            sbus.burst(result["pan"], result["tilt"], 200, *m)
                        else:
                            kick_active = False
                            recovery_active = True
                            recovery_t0 = time.time()
                            kick_count += 1
                elif kick_type == KICK_SPIN:
                    if dt < KICK_SPIN_SEC:
                        m = differential(S, -S, S)
                        sbus.burst(result["pan"], result["tilt"], 200, *m)
                    else:
                        kick_active = False
                        recovery_active = True
                        recovery_t0 = time.time()
                        kick_count += 1
                        ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
                time.sleep(0.05)
                continue
            if recovery_active:
                dt = time.time() - recovery_t0
                if dt < RECOVERY_SEC:
                    m = differential(-RECOVERY_SPEED, -RECOVERY_SPEED, RECOVERY_SPEED)
                    sbus.burst(result["pan"], result["tilt"], 200, *m)
                else:
                    recovery_active = False
                time.sleep(0.05)
                continue
            kick = should_kick(result, ball, S, fw)
            if kick is not None:
                kick_active = True
                kick_type = kick
                kick_phase = "turn" if kick == KICK_ANGLED else "strike"
                kick_t0 = time.time()
                ibus.set_ultrasonic_led(0xFF, 0x20, 0x00, blink=True)
                r = ball[2] if ball else 0
                log.info(
                    "[FUTBOT] Kick! tipo=%s r=%.0f ema_cx=%s",
                    kick,
                    r,
                    result["ema_cx"],
                )
                sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
                continue

            if result["tracking_locked"]:
                pan_offset = result["pan"] - PAN_CENTER
                if abs(pan_offset) > PAN_APPROACH_THRESHOLD:
                    align_speed = max(60.0, min(200.0, abs(pan_offset) * 2.5))
                    if SERVO_PAN_INVERTED:
                        if pan_offset > 0:
                            m = differential(-align_speed, align_speed, S)
                        else:
                            m = differential(align_speed, -align_speed, S)
                    else:
                        if pan_offset > 0:
                            m = differential(align_speed, -align_speed, S)
                        else:
                            m = differential(-align_speed, align_speed, S)
                else:
                    m = differential(S * 0.6, S * 0.6, S)
                sbus.burst(result["pan"], result["tilt"], 200, *m)
                search_spin_until = 0.0
                search_pause_until = 0.0
            else:
                time_since_detect = now - last_detect_ts
                if time_since_detect > SEARCH_GRACE_SEC:
                    if now < search_pause_until:
                        sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
                    elif now < search_spin_until:
                        m = differential(-SEARCH_SPIN_SPEED, SEARCH_SPIN_SPEED, S)
                        sbus.burst(result["pan"], result["tilt"], 200, *m)
                    else:
                        if search_spin_until > 0:
                            search_pause_until = now + SEARCH_PAUSE_SEC
                            search_spin_until = 0.0
                            sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
                        else:
                            search_spin_until = now + SEARCH_SPIN_SEC
                            search_pause_until = 0.0
                else:
                    sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
            if frame_count % 10 == 0 and result["ema_cx"] is not None:
                r = tracker.last_radius or 0
                log.info(
                    "[FUTBOT] %.1fs | cx=%s cy=%s r=%.0f mode=%s",
                    elapsed,
                    result["ema_cx"],
                    result["ema_cy"],
                    r,
                    result["mode"],
                )
            now_log = time.time()
            if now_log - last_fps_log >= 5.0:
                fps = frame_count / elapsed if elapsed > 0 else 0
                pct = detect_count / frame_count * 100 if frame_count > 0 else 0
                log.info(
                    "[FUTBOT] --- FPS: %.1f | Detect: %.0f%% | Kicks: %d ---",
                    fps,
                    pct,
                    kick_count,
                )
                last_fps_log = now_log
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("[FUTBOT] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
        log.info("[FUTBOT] === FIN (%.1fs, kicks=%d) ===", time.time() - t0, kick_count)
