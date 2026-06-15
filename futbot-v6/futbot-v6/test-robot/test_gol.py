import time

import cv2

from hardware import (
    BALL_CLOSE_RADIUS,
    CENTER_THRESH,
    DEFAULT_SPEED,
    PAN_CENTER,
    SPIN_360_SEC,
    TILT_CENTER,
    create_detector,
    differential,
    find_camera,
    log,
)
from test_servos import ServoBallTracker

GOL_GIRO_ANGLE_SEC = 0.5
GOL_GIRO_ADVANCE_SEC = 1.5
GOL_AVANCE_BRAKE_SEC = 0.5
GOL_AVANCE_SHOT_SEC = 1.0
GOL_DURATION = 120.0


def run_gol_giro(sbus, speed):
    cap, fw, _ = find_camera()
    if not cap:
        log.error("[GOL-GIRO] No se detecto camara. Abortando.")
        return
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fcx = fw // 2
    S = speed
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)
    tracker = ServoBallTracker(fw, fh, sweep_enabled=True)
    log.info("=" * 55)
    log.info("[GOL-GIRO] === TEST GOL CON GIRO (%.0fs max) ===", GOL_DURATION)
    log.info("[GOL-GIRO] Buscar pelota -> avanzar -> girar 45 -> avanzar -> golpear")
    log.info("=" * 55)
    t0 = time.time()
    phase = "search"
    t_phase = time.time()

    try:
        while time.time() - t0 < GOL_DURATION:
            if phase == "search":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                raw_ball = detector.detect(frame)
                result = tracker.update(raw_ball, time.time())
                sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)

                if result["detected"] and result["tracking_locked"]:
                    cx = result["ema_cx"]
                    cy = result["ema_cy"]
                    r = tracker.last_radius or 0
                    log.info(
                        "[GOL-GIRO] Pelota detectada cx=%d cy=%d r=%.0f", cx, cy, r
                    )
                    phase = "approach"
                    t_phase = time.time()

            elif phase == "approach":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                raw_ball = detector.detect(frame)
                result = tracker.update(raw_ball, time.time())

                if result["mode"] in ("recenter", "sweep"):
                    sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
                    log.info("[GOL-GIRO] Pelota perdida. Volviendo a buscar.")
                    phase = "search"
                    continue

                sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)

                if result["detected"]:
                    cx = result["ema_cx"]
                    cy = result["ema_cy"]
                    r = tracker.last_radius or 0
                    offset = abs(cx - fcx)
                    omega = max(-1.0, min(1.0, (cx - fcx) / fcx))
                    v_left = S * 0.6 * (1 + omega * 0.5)
                    v_right = S * 0.6 * (1 - omega * 0.5)
                    m = differential(v_left, v_right, S)
                    sbus.burst(result["pan"], result["tilt"], 200, *m)
                    if r >= BALL_CLOSE_RADIUS and offset < CENTER_THRESH:
                        log.info("[GOL-GIRO] Pelota cerca y centrada. Girando...")
                        sbus.stop()
                        phase = "turn"
                        t_phase = time.time()
                time.sleep(0.15)

            elif phase == "turn":
                elapsed = time.time() - t_phase
                if elapsed < GOL_GIRO_ANGLE_SEC:
                    m = differential(-S * 0.5, S * 0.5, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] Giro completado. Avanzando para golpear...")
                    phase = "strike"
                    t_phase = time.time()

            elif phase == "strike":
                elapsed = time.time() - t_phase
                if elapsed < GOL_GIRO_ADVANCE_SEC:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] GOL! Celebrando giro 360...")
                    phase = "celebrate"
                    t_phase = time.time()

            elif phase == "celebrate":
                elapsed = time.time() - t_phase
                if elapsed < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-GIRO] Celebracion completada!")
                    break

    except KeyboardInterrupt:
        log.info("[GOL-GIRO] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        log.info("[GOL-GIRO] === FIN ===")


def run_gol_avance(sbus, speed):
    cap, fw, _ = find_camera()
    if not cap:
        log.error("[GOL-AVANCE] No se detecto camara. Abortando.")
        return
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fcx = fw // 2
    S = speed
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)
    tracker = ServoBallTracker(fw, fh, sweep_enabled=True)
    log.info("=" * 55)
    log.info("[GOL-AVANCE] === TEST GOL AVANZANDO (%.0fs max) ===", GOL_DURATION)
    log.info("[GOL-AVANCE] Buscar pelota -> acercar lento -> frenar -> golpe")
    log.info("=" * 55)
    t0 = time.time()
    phase = "search"
    t_phase = time.time()

    try:
        while time.time() - t0 < GOL_DURATION:
            if phase == "search":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                raw_ball = detector.detect(frame)
                result = tracker.update(raw_ball, time.time())
                sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)

                if result["detected"] and result["tracking_locked"]:
                    cx = result["ema_cx"]
                    cy = result["ema_cy"]
                    r = tracker.last_radius or 0
                    log.info(
                        "[GOL-AVANCE] Pelota detectada cx=%d cy=%d r=%.0f", cx, cy, r
                    )
                    phase = "approach"
                    t_phase = time.time()

            elif phase == "approach":
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                raw_ball = detector.detect(frame)
                result = tracker.update(raw_ball, time.time())

                if result["mode"] in ("recenter", "sweep"):
                    sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)
                    log.info("[GOL-AVANCE] Pelota perdida. Volviendo a buscar.")
                    phase = "search"
                    continue

                sbus.burst(result["pan"], result["tilt"], 200, 0, 0, 0, 0)

                if result["detected"]:
                    cx = result["ema_cx"]
                    cy = result["ema_cy"]
                    r = tracker.last_radius or 0
                    offset = abs(cx - fcx)
                    omega = max(-1.0, min(1.0, (cx - fcx) / fcx))
                    v_left = S * 0.5 * (1 + omega * 0.5)
                    v_right = S * 0.5 * (1 - omega * 0.5)
                    m = differential(v_left, v_right, S)
                    sbus.burst(result["pan"], result["tilt"], 200, *m)
                    if r >= BALL_CLOSE_RADIUS * 0.8 and offset < CENTER_THRESH:
                        log.info("[GOL-AVANCE] Cerca. Frenando...")
                        sbus.stop()
                        phase = "brake"
                        t_phase = time.time()
                time.sleep(0.15)

            elif phase == "brake":
                elapsed = time.time() - t_phase
                if elapsed >= GOL_AVANCE_BRAKE_SEC:
                    log.info("[GOL-AVANCE] Golpe!")
                    phase = "strike"
                    t_phase = time.time()

            elif phase == "strike":
                elapsed = time.time() - t_phase
                if elapsed < GOL_AVANCE_SHOT_SEC:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-AVANCE] GOL! Celebrando giro 360...")
                    phase = "celebrate"
                    t_phase = time.time()

            elif phase == "celebrate":
                elapsed = time.time() - t_phase
                if elapsed < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[GOL-AVANCE] Celebracion completada!")
                    break

    except KeyboardInterrupt:
        log.info("[GOL-AVANCE] Interrumpido")
    finally:
        sbus.stop()
        cap.release()
        log.info("[GOL-AVANCE] === FIN ===")
