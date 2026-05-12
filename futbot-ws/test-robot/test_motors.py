import time

from hardware import PAN_CENTER, TILT_CENTER, log, differential


# ── Motor test (--test) ──────────────────────────────────────────────────────


def run_test(sbus, speed):
    S = speed
    tests = [
        {
            "name": "ADELANTE (derecho)",
            "v_left": S,
            "v_right": S,
            "desc": "Robot debe avanzar recto hacia adelante",
        },
        {
            "name": "GIRO ANTICLOCKWISE (sobre su eje)",
            "v_left": S,
            "v_right": -S,
            "desc": "Robot debe girar a la izquierda sobre su eje",
        },
        {
            "name": "CURVA IZQUIERDA",
            "v_left": S * 0.5,
            "v_right": S,
            "desc": "Robot debe avanzar curvando hacia la izquierda",
        },
    ]

    log.info("=" * 55)
    log.info("[TEST] === PRUEBA DE MOTORES ===")
    log.info("[TEST]")
    log.info("[TEST] Layout fisico:")
    log.info("[TEST]   m1(izq-frontal) | m2(der-frontal)")
    log.info("[TEST]   m3(izq-trasera) | m4(der-trasera)")
    log.info("[TEST]")
    log.info("[TEST] Signo convencion (diferencial):")
    log.info("[TEST]   vL>0, vR>0  =>  adelante")
    log.info("[TEST]   vL<0, vR<0  =>  atras")
    log.info("[TEST]   vL>0, vR<0  =>  giro izquierda (CCW)")
    log.info("[TEST]   vL<0, vR>0  =>  giro derecha (CW)")
    log.info("[TEST]")
    log.info("[TEST] Velocidad: %.0f", S)
    log.info("=" * 55)

    for i, t in enumerate(tests, 1):
        m = differential(t["v_left"], t["v_right"], S)

        log.info("-" * 55)
        log.info("[TEST] %d/%d: %s", i, len(tests), t["name"])
        log.info("[TEST]   v_left=%.2f  v_right=%.2f", t["v_left"], t["v_right"])
        log.info("[TEST]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f", *m)
        log.info("[TEST]   Esperado: %s", t["desc"])
        log.info("[TEST]   Ejecutando 2.0s...")

        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, *m)
        time.sleep(2.3)

        log.info("[TEST]   OK - Verificar si el robot hizo: %s", t["desc"])
        log.info("[TEST]   Pausa 1.5s...")
        time.sleep(1.5)

    log.info("-" * 55)
    log.info("[TEST] Frenando...")
    sbus.stop()
    time.sleep(0.5)
    log.info("[TEST] === FIN PRUEBA ===")
    log.info("[TEST] Si los movimientos no coinciden con lo esperado,")
    log.info("[TEST] revisar el mapeo de motores o invertir signos.")


# ── Diag turns (--diag-turns) ───────────────────────────────────────────────


def run_diag_turns(sbus, speed):
    S = speed
    pause = 1.5

    log.info("=" * 60)
    log.info("[DIAG-T] === DIAGNOSTICO GIROS (patrones de giro) ===")
    log.info("[DIAG-T]")
    log.info("[DIAG-T] Pruebas de giro diferencial")
    log.info("[DIAG-T] Velocidad: %.0f", S)
    log.info("=" * 60)

    tests = [
        {
            "label": "T1",
            "desc": "Solo ruedas izquierda adelante (vL=S, vR=0)",
            "m": differential(S, 0, S),
        },
        {
            "label": "T2",
            "desc": "Solo ruedas derecha adelante (vL=0, vR=S)",
            "m": differential(0, S, S),
        },
        {
            "label": "T3",
            "desc": "Izq adelante + Der atras (giro CCW)",
            "m": differential(S, -S, S),
        },
        {
            "label": "T4",
            "desc": "Izq atras + Der adelante (giro CW)",
            "m": differential(-S, S, S),
        },
    ]

    for t in tests:
        log.info("-" * 60)
        log.info("[DIAG-T] %s: %s", t["label"], t["desc"])
        log.info(
            "[DIAG-T]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f",
            *t["m"],
        )
        log.info("[DIAG-T]   Ejecutando 2.0s...")
        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, *t["m"])
        time.sleep(2.0)
        log.info("[DIAG-T]   OK. Pausa %.1fs...", pause)
        sbus.stop()
        time.sleep(pause)

    log.info("-" * 60)
    log.info("[DIAG-T] === FIN ===")
    log.info("[DIAG-T] Reportar: ¿direccion del robot en T1-T4?")
    log.info("[DIAG-T]   (adelante/atrás/izquierda/derecha/giro CCW/giro CW)")


# ── Diag motors (--diag-motors) ──────────────────────────────────────────────


def run_diag_motors(sbus, speed):
    S = speed
    pause = 1.5

    log.info("=" * 60)
    log.info("[DIAG] === DIAGNOSTICO DE MOTORES ===")
    log.info("[DIAG]")
    log.info("[DIAG] Fase A: Motores individuales (4 pruebas × 2s)")
    log.info("[DIAG] Fase B: Patrones de movimiento (4 pruebas × 2s)")
    log.info("[DIAG]")
    log.info("[DIAG] Layout fisico:")
    log.info("[DIAG]   m1(izq-frontal) | m2(der-frontal)")
    log.info("[DIAG]   m3(izq-trasera) | m4(der-trasera)")
    log.info("[DIAG]")
    log.info("[DIAG] Velocidad: %.0f", S)
    log.info("=" * 60)

    phase_a = [
        {
            "motor": 1,
            "label": "A1",
            "desc": "Motor 1 solo (val=-%.0f) → ¿rueda izq-frontal avanza?" % S,
            "m1": -S,
            "m2": 0,
            "m3": 0,
            "m4": 0,
        },
        {
            "motor": 2,
            "label": "A2",
            "desc": "Motor 2 solo (val=+%.0f) → ¿rueda der-frontal avanza?" % S,
            "m1": 0,
            "m2": S,
            "m3": 0,
            "m4": 0,
        },
        {
            "motor": 3,
            "label": "A3",
            "desc": "Motor 3 solo (val=-%.0f) → ¿rueda izq-trasera avanza?" % S,
            "m1": 0,
            "m2": 0,
            "m3": -S,
            "m4": 0,
        },
        {
            "motor": 4,
            "label": "A4",
            "desc": "Motor 4 solo (val=+%.0f) → ¿rueda der-trasera avanza?" % S,
            "m1": 0,
            "m2": 0,
            "m3": 0,
            "m4": S,
        },
    ]

    phase_b = [
        {
            "label": "B1",
            "desc": "Adelante recto (vL=S, vR=S)",
            "m": differential(S, S, S),
        },
        {
            "label": "B2",
            "desc": "Atras recto (vL=-S, vR=-S)",
            "m": differential(-S, -S, S),
        },
        {
            "label": "B3",
            "desc": "Giro CCW sobre eje (vL=S, vR=-S)",
            "m": differential(S, -S, S),
        },
        {
            "label": "B4",
            "desc": "Giro CW sobre eje (vL=-S, vR=S)",
            "m": differential(-S, S, S),
        },
    ]

    log.info("[DIAG]")
    log.info("[DIAG] >>> FASE A: Motores individuales <<<")
    log.info("[DIAG]")
    for t in phase_a:
        log.info("-" * 60)
        log.info("[DIAG] %s: Motor %d", t["label"], t["motor"])
        log.info(
            "[DIAG]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f",
            t["m1"],
            t["m2"],
            t["m3"],
            t["m4"],
        )
        log.info("[DIAG]   %s", t["desc"])
        log.info("[DIAG]   Ejecutando 2.0s...")
        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, t["m1"], t["m2"], t["m3"], t["m4"])
        time.sleep(2.0)
        log.info("[DIAG]   OK. Pausa %.1fs...", pause)
        sbus.stop()
        time.sleep(pause)

    log.info("[DIAG]")
    log.info("[DIAG] >>> FASE B: Patrones de movimiento <<<")
    log.info("[DIAG]")
    for t in phase_b:
        log.info("-" * 60)
        log.info("[DIAG] %s: %s", t["label"], t["desc"])
        log.info(
            "[DIAG]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f",
            *t["m"],
        )
        log.info("[DIAG]   Ejecutando 2.0s...")
        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, *t["m"])
        time.sleep(2.0)
        log.info("[DIAG]   OK. Pausa %.1fs...", pause)
        sbus.stop()
        time.sleep(pause)

    log.info("-" * 60)
    log.info("[DIAG] Frenando...")
    sbus.stop()
    time.sleep(0.5)
    log.info("[DIAG] === FIN DIAGNOSTICO ===")
    log.info("[DIAG]")
    log.info("[DIAG] REPORTAR para cada prueba:")
    log.info("[DIAG]   A1-A4: ¿Que rueda giro? ¿En que direccion?")
    log.info("[DIAG]   B1-B4: ¿Que direccion tomo el robot?")
    log.info("[DIAG]   (adelante/atrás/giro CCW/giro CW)")