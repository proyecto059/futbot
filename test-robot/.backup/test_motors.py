import math
import time

from hardware import PAN_CENTER, TILT_CENTER, log, mecanum


# ── Motor test (--test) ──────────────────────────────────────────────────────


def run_test(sbus, speed):
    S = speed
    tests = [
        {
            "name": "ADELANTE (derecho)",
            "vel": S,
            "deg": 90,
            "omega": 0,
            "desc": "Robot debe avanzar recto hacia adelante",
        },
        {
            "name": "LATERAL DERECHA (strafe)",
            "vel": S,
            "deg": 0,
            "omega": 0,
            "desc": "Robot debe moverse lateralmente a la derecha sin rotar",
        },
        {
            "name": "DIAGONAL ATRAS-IZQUIERDA",
            "vel": S,
            "deg": 225,
            "omega": 0,
            "desc": "Robot debe moverse en diagonal hacia atras-izquierda",
        },
    ]

    log.info("=" * 55)
    log.info("[TEST] === PRUEBA DE MOTORES ===")
    log.info("[TEST]")
    log.info("[TEST] Layout fisico:")
    log.info("[TEST]   m1(izq-frontal) | m2(der-frontal)")
    log.info("[TEST]   m3(izq-trasera) | m4(der-trasera)")
    log.info("[TEST]")
    log.info("[TEST] Signo convencion (burst_simultaneo):")
    log.info("[TEST]   m1<0, m2>0, m3<0, m4>0  =>  adelante")
    log.info("[TEST]   m1>0, m2<0, m3>0, m4<0  =>  atras")
    log.info("[TEST]   m1<0, m2<0, m3>0, m4>0  =>  strafe derecha")
    log.info("[TEST]   m1>0, m2>0, m3<0, m4<0  =>  strafe izquierda")
    log.info("[TEST]")
    log.info("[TEST] Velocidad: %.0f", S)
    log.info("=" * 55)

    for i, t in enumerate(tests, 1):
        m = mecanum(t["vel"], t["deg"], t["omega"], S)
        vx = t["vel"] * math.cos(math.radians(t["deg"]))
        vy = t["vel"] * math.sin(math.radians(t["deg"]))

        log.info("-" * 55)
        log.info("[TEST] %d/%d: %s", i, len(tests), t["name"])
        log.info(
            "[TEST]   Parametros: vel=%.0f  dir=%d°  omega=%.1f",
            t["vel"],
            t["deg"],
            t["omega"],
        )
        log.info("[TEST]   vx=%.2f  vy=%.2f  (descomp. polar)", vx, vy)
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


# ── Diag strafe (--diag-strafe) ──────────────────────────────────────────────


def run_diag_strafe(sbus, speed):
    S = speed
    pause = 1.5

    log.info("=" * 60)
    log.info("[DIAG-S] === DIAGNOSTICO STRAFE (pares diagonales) ===")
    log.info("[DIAG-S]")
    log.info("[DIAG-S] Solo 2 motores activos por prueba")
    log.info("[DIAG-S] Velocidad: %.0f", S)
    log.info("=" * 60)

    tests = [
        {
            "label": "D1",
            "desc": "m1=-S (FL adelante) + m4=+S (RR adelante)",
            "m1": -S,
            "m2": 0,
            "m3": 0,
            "m4": S,
        },
        {
            "label": "D2",
            "desc": "m2=-S (FR atras) + m3=-S (RL atras)",
            "m1": 0,
            "m2": -S,
            "m3": -S,
            "m4": 0,
        },
        {
            "label": "D3",
            "desc": "m1=+S (FL atras) + m4=-S (RR atras)",
            "m1": S,
            "m2": 0,
            "m3": 0,
            "m4": -S,
        },
        {
            "label": "D4",
            "desc": "m2=+S (FR adelante) + m3=+S (RL adelante)",
            "m1": 0,
            "m2": S,
            "m3": S,
            "m4": 0,
        },
    ]

    for t in tests:
        log.info("-" * 60)
        log.info("[DIAG-S] %s: %s", t["label"], t["desc"])
        log.info(
            "[DIAG-S]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f",
            t["m1"],
            t["m2"],
            t["m3"],
            t["m4"],
        )
        log.info("[DIAG-S]   Ejecutando 2.0s...")
        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, t["m1"], t["m2"], t["m3"], t["m4"])
        time.sleep(2.0)
        log.info("[DIAG-S]   OK. Pausa %.1fs...", pause)
        sbus.stop()
        time.sleep(pause)

    log.info("-" * 60)
    log.info("[DIAG-S] === FIN ===")
    log.info("[DIAG-S] Reportar: ¿direccion del robot en D1-D4?")
    log.info("[DIAG-S]   (adelante/atrás/strafe der/strafe izq/diagonal/giro)")


# ── Diag motors (--diag-motors) ──────────────────────────────────────────────


def run_diag_motors(sbus, speed):
    S = speed
    pause = 1.5

    log.info("=" * 60)
    log.info("[DIAG] === DIAGNOSTICO DE MOTORES ===")
    log.info("[DIAG]")
    log.info("[DIAG] Fase A: Motores individuales (4 pruebas × 2s)")
    log.info("[DIAG] Fase B: Patrones strafe (4 pruebas × 2s)")
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
            "desc": "Strafe derecha SDK (m1=-S, m2=-S, m3=+S, m4=+S)",
            "m1": -S,
            "m2": -S,
            "m3": S,
            "m4": S,
        },
        {
            "label": "B2",
            "desc": "Strafe izquierda SDK (m1=+S, m2=+S, m3=-S, m4=-S)",
            "m1": S,
            "m2": S,
            "m3": -S,
            "m4": -S,
        },
        {
            "label": "B3",
            "desc": "Diagonal alt 1 (m1=-S, m2=+S, m3=+S, m4=-S)",
            "m1": -S,
            "m2": S,
            "m3": S,
            "m4": -S,
        },
        {
            "label": "B4",
            "desc": "Diagonal alt 2 (m1=+S, m2=-S, m3=-S, m4=+S)",
            "m1": S,
            "m2": -S,
            "m3": -S,
            "m4": S,
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
    log.info("[DIAG] >>> FASE B: Patrones strafe <<<")
    log.info("[DIAG]")
    for t in phase_b:
        log.info("-" * 60)
        log.info("[DIAG] %s: %s", t["label"], t["desc"])
        log.info(
            "[DIAG]   m1=%+7.1f  m2=%+7.1f  m3=%+7.1f  m4=%+7.1f",
            t["m1"],
            t["m2"],
            t["m3"],
            t["m4"],
        )
        log.info("[DIAG]   Ejecutando 2.0s...")
        sbus.burst(PAN_CENTER, TILT_CENTER, 2000, t["m1"], t["m2"], t["m3"], t["m4"])
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
    log.info("[DIAG]   (adelante/atrás/izquierda/derecha/diagonal/giro)")