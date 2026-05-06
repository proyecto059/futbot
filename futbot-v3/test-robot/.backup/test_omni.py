import time

from hardware import PAN_CENTER, TILT_CENTER, log, mecanum


# ── Omnidirectional movements (--all-omni) ──────────────────────────────────


def run_all_omni(sbus, speed):
    S = speed
    moves = [
        ("Adelante", (-S, S, -S, S), 2.0),
        ("Atras", (S, -S, S, -S), 2.0),
        ("Strafe Derecha", (-S, -S, S, S), 2.0),
        ("Strafe Izquierda", (S, S, -S, -S), 2.0),
        ("Diagonal Adelante-Der", (-S, 0, 0, S), 2.0),
        ("Diagonal Adelante-Izq", (0, S, -S, 0), 2.0),
        ("Diagonal Atras-Der", (0, -S, S, 0), 2.0),
        ("Diagonal Atras-Izq", (S, 0, 0, -S), 2.0),
        ("Giro Horario (CW)", (-S, -S, -S, -S), 2.0),
        ("Giro Antihorario (CCW)", (S, S, S, S), 2.0),
        ("Curva Adelante-CW", mecanum(S * 0.8, 90, 1.0, S), 3.0),
        ("Curva Adelante-CCW", mecanum(S * 0.8, 90, -1.0, S), 3.0),
    ]
    seqs = 3
    total = len(moves) + seqs
    n = 1

    for name, m, dur in moves:
        log.info("[OMNI] %d/%d: %s (%.1fs)", n, total, name, dur)
        sbus.burst(PAN_CENTER, TILT_CENTER, int(dur * 1000), *m)
        time.sleep(dur + 0.3)
        n += 1

    log.info("[OMNI] %d/%d: Zigzag (4 cambios rapidos)", n, total)
    for j in range(4):
        m = (S, S, -S, -S) if j % 2 == 0 else (-S, -S, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 800, *m)
        time.sleep(1.0)
    n += 1

    log.info("[OMNI] %d/%d: Patron cuadrado (4 lados)", n, total)
    for sname, m in [
        ("Adelante", (-S, S, -S, S)),
        ("Derecha", (-S, -S, S, S)),
        ("Atras", (S, -S, S, -S)),
        ("Izquierda", (S, S, -S, -S)),
    ]:
        log.info("[OMNI]   Cuadrado: %s", sname)
        sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
        time.sleep(1.3)
    n += 1

    log.info("[OMNI] %d/%d: Figura 8 (dos curvas opuestas)", n, total)
    for label, m in [
        ("Curva CW", mecanum(S * 0.7, 90, 0.8, S)),
        ("Curva CCW", mecanum(S * 0.7, 90, -0.8, S)),
    ]:
        log.info("[OMNI]   Fig8: %s", label)
        sbus.burst(PAN_CENTER, TILT_CENTER, 3000, *m)
        time.sleep(3.3)

    log.info("[OMNI] Secuencia omnidireccional completada (%d movimientos)", total)
