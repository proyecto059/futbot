#!/usr/bin/env python3

import argparse
import sys
import time
from enum import Enum, auto

from hardware import (
    CENTER_THRESH,
    DEFAULT_SPEED,
    OBSTACLE_MM,
    PAN_CENTER,
    PAN_MAX,
    PAN_MIN,
    PAN_STEP,
    RETREAT_SEC,
    RETREAT_SPEED,
    SHOT_SEC,
    SHOT_SPEED,
    AIM_STRAFE_SEC,
    BALL_CLOSE_RADIUS,
    SPIN_360_SEC,
    TILT_CENTER,
    SharedI2CBus,
    SerialBus,
    detect_ball,
    find_camera,
    log,
    mecanum,
)
from test_line import run_test_line
from test_motors import run_diag_motors, run_diag_strafe, run_test
from test_omni import run_all_omni
from test_servos import run_test_servos
from test_sonic import run_test_sonic


# ── State machine ────────────────────────────────────────────────────────────


class State(Enum):
    SEARCHING = auto()
    APPROACHING = auto()
    AIMING = auto()
    ANGULAR_SHOT = auto()
    SPINNING = auto()
    DONE = auto()


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser(
        description="TurboPi Hiwonder – Buscar pelota naranja, tiro angular, giro 360"
    )
    ap.add_argument(
        "--all-omni",
        action="store_true",
        help="Ejecutar todos los movimientos omnidireccionales antes de buscar pelota",
    )
    ap.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help="Velocidad base (default: 250)",
    )
    ap.add_argument(
        "--test",
        action="store_true",
        help="Prueba de 3 movimientos para verificar formula mecanum y mapeo de motores",
    )
    ap.add_argument(
        "--test-servo",
        action="store_true",
        help="Seguir pelota naranja con servos durante 60s (sin mover ruedas)",
    )
    ap.add_argument(
        "--test-line",
        action="store_true",
        help="Avanzar, detectar linea blanca → retroceder + giro 360",
    )
    ap.add_argument(
        "--test-sonic",
        action="store_true",
        help="Avanzar, obstaculo <200mm → retroceder + giro 360",
    )
    ap.add_argument(
        "--no-ultrasonic", action="store_true", help="Deshabilitar ultrasonico"
    )
    ap.add_argument(
        "--no-line-follower", action="store_true", help="Deshabilitar line follower"
    )
    ap.add_argument(
        "--diag-motors",
        action="store_true",
        help="Diagnostico individual de motores (8 pruebas: 4 individuales + 4 strafe)",
    )
    ap.add_argument(
        "--diag-strafe",
        action="store_true",
        help="Diagnostico de pares diagonales para descubrir strafe (4 pruebas)",
    )
    args = ap.parse_args()

    S = args.speed

    log.info("=" * 50)
    log.info("TurboPi – Iniciando sistema")
    log.info(
        "  Velocidad: %.0f | Test: %s | All-omni: %s | Diag: %s",
        S,
        args.test,
        args.all_omni,
        args.diag_motors,
    )
    log.info(
        "  Ultrasonico: %s | Line follower: %s",
        not args.no_ultrasonic,
        not args.no_line_follower,
    )
    log.info("=" * 50)

    # ── Init UART (siempre necesario) ──
    sbus = SerialBus()

    log.info("Centrando camara (servos)...")
    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(1.5)

    # ── Test mode: solo UART, 3 movimientos, salir ──
    if args.test:
        try:
            run_test(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (test)")
        return

    # ── Diag-motors mode: solo UART, diagnostico individual ──
    if args.diag_motors:
        try:
            run_diag_motors(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (diag-motors)")
        return

    # ── Diag-strafe mode: solo UART, pares diagonales ──
    if args.diag_strafe:
        try:
            run_diag_strafe(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (diag-strafe)")
        return

    # ── Test-servo mode: UART + camara, seguir pelota con servos ──
    if args.test_servo:
        try:
            run_test_servos(sbus)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (test-servos)")
        return

    # ── Init I2C (no needed for test) ──
    ibus = SharedI2CBus()

    # ── Test-line mode: UART + I2C, probar line follower ──
    if args.test_line:
        try:
            run_test_line(sbus, ibus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus.close()
            log.info("TurboPi – Fin (test-line)")
        return

    # ── Test-sonic mode: UART + I2C, probar ultrasonico ──
    if args.test_sonic:
        try:
            run_test_sonic(sbus, ibus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus.close()
            log.info("TurboPi – Fin (test-sonic)")
        return

    # ── Camera ──
    cap, fw = find_camera()
    if not cap:
        log.error("No se detecto camara USB. Abortando.")
        sbus.close()
        ibus.close()
        sys.exit(1)
    fcx = fw // 2

    # ── Calibrate line follower ──
    baseline = [False] * 4
    if not args.no_line_follower:
        baseline = ibus.calibrate_line()

    # ── All-omni demo ──
    if args.all_omni:
        run_all_omni(sbus, S)
        log.info("Demo omnidireccional terminada. Esperando 2s...")
        time.sleep(2)

    # ── State machine ──
    state = State.SEARCHING
    pan = PAN_CENTER
    pdir = 1
    t_aim = t_shot = t_spin = 0.0

    log.info("Iniciando busqueda de pelota naranja...")

    try:
        while state != State.DONE:
            # ── Safety: ultrasonico ──
            if not args.no_ultrasonic:
                dist = ibus.read_ultrasonic()
                if dist < OBSTACLE_MM and state not in (
                    State.ANGULAR_SHOT,
                    State.SPINNING,
                ):
                    log.warning(
                        "[SAFETY] Obstaculo a %dmm! Frenando y retrocediendo", dist
                    )
                    sbus.stop(pan)
                    time.sleep(0.2)
                    sbus.burst(
                        pan,
                        TILT_CENTER,
                        int(RETREAT_SEC * 1000),
                        RETREAT_SPEED,
                        -RETREAT_SPEED,
                        RETREAT_SPEED,
                        -RETREAT_SPEED,
                    )
                    time.sleep(RETREAT_SEC + 0.2)
                    continue

            # ── Safety: line follower ──
            if not args.no_line_follower:
                changed, cur = ibus.line_changed(baseline)
                if changed and state not in (State.ANGULAR_SHOT, State.SPINNING):
                    log.warning(
                        "[SAFETY] Linea blanca detectada! sensores=%s baseline=%s",
                        cur,
                        baseline,
                    )
                    sbus.stop(pan)
                    time.sleep(0.2)
                    sbus.burst(
                        pan,
                        TILT_CENTER,
                        int(RETREAT_SEC * 1000),
                        RETREAT_SPEED,
                        -RETREAT_SPEED,
                        RETREAT_SPEED,
                        -RETREAT_SPEED,
                    )
                    time.sleep(RETREAT_SEC + 0.3)
                    if state == State.APPROACHING:
                        state = State.SEARCHING
                        pan = PAN_CENTER
                        pdir = 1
                        log.info("[SEARCHING] Volviendo a buscar despues de linea")
                    continue

            # ── Camera frame ──
            ok, frame = cap.read()
            if not ok:
                log.warning("Frame invalido de camara")
                time.sleep(0.05)
                continue

            ball = detect_ball(frame)

            # ── SEARCHING ──
            if state == State.SEARCHING:
                if ball:
                    cx, cy, r = ball
                    log.info(
                        "[SEARCHING] Pelota detectada! cx=%d cy=%d radio=%.0f",
                        cx,
                        cy,
                        r,
                    )
                    pan = max(PAN_MIN, min(PAN_MAX, int(cx / fw * 180)))
                    state = State.APPROACHING
                    log.info("[APPROACHING] Acercandose a pelota (pan=%d)", pan)
                else:
                    pan += PAN_STEP * pdir
                    if pan >= PAN_MAX:
                        pan = PAN_MAX
                        pdir = -1
                    elif pan <= PAN_MIN:
                        pan = PAN_MIN
                        pdir = 1
                    sbus.burst(pan, TILT_CENTER, 200, 0, 0, 0, 0)
                    log.debug("[SEARCHING] Barrido pan=%d", pan)
                    time.sleep(0.15)

            # ── APPROACHING ──
            elif state == State.APPROACHING:
                if ball:
                    cx, cy, r = ball
                    pan = max(PAN_MIN, min(PAN_MAX, int(cx / fw * 180)))
                    offset = abs(cx - fcx)

                    if r >= BALL_CLOSE_RADIUS and offset < CENTER_THRESH:
                        log.info(
                            "[APPROACHING] Pelota centrada y cerca (radio=%.0f, offset=%d)",
                            r,
                            offset,
                        )
                        state = State.AIMING
                        t_aim = time.time()
                        log.info("[AIMING] Posicionando para tiro angular...")
                    else:
                        omega = max(-1.0, min(1.0, (cx - fcx) / fcx * 0.5))
                        m = mecanum(S * 0.6, 90, omega, S)
                        sbus.burst(pan, TILT_CENTER, 200, *m)
                        log.info(
                            "[APPROACHING] Avanzando cx=%d radio=%.0f dist_us=%dmm",
                            cx,
                            r,
                            dist if not args.no_ultrasonic else -1,
                        )
                        time.sleep(0.15)
                else:
                    log.info("[APPROACHING] Pelota perdida. Volviendo a buscar.")
                    state = State.SEARCHING
                    pan = PAN_CENTER
                    pdir = 1

            # ── AIMING ──
            elif state == State.AIMING:
                dt = time.time() - t_aim
                if dt < AIM_STRAFE_SEC:
                    sbus.burst(
                        PAN_CENTER,
                        TILT_CENTER,
                        200,
                        S * 0.5,
                        S * 0.5,
                        -S * 0.5,
                        -S * 0.5,
                    )
                    log.info(
                        "[AIMING] Strafe izquierda para posicion angular (%.1f/%.1fs)",
                        dt,
                        AIM_STRAFE_SEC,
                    )
                    time.sleep(0.15)
                else:
                    log.info("[AIMING] Posicion lista. Ejecutando tiro angular!")
                    state = State.ANGULAR_SHOT
                    t_shot = time.time()

            # ── ANGULAR SHOT ──
            elif state == State.ANGULAR_SHOT:
                dt = time.time() - t_shot
                if dt < SHOT_SEC:
                    m = mecanum(SHOT_SPEED, 45, 0)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info(
                        "[ANGULAR_SHOT] Tiro diagonal adelante-derecha! (%.1f/%.1fs)",
                        dt,
                        SHOT_SEC,
                    )
                    time.sleep(0.15)
                else:
                    sbus.stop()
                    log.info("[ANGULAR_SHOT] Tiro completado!")
                    state = State.SPINNING
                    t_spin = time.time()
                    log.info(
                        "[SPINNING] Giro 360 celebratorio (%.1fs)...", SPIN_360_SEC
                    )

            # ── SPINNING ──
            elif state == State.SPINNING:
                dt = time.time() - t_spin
                if dt < SPIN_360_SEC:
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, -S, -S, -S, -S)
                    log.info("[SPINNING] Girando... (%.1f/%.1fs)", dt, SPIN_360_SEC)
                    time.sleep(0.15)
                else:
                    log.info("[SPINNING] Giro completado!")
                    state = State.DONE

    except KeyboardInterrupt:
        log.info("Interrumpido por usuario (Ctrl+C)")
    finally:
        log.info("Deteniendo motores y cerrando hardware...")
        sbus.stop()
        sbus.close()
        if cap:
            cap.release()
        ibus.close()
        log.info("=" * 50)
        log.info("TurboPi – Fin")
        log.info("=" * 50)


if __name__ == "__main__":
    main()
