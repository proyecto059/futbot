import time

from hardware import PAN_CENTER, TILT_CENTER, SPIN_360_SEC, differential, log

TEST_SENSOR_DURATION = 60.0
TEST_SONIC_SPEED = 200.0
TEST_SONIC_THRESHOLD = 200


# ── Ultrasonic test (--test-sonic) ───────────────────────────────────────────


def run_test_sonic(sbus, ibus, speed):
    S = speed
    log.info("=" * 55)
    log.info("[TEST-SONIC] === PRUEBA ULTRASONICO (%.0fs) ===", TEST_SENSOR_DURATION)
    log.info("[TEST-SONIC] Velocidad avance: %.0f", S)
    log.info("[TEST-SONIC] Umbral: %dmm", TEST_SONIC_THRESHOLD)
    log.info("[TEST-SONIC] Avanzara recto, si obstaculo <%dmm:", TEST_SONIC_THRESHOLD)
    log.info("[TEST-SONIC]   frenar → retroceder 1s → giro 360° → reanudar")
    log.info("=" * 55)

    t0 = time.time()
    obstacles = 0
    last_log = t0

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= TEST_SENSOR_DURATION:
                break

            dist = ibus.read_ultrasonic()

            if dist < TEST_SONIC_THRESHOLD:
                obstacles += 1
                log.warning(
                    "[TEST-SONIC] Obstaculo a %dmm! (hit #%d)",
                    dist,
                    obstacles,
                )

                sbus.stop()
                time.sleep(0.3)

                log.info("[TEST-SONIC] Retrocediendo 1s...")
                m = differential(-S, -S, S)
                sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
                time.sleep(1.3)

                log.info("[TEST-SONIC] Giro 360 (%.1fs)...", SPIN_360_SEC)
                t_spin = time.time()
                while time.time() - t_spin < SPIN_360_SEC:
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    time.sleep(0.15)

                sbus.stop()
                time.sleep(0.3)
                log.info("[TEST-SONIC] Giro completado. Reanudando avance.")
            else:
                m = differential(S, S, S)
                sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)

                now = time.time()
                if now - last_log >= 2.0:
                    log.info(
                        "[TEST-SONIC] %.1fs | Avanzando... distancia: %dmm",
                        elapsed,
                        dist,
                    )
                    last_log = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("[TEST-SONIC] Interrumpido por usuario")
    finally:
        sbus.stop()
        total = time.time() - t0
        log.info("=" * 55)
        log.info("[TEST-SONIC] === FIN (%.1fs) ===", total)
        log.info("[TEST-SONIC] Obstaculos detectados: %d", obstacles)
        log.info("=" * 55)