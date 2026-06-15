import time

from hardware import PAN_CENTER, TILT_CENTER, log, differential


def run_all_moves(sbus, speed):
    S = speed
    moves = [
        ("Adelante", differential(S, S, S), 2.0),
        ("Atras", differential(-S, -S, S), 2.0),
        ("Giro CW (horario)", differential(S, -S, S), 2.0),
        ("Giro CCW (antihorario)", differential(-S, S, S), 2.0),
        ("Curva Izquierda", differential(S * 0.5, S, S), 3.0),
        ("Curva Derecha", differential(S, S * 0.5, S), 3.0),
    ]
    seqs = 3
    total = len(moves) + seqs
    n = 1

    for name, m, dur in moves:
        log.info("[MOVES] %d/%d: %s (%.1fs)", n, total, name, dur)
        sbus.burst(PAN_CENTER, TILT_CENTER, int(dur * 1000), *m)
        time.sleep(dur + 0.3)
        n += 1

    log.info("[MOVES] %d/%d: Zigzag (4 giros rapidos)", n, total)
    for j in range(4):
        m = differential(S, -S, S) if j % 2 == 0 else differential(-S, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 800, *m)
        time.sleep(1.0)
    n += 1

    log.info("[MOVES] %d/%d: Patron cuadrado (4 lados)", n, total)
    for sname, m in [
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
        ("Giro 90 CW", differential(S, -S, S)),
        ("Adelante", differential(S, S, S)),
    ]:
        log.info("[MOVES]   Cuadrado: %s", sname)
        sbus.burst(PAN_CENTER, TILT_CENTER, 1000, *m)
        time.sleep(1.3)
    n += 1

    log.info("[MOVES] %d/%d: Espiral (curva progresiva)", n, total)
    for ratio in [1.0, 0.7, 0.5, 0.3]:
        m = differential(S * ratio, S, S)
        sbus.burst(PAN_CENTER, TILT_CENTER, 1500, *m)
        time.sleep(1.8)

    log.info("[MOVES] Secuencia completada (%d movimientos)", total)
