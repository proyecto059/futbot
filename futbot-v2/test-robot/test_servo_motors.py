import time

from hardware import (
    DEFAULT_SPEED,
    PAN_CENTER,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
from test_servos import ServoBallTracker

DURATION = 60.0
TURN_SPEED = 75.0
FWD_SEC = 0.5
PAUSE_SEC = 2.0
REV_SEC = 0.5
OBSTACLE_MM = 80
RETREAT_SEC = 0.8
SONIC_EVERY_N = 5
ROTATION_RATE_DEG_PER_SEC = 90.0

PHASES = [
    ("left45", FWD_SEC),
    ("pause1", PAUSE_SEC),
    ("center1", FWD_SEC),
    ("pause2", PAUSE_SEC),
    ("right45", REV_SEC),
    ("pause3", PAUSE_SEC),
    ("center2", REV_SEC),
    ("pause4", PAUSE_SEC),
]


def run_test_servo_motors(sbus, ibus):
    cap, fw, exp = find_camera()
    if not cap:
        log.error("[TSM] No se detecto camara. Abortando.")
        return

    fh = (fw * 3) // 4
    log.info("[TSM] Resolucion: %dx%d", fw, fh)
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)
    tracker = ServoBallTracker(
        fw,
        fh,
        sweep_enabled=True,
        max_track_delta=25,
        max_track_delta_near_center=8,
        track_alpha=0.6,
    )

    log.info("=" * 60)
    log.info("[TSM] === TEST SERVOS+GIRO-DIFERENCIAL (%.0fs) ===", DURATION)
    log.info(
        "[TSM] Patron: left45 %.1fs → pause → center → pause → right45 %.1fs → pause → center → pause",
        FWD_SEC,
        REV_SEC,
    )
    log.info("[TSM] Resolucion: %dx%d | sonic cada %d frames", fw, fh, SONIC_EVERY_N)
    log.info("=" * 60)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    t0 = time.time()
    last_frame_time = t0
    frame_count = 0
    detect_count = 0
    obstacle_count = 0
    last_fps_log = t0
    retreating_until = 0.0
    cached_dist = 9999

    phase_totals = {n: 0 for n, _ in PHASES}
    phase_detects = {n: 0 for n, _ in PHASES}

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= DURATION:
                break

            now = time.time()
            dt = now - last_frame_time
            last_frame_time = now
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            frame_count += 1
            ball = detector.detect(frame)
            if ball is not None:
                detect_count += 1

            cycle_len = sum(d for _, d in PHASES)
            t_in_cycle = elapsed % cycle_len
            acc = 0.0
            phase_name = PHASES[0][0]
            for pname, pdur in PHASES:
                acc += pdur
                if t_in_cycle < acc:
                    phase_name = pname
                    break

            if phase_name in ("left45", "center2"):
                rot_ff = ROTATION_RATE_DEG_PER_SEC * dt
            elif phase_name in ("right45", "center1"):
                rot_ff = -ROTATION_RATE_DEG_PER_SEC * dt
            else:
                rot_ff = 0.0

            result = tracker.update(ball, now, rotation_ff=rot_ff)
            pan = result["pan"]
            tilt = result["tilt"]

            phase_totals[phase_name] = phase_totals.get(phase_name, 0) + 1
            if result["detected"]:
                phase_detects[phase_name] = phase_detects.get(phase_name, 0) + 1

            if now < retreating_until:
                sbus.burst(pan, tilt, 200, 0, 0, 0, 0)
                continue

            if frame_count % SONIC_EVERY_N == 0:
                cached_dist = ibus.read_ultrasonic()

            if ball is None and cached_dist < OBSTACLE_MM:
                obstacle_count += 1
                log.warning(
                    "[TSM] OBSTACULO %dmm! Retrocediendo (#%d)",
                    cached_dist,
                    obstacle_count,
                )
                m_ret = differential(-200, -200, 200)
                sbus.burst(pan, tilt, int(RETREAT_SEC * 1000), *m_ret)
                retreating_until = now + RETREAT_SEC + 0.1
                continue

            if phase_name in ("left45", "center2"):
                m = differential(TURN_SPEED, -TURN_SPEED, DEFAULT_SPEED)
            elif phase_name in ("right45", "center1"):
                m = differential(-TURN_SPEED, TURN_SPEED, DEFAULT_SPEED)
            else:
                m = (0, 0, 0, 0)

            sbus.burst(pan, tilt, 200, *m)

            if frame_count % 10 == 0:
                r_str = "LOST"
                if ball is not None:
                    cx, cy, r = ball
                    r_str = "cx=%d cy=%d r=%.0f" % (cx, cy, r)
                log.info(
                    "[TSM] %.1fs | %-7s | %s | mode=%s | m=(%d,%d,%d,%d) | pan=%d tilt=%d",
                    elapsed,
                    phase_name,
                    r_str,
                    result["mode"],
                    int(m[0]),
                    int(m[1]),
                    int(m[2]),
                    int(m[3]),
                    pan,
                    tilt,
                )

            if now - last_fps_log >= 5.0:
                fps = frame_count / elapsed if elapsed > 0 else 0
                pct = detect_count / frame_count * 100 if frame_count > 0 else 0
                phase_stats = " | ".join(
                    "%s:%.0f%%"
                    % (
                        n,
                        phase_detects.get(n, 0) / max(1, phase_totals.get(n, 0)) * 100,
                    )
                    for n, _ in PHASES
                )
                log.info(
                    "[TSM] --- FPS:%.1f Detect:%.0f%% (%d/%d) Obstacles:%d | %s ---",
                    fps,
                    pct,
                    detect_count,
                    frame_count,
                    obstacle_count,
                    phase_stats,
                )
                last_fps_log = now

    except KeyboardInterrupt:
        log.info("[TSM] Interrumpido")
    finally:
        sbus.stop(PAN_CENTER, TILT_CENTER)
        time.sleep(0.3)
        cap.release()
        total = time.time() - t0
        pct = detect_count / frame_count * 100 if frame_count > 0 else 0
        log.info("=" * 60)
        log.info("[TSM] === FIN (%.1fs) ===", total)
        log.info(
            "[TSM] Frames:%d Detects:%d (%.0f%%) Obstacles:%d",
            frame_count,
            detect_count,
            pct,
            obstacle_count,
        )
        for name, _ in PHASES:
            tot = phase_totals.get(name, 0)
            det = phase_detects.get(name, 0)
            p = det / tot * 100 if tot > 0 else 0
            log.info("[TSM]   %-7s: %d/%d (%.0f%%)", name, det, tot, p)
        log.info("=" * 60)
