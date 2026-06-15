"""Constantes del pipeline FSM.

Fuente única de verdad para velocidades, ganancias, umbrales y nombres de
estado del autómata SEARCH / CHASE.
"""

# ── Chase ────────────────────────────────────────────────────────────────
CHASE_SPEED_BASE = 80          # velocidad base de avance (0-255)
CHASE_ROT_GAIN = 0.8           # ganancia proporcional de rotacion
CHASE_DEADBAND_PX = 16         # zona muerta en pixeles (+-)
KICK_RADIUS_PX = 50            # radio de bola para activar kick directo
CHASE_MISS_SECS = 0.8          # timeout para declarar pelota perdida

# ── Chase blind (pelota perdida recientemente) ───────────────────────────
CHASE_BLIND_SPEED = 60         # velocidad de escaneo a ciegas
CHASE_BLIND_MS = 100           # duracion del paso de escaneo ciego (ms)
CHASE_BLIND_SCAN_SECS = 0.2    # intervalo entre escaneos ciegos

# ── Search ───────────────────────────────────────────────────────────────
SEARCH_TURN_SPEED = 255        # velocidad de giro en busqueda
SEARCH_TURN_MS = 250           # duracion del paso de giro (ms)
SEARCH_SCAN_SECS = 0.3         # intervalo entre giros de busqueda

# ── Nombres de estado FSM ────────────────────────────────────────────────
SEARCH = "SEARCH"
CHASE = "CHASE"
