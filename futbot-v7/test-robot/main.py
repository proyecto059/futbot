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
    BALL_CLOSE_RADIUS,
    SPIN_360_SEC,
    TILT_CENTER,
    SharedI2CBus,
    SerialBus,
    detect_ball,
    find_camera,
    log,
    differential,
    map_x_to_pan,
)
from test_line import run_test_line
from test_motors import run_diag_motors, run_diag_turns, run_test
from test_omni import run_all_moves
from test_servo_motors import run_test_servo_motors
from test_servos import run_diag_servos, run_test_servos
from test_sonic import run_test_sonic
from test_gol import run_gol_giro, run_gol_avance
from play_futbot import run_play_futbot
from diag_center_kick import run_diag_center_kick


# ── State machine ────────────────────────────────────────────────────────────


class State(Enum):
    SEARCHING = auto()
    APPROACHING = auto()
    AIMING = auto()
    ANGULAR_SHOT = auto()
    SPINNING = auto()
    DONE = auto()


# ── Main ─────────────────────────────────────────────────────────────────────


APPROACH_LOST_CONFIRM_FRAMES = 3
APPROACH_HOLD_SEC = 0.4


def should_hold_approach(
    miss_count,
    last_seen_ts,
    now_ts,
    miss_confirm_frames=APPROACH_LOST_CONFIRM_FRAMES,
    hold_sec=APPROACH_HOLD_SEC,
):
    return miss_count <= miss_confirm_frames or (now_ts - last_seen_ts) < hold_sec


def main():
    ap = argparse.ArgumentParser(
        description="TurboPi Hiwonder – Buscar pelota naranja, tiro angular, giro 360"
    )
    ap.add_argument(
        "--all-moves",
        action="store_true",
        help="Ejecutar todos los movimientos diferenciales antes de buscar pelota",
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
        help="Prueba de 3 movimientos para verificar formula diferencial y mapeo de motores",
    )
    ap.add_argument(
        "--test-servo",
        action="store_true",
        help="Seguir pelota naranja con servos durante 60s (sin mover ruedas)",
    )
    ap.add_argument(
        "--test-servo-motors",
        action="store_true",
        help="Seguir pelota con servos + motores + ultrasonico 120s",
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
        help="Diagnostico individual de motores (8 pruebas: 4 individuales + 4 giros)",
    )
    ap.add_argument(
        "--diag-turns",
        action="store_true",
        help="Diagnostico de patrones de giro diferencial (4 pruebas)",
    )
    ap.add_argument(
        "--diag-servos",
        action="store_true",
        help="Diagnostico de servos: tilt arriba/abajo y pan izquierda/derecha",
    )
    ap.add_argument(
        "--gol-giro",
        action="store_true",
        help="Test gol: buscar pelota -> avanzar -> girar -> avanzar -> golpear",
    )
    ap.add_argument(
        "--gol-avance",
        action="store_true",
        help="Test gol: buscar pelota -> acercar -> frenar -> golpe",
    )
    ap.add_argument(
        "--play-futbot",
        action="store_true",
        help="Jugar futbol: buscar pelota -> acercar -> patear (push/angled/spin)",
    )
    ap.add_argument(
        "--diag-center-kick",
        action="store_true",
        help="Diag: buscar pelota -> alinear chasis -> patear (3 veces)",
    )
    args = ap.parse_args()

    S = args.speed

    log.info("=" * 50)
    log.info("TurboPi – Iniciando sistema")
    log.info(
        "  Velocidad: %.0f | Test: %s | All-moves: %s | Diag: %s",
        S,
        args.test,
        args.all_moves,
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

    # ── Diag-turns mode: solo UART, patrones de giro ──
    if args.diag_turns:
        try:
            run_diag_turns(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (diag-turns)")
        return

    # ── Diag-servos mode: solo UART, barrido de servos ──
    if args.diag_servos:
        try:
            run_diag_servos(sbus)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.close()
            log.info("TurboPi – Fin (diag-servos)")
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

    # ── Test-servo-motors mode: UART + I2C + camara ──
    if args.test_servo_motors:
        ibus_sm = SharedI2CBus()
        try:
            run_test_servo_motors(sbus, ibus_sm)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus_sm.close()
            log.info("TurboPi – Fin (test-servo-motors)")
        return

    # ── Gol-giro mode: UART + camara, gol con giro ──
    if args.gol_giro:
        try:
            run_gol_giro(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (gol-giro)")
        return

    # ── Gol-avance mode: UART + camara, gol avanzando ──
    if args.gol_avance:
        try:
            run_gol_avance(sbus, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            log.info("TurboPi – Fin (gol-avance)")
        return

    if args.play_futbot:
        ibus_pf = SharedI2CBus()
        try:
            run_play_futbot(sbus, ibus_pf, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus_pf.close()
            log.info("TurboPi – Fin (play-futbot)")
        return

    if args.diag_center_kick:
        ibus_d = SharedI2CBus()
        try:
            run_diag_center_kick(sbus, ibus_d, S)
        except KeyboardInterrupt:
            log.info("Interrumpido por usuario (Ctrl+C)")
        finally:
            sbus.stop()
            sbus.close()
            ibus_d.close()
            log.info("TurboPi – Fin (diag-center-kick)")
        return

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
    cap, fw, exp = find_camera()
    if not cap:
        log.error("No se detecto camara USB. Abortando.")
        sbus.close()
        ibus.close()
        sys.exit(1)
    fcx = fw // 2

    # ── Calibrate line follower ──
    baseline = [True, True, True, True]
    if not args.no_line_follower:
        baseline = ibus.calibrate_line()

    # ── All-moves demo ──
    if args.all_moves:
        run_all_moves(sbus, S)
        log.info("Demo de movimientos terminada. Esperando 2s...")
        time.sleep(2)

    # ── State machine ──
    state = State.SEARCHING
    pan = PAN_CENTER
    pdir = 1
    approach_last_seen_ts = 0.0
    approach_miss_count = 0
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
                    m = differential(-RETREAT_SPEED, -RETREAT_SPEED, RETREAT_SPEED)
                    sbus.burst(
                        pan,
                        TILT_CENTER,
                        int(RETREAT_SEC * 1000),
                        *m,
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
                    m = differential(-RETREAT_SPEED, -RETREAT_SPEED, RETREAT_SPEED)
                    sbus.burst(
                        pan,
                        TILT_CENTER,
                        int(RETREAT_SEC * 1000),
                        *m,
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
                    pan = map_x_to_pan(cx, fw)
                    approach_last_seen_ts = time.time()
                    approach_miss_count = 0
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
                    pan = map_x_to_pan(cx, fw)
                    approach_miss_count = 0
                    approach_last_seen_ts = time.time()
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
                        v_left = S * 0.6 * (1 + omega)
                        v_right = S * 0.6 * (1 - omega)
                        m = differential(v_left, v_right, S)
                        sbus.burst(pan, TILT_CENTER, 200, *m)
                        log.info(
                            "[APPROACHING] Avanzando cx=%d radio=%.0f dist_us=%dmm",
                            cx,
                            r,
                            dist if not args.no_ultrasonic else -1,
                        )
                        time.sleep(0.15)
                else:
                    approach_miss_count += 1
                    now = time.time()
                    holding = should_hold_approach(
                        approach_miss_count,
                        approach_last_seen_ts,
                        now,
                    )
                    if holding:
                        log.info(
                            "[APPROACHING] Pelota no visible (miss=%d). Manteniendo pan=%d.",
                            approach_miss_count,
                            pan,
                        )
                        continue
                    log.info("[APPROACHING] Pelota perdida. Volviendo a buscar.")
                    state = State.SEARCHING
                    pan = PAN_CENTER
                    pdir = 1

            # ── AIMING ──
            elif state == State.AIMING:
                dt = time.time() - t_aim
                if dt < 0.8:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info("[AIMING] Avanzando recto (%.1f/0.8s)", dt)
                    time.sleep(0.15)
                elif dt < 1.3:
                    m = differential(-S * 0.5, S * 0.5, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info("[AIMING] Girando ~45 (%.1f/1.3s)", dt)
                    time.sleep(0.15)
                elif dt < 2.8:
                    m = differential(S, S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info("[AIMING] Avanzando al arco (%.1f/2.8s)", dt)
                    time.sleep(0.15)
                else:
                    log.info("[AIMING] Posicion lista. Ejecutando tiro!")
                    state = State.ANGULAR_SHOT
                    t_shot = time.time()

            # ── ANGULAR SHOT ──
            elif state == State.ANGULAR_SHOT:
                dt = time.time() - t_shot
                if dt < SHOT_SEC:
                    m = differential(SHOT_SPEED, SHOT_SPEED, SHOT_SPEED)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
                    log.info(
                        "[ANGULAR_SHOT] Tiro hacia adelante! (%.1f/%.1fs)",
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
                    m = differential(S, -S, S)
                    sbus.burst(PAN_CENTER, TILT_CENTER, 200, *m)
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
