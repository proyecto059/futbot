import time

from hardware import (
    PAN_CENTER,
    PAN_MAX,
    PAN_MIN,
    TILT_CENTER,
    detect_ball,
    find_camera,
    log,
)
import cv2

TEST_SERVO_DURATION = 60.0


# ── Servo tracking test (--test-servo) ───────────────────────────────────────


def run_test_servos(sbus):
    cap, fw = find_camera()
    if not cap:
        log.error("[TEST-SERVO] No se detecto camara. Abortando.")
        return

    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    log.info("=" * 55)
    log.info(
        "[TEST-SERVO] === SEGUIMIENTO DE PELOTA CON SERVOS (%.0fs) ===",
        TEST_SERVO_DURATION,
    )
    log.info("[TEST-SERVO] Resolucion: %dx%d", fw, fh)
    log.info("[TEST-SERVO] Solo servos, ruedas detenidas")
    log.info("[TEST-SERVO] Mapeo: cx 0->pan=0, cx %d->pan=180", fw)
    log.info("[TEST-SERVO] Mapeo: cy 0->tilt=180, cy %d->tilt=0", fh)
    log.info("[TEST-SERVO] Si tilt esta invertido, cambiamos en codigo")
    log.info("=" * 55)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    t0 = time.time()
    frame_count = 0
    detect_count = 0
    last_fps_log = t0
    last_pan = PAN_CENTER
    last_tilt = TILT_CENTER

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= TEST_SERVO_DURATION:
                break

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue

            frame_count += 1
            ball = detect_ball(frame)

            if ball:
                cx, cy, r = ball
                detect_count += 1

                target_pan = int(cx / fw * 180)
                target_pan = max(PAN_MIN, min(PAN_MAX, target_pan))

                target_tilt = int((1.0 - cy / fh) * 180)
                target_tilt = max(0, min(180, target_tilt))

                pan = int(last_pan + (target_pan - last_pan) * 0.4)
                tilt = int(last_tilt + (target_tilt - last_tilt) * 0.4)
                pan = max(PAN_MIN, min(PAN_MAX, pan))
                tilt = max(0, min(180, tilt))

                sbus.burst(pan, tilt, 200, 0, 0, 0, 0)
                last_pan = pan
                last_tilt = tilt

                log.info(
                    "[TEST-SERVO] %.1fs | Pelota cx=%d cy=%d r=%.0f -> pan=%d tilt=%d",
                    elapsed,
                    cx,
                    cy,
                    r,
                    pan,
                    tilt,
                )
            else:
                pan = int(last_pan + (PAN_CENTER - last_pan) * 0.1)
                tilt = int(last_tilt + (TILT_CENTER - last_tilt) * 0.1)
                sbus.burst(pan, tilt, 200, 0, 0, 0, 0)
                last_pan = pan
                last_tilt = tilt
                log.info(
                    "[TEST-SERVO] %.1fs | Sin pelota - centrando pan=%d tilt=%d",
                    elapsed,
                    pan,
                    tilt,
                )

            now = time.time()
            if now - last_fps_log >= 5.0:
                fps = frame_count / elapsed if elapsed > 0 else 0
                pct = (detect_count / frame_count * 100) if frame_count > 0 else 0
                log.info(
                    "[TEST-SERVO] --- FPS: %.1f | Deteccion: %.0f%% (%d/%d) ---",
                    fps,
                    pct,
                    detect_count,
                    frame_count,
                )
                last_fps_log = now

    except KeyboardInterrupt:
        log.info("[TEST-SERVO] Interrumpido por usuario")
    finally:
        sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
        time.sleep(0.5)
        cap.release()
        total = time.time() - t0
        pct = (detect_count / frame_count * 100) if frame_count > 0 else 0
        log.info("=" * 55)
        log.info("[TEST-SERVO] === FIN (%.1fs) ===", total)
        log.info(
            "[TEST-SERVO] Frames: %d | Detecciones: %d (%.0f%%)",
            frame_count,
            detect_count,
            pct,
        )
        log.info("=" * 55)