import time

from hardware import PAN_CENTER, TILT_CENTER, SPIN_360_SEC, differential, log

TEST_SENSOR_DURATION = 60.0
TEST_LINE_SPEED = 200.0


def run_test_line(sbus, ibus, speed):
    baseline = ibus.calibrate_line()
    S = speed
    log.info("=" * 55)
    log.info("[TEST-LINE] === PRUEBA LINE FOLLOWER (%.0fs) ===", TEST_SENSOR_DURATION)
    log.info("[TEST-LINE] Baseline (pasto): %s", baseline)
    log.info("[TEST-LINE] Velocidad avance: %.0f", S)
    log.info("[TEST-LINE] Avanzara recto, si detecta linea blanca:")
    log.info("[TEST-LINE]   frenar -> retroceder 1s -> giro 360 -> reanudar")
    log.info("=" * 55)

    t0 = time.time()
    line_hits = 0
    last_log = t0

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= TEST_SENSOR_DURATION:
                break

            m = differential(S, S, S)
            sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)

            changed, cur = ibus.line_changed(baseline)
            if changed:
                line_hits += 1
                log.warning(
                    "[TEST-LINE] Linea blanca detectada! sensores=%s baseline=%s (hit #%d)",
                    cur,
                    baseline,
                    line_hits,
                )

                sbus.stop()
                time.sleep(0.3)

                log.info("[TEST-LINE] Retrocediendo 1s...")
                m = differential(-S, -S, S)
                sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
                time.sleep(1.3)

                log.info("[TEST-LINE] Giro 360 (%.1fs)...", SPIN_360_SEC)
                t_spin = time.time()
                while time.time() - t_spin < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)

                sbus.stop()
                time.sleep(0.3)
                log.info("[TEST-LINE] Giro completado. Reanudando avance.")
            else:
                now = time.time()
                if now - last_log >= 3.0:
                    log.info(
                        "[TEST-LINE] %.1fs | Avanzando... sensores=%s baseline=%s",
                        elapsed,
                        cur,
                        baseline,
                    )
                    last_log = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("[TEST-LINE] Interrumpido por usuario")
    finally:
        sbus.stop()
        total = time.time() - t0
        log.info("=" * 55)
        log.info("[TEST-LINE] === FIN (%.1fs) ===", total)
        log.info("[TEST-LINE] Lineas detectadas: %d", line_hits)
        log.info("=" * 55)
