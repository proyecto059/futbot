"""Constantes del pipeline FSM.

Fuente única de verdad para velocidades, ganancias, umbrales y nombres de
estado del autómata SEARCH / CHASE / AVOID.
"""

# ── Chase ────────────────────────────────────────────────────────────────
CHASE_SPEED_BASE = 80  # velocidad base de avance (0-255)
CHASE_ROT_GAIN = 0.8  # ganancia proporcional de rotación
CHASE_DEADBAND_PX = 16  # zona muerta en píxeles (±)
KICK_RADIUS_PX = 50  # radio de bola para activar kick directo
CHASE_MISS_SECS = 0.8  # timeout para declarar pelota perdida

# ── Chase blind (pelota perdida recientemente) ──────────────────────────
CHASE_BLIND_SPEED = 60  # velocidad de escaneo a ciegas
CHASE_BLIND_MS = 100  # duración del paso de escaneo ciego (ms)
CHASE_BLIND_SCAN_SECS = 0.2  # intervalo entre escaneos ciegos

# ── Search ───────────────────────────────────────────────────────────────
SEARCH_TURN_SPEED = 255  # velocidad de giro en búsqueda
SEARCH_TURN_MS = 250  # duración del paso de giro (ms)
SEARCH_SCAN_SECS = 0.3  # intervalo entre giros de búsqueda

# ── Avoid ────────────────────────────────────────────────────────────────
AVOID_REVERSE_SPEED = 110  # velocidad de retroceso
AVOID_REVERSE_MS = 220  # duración del retroceso (ms)
AVOID_TURN_SPEED = 115  # velocidad de giro en evasión
AVOID_TURN_MS = 180  # duración del giro (ms)
AVOID_MAX_STEPS = 5  # pasos máximos del plan de evasión

# ── Umbrales de detección ───────────────────────────────────────────────
DIST_TRIGGER_MM = 250  # distancia ultrasónica para activar avoid
BALL_TOUCH_DIST_MM = 400  # distancia para suprimir avoid (pelota cerca)
BALL_TOUCH_MAX_SECS = 3.0  # ventana temporal de "pelota reciente"

# ── Nombres de estado FSM ───────────────────────────────────────────────
SEARCH = "SEARCH"
CHASE = "CHASE"
AVOID = "AVOID"
