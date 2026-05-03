"""Constantes del pipeline2 — modo simple: ver pelota → avanzar.

Fuente única de verdad para velocidades y nombres de estado.
"""

# ── Estados FSM ─────────────────────────────────────────────────────────
IDLE = "IDLE"          # no ve pelota → motores detenidos
ADVANCE = "ADVANCE"    # ve pelota → motores hacia adelante

# ── Velocidades ─────────────────────────────────────────────────────────
ADVANCE_SPEED = 120    # velocidad de avance (0-255)
ADVANCE_DUR_MS = 140   # duración de cada burst de avance (ms)
STOP_DUR_MS = 100      # duración del comando stop (ms)