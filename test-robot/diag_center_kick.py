import time

import cv2

from hardware import (
    OBSTACLE_MM,
    PAN_CENTER,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
from test_servos import ServoBallTracker

DIAG_DURATION = 120.0
SWEEP_STEP = 5

ROTATION_GAIN = 3.5
FWD_ALIGNED = 0.7
FWD_CLOSE = 0.25
FWD_MISALIGNED = 0.4
FWD_FAR_EDGE = 0.08
FAR_EDGE_PAN = 50
PAN_ALIGNED_THRESH = 15
CLOSE_RADIUS = 60
CHASE_TIMEOUT = 15.0

KICK_RADIUS = 70
LOST_CONFIRM = 5

CAMERA_FAIL_MAX = 10

RETREAT_SEC = 1.0
MAX_KICKS = 3


def run_diag_center_kick(sbus, ibus, speed):
    cap, fw, _ = find_camera(threaded=True)
    if not cap:
        log.error("[DIAG] No se detecto camara. Abortando.")
        return

    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    S = speed
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)

    tracker = ServoBallTracker(fw, fh, sweep_enabled=False)
    baseline = ibus.calibrate_line()

    log.info("=" * 60)
    log.info("[DIAG] === DIAG CHASE v7 (%.0fs) ===", DIAG_DURATION)
    log.info("[DIAG] search → chase | LOST+r = GOL | threaded cam")
    log.info(
        "[DIAG] gain=%.1f aligned=%.0f close=%.0f mis=%.0f far=%.0f kick_r=%d",
        ROTATION_GAIN,
        FWD_ALIGNED * 100,
        FWD_CLOSE * 100,
        FWD_MISALIGNED * 100,
        FWD_FAR_EDGE * 100,
        KICK_RADIUS,
    )
    log.info("=" * 60)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    t0 = time.time()
    state = "search"
    manual_sweep_dir = 1
    manual_sweep_pan = PAN_CENTER
    phase_start = 0.0
    frame_count = 0
    kick_count = 0
    last_log = t0
    consecutive_lost = 0
    last_radius_before_lost = 0
    cam_fail_count = 0

    try:
        while time.time() - t0 < DIAG_DURATION:
            elapsed = time.time() - t0

            line_changed, cur_sensors = ibus.line_changed(baseline)
            if line_changed:
                log.warning("[DIAG] Linea blanca! sensores=%s", cur_sensors)
                sbus.stop()
                time.sleep(0.5)
                state = "search"
                consecutive_lost = 0
                continue

            if frame_count % 5 == 0:
                dist = ibus.read_ultrasonic()
                if dist < OBSTACLE_MM and state != "chase":
                    log.warning("[DIAG] Obstaculo %dmm", dist)
                    sbus.stop()
                    time.sleep(0.3)
                    m = differential(-S * 0.5, -S * 0.5, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 500, *m)
                    time.sleep(RETREAT_SEC)
                    state = "search"
                    consecutive_lost = 0
                    continue

            ok, frame = cap.read()
            if not ok or frame is None:
                cam_fail_count += 1
                if cam_fail_count >= CAMERA_FAIL_MAX:
                    log.error(
                        "[DIAG] Camara perdida (%d fails). Saliendo.", cam_fail_count
                    )
                    break
                time.sleep(0.05)
                continue
            cam_fail_count = 0
            frame_count += 1
            now = time.time()
            ball = detector.detect(frame, now)
            result = tracker.update(ball, now)
            pan = result["pan"]
            tilt = result["tilt"]
            ball_r = tracker.last_radius or 0

            if state == "search":
                consecutive_lost = 0

                if not result["detected"]:
                    manual_sweep_pan += SWEEP_STEP * manual_sweep_dir
                    if manual_sweep_pan >= 180:
                        manual_sweep_pan = 180
                        manual_sweep_dir = -1
                    elif manual_sweep_pan <= 0:
                        manual_sweep_pan = 0
                        manual_sweep_dir = 1
                else:
                    manual_sweep_pan = pan

                sbus.burst(manual_sweep_pan, TILT_CENTER, 200, 0, 0, 0, 0)

                if frame_count % 15 == 0:
                    log.info(
                        "[DIAG] search | sweep=%d pan=%d mode=%s",
                        manual_sweep_pan,
                        pan,
                        result["mode"],
                    )

                if result["detected"] and result["tracking_locked"]:
                    log.info(
                        "[DIAG] Encontrada! pan=%d r=%.0f -> chase",
                        pan,
                        ball_r,
                    )
                    state = "chase"
                    phase_start = now

            elif state == "chase":
                if result["tracking_locked"]:
                    consecutive_lost = 0
                    last_radius_before_lost = ball_r
                else:
                    consecutive_lost += 1

                if consecutive_lost >= LOST_CONFIRM:
                    if last_radius_before_lost >= KICK_RADIUS:
                        log.info(
                            "[DIAG] LOST r=%.0f (>=%d) -> GOL!",
                            last_radius_before_lost,
                            KICK_RADIUS,
                        )
                        sbus.stop()
                        kick_count += 1
                        ibus.set_ultrasonic_led(0xFF, 0x20, 0x00, blink=True)
                        time.sleep(0.3)

                        log.info("[DIAG] Retrocediendo...")
                        m = differential(-S * 0.5, -S * 0.5, S)
                        sbus.burst(PAN_CENTER, TILT_CENTER, 500, *m)
                        time.sleep(RETREAT_SEC)
                        sbus.stop()
                        ibus.set_ultrasonic_led(0x00, 0x10, 0x00)

                        if kick_count >= MAX_KICKS:
                            log.info("[DIAG] %d kicks completados. Fin.", kick_count)
                            break
                        state = "search"
                        consecutive_lost = 0
                        continue
                    else:
                        log.info(
                            "[DIAG] LOST r=%.0f (<%d) -> search",
                            last_radius_before_lost,
                            KICK_RADIUS,
                        )
                        sbus.stop()
                        state = "search"
                        consecutive_lost = 0
                        continue

                dt = now - phase_start
                if dt > CHASE_TIMEOUT:
                    log.warning("[DIAG] Chase timeout (%.1fs) -> search", dt)
                    sbus.stop()
                    state = "search"
                    consecutive_lost = 0
                    continue

                if not result["tracking_locked"]:
                    m = differential(S * 0.15, S * 0.15, S)
                    sbus.burst(pan, tilt, 200, *m)
                    time.sleep(0.05)
                    continue

                pan_offset = PAN_CENTER - pan
                abs_pan = abs(pan_offset)

                if ball_r >= CLOSE_RADIUS:
                    fwd_ratio = FWD_CLOSE
                elif abs_pan >= FAR_EDGE_PAN:
                    fwd_ratio = FWD_FAR_EDGE
                elif abs_pan <= PAN_ALIGNED_THRESH:
                    fwd_ratio = FWD_ALIGNED
                else:
                    fwd_ratio = FWD_MISALIGNED

                forward = S * fwd_ratio
                rotation = pan_offset * ROTATION_GAIN

                v_left = forward + rotation
                v_right = forward - rotation

                m = differential(v_left, v_right, S)

                sbus.burst(pan, tilt, 200, *m)

                if now - last_log >= 0.3:
                    log.info(
                        "[DIAG] chase %.1fs | pan=%d off=%+d r=%.0f | fwd=%.0f rot=%.0f | vl=%.0f vr=%.0f m=%s",
                        dt,
                        pan,
                        pan_offset,
                        ball_r,
                        forward,
                        rotation,
                        v_left,
                        v_right,
                        tuple(round(x) for x in m),
                    )
                    last_log = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("[DIAG] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        ibus.set_ultrasonic_led(0x00, 0x10, 0x00)
        total = time.time() - t0
        log.info("=" * 60)
        log.info("[DIAG] === FIN (%.1fs, kicks=%d) ===", total, kick_count)
        log.info("=" * 60)