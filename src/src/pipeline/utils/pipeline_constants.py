"""Constantes del pipeline FSM — parámetros de comportamiento del robot.

Edita estos valores para ajustar la agresividad, velocidad y sensibilidad
del robot sin tocar la lógica del pipeline.
"""

# ── Estados de la FSM ────────────────────────────────────────────────────────
SEARCH = "SEARCH"
CHASE  = "CHASE"
AVOID  = "AVOID"

# ── Umbrales de detección ────────────────────────────────────────────────────
DIST_TRIGGER_MM    = 250    # distancia ultrasonido para activar AVOID (mm)
KICK_RADIUS_PX     = 50     # radio mínimo de la pelota para patear (px)
BALL_TOUCH_DIST_MM = 400    # distancia estimada de contacto con la pelota (mm)
BALL_TOUCH_MAX_SECS = 3.0   # tiempo máximo en modo "toque" antes de resetear

# ── Parámetros de SEARCH ─────────────────────────────────────────────────────
SEARCH_TURN_SPEED = 255     # velocidad de giro buscando pelota (0-255)
SEARCH_TURN_MS    = 250     # duración del giro (ms)
SEARCH_SCAN_SECS  = 0.3     # pausa entre giros (s)

# ── Parámetros de CHASE ──────────────────────────────────────────────────────
CHASE_SPEED_BASE     = 120  # velocidad base de persecución (0-255)
CHASE_ROT_GAIN       = 0.8  # ganancia de rotación proporcional al error de cx
CHASE_DEADBAND_PX    = 16   # zona muerta central antes de aplicar rotación (px)
CHASE_MISS_SECS      = 1.5  # segundos sin ver la pelota antes de ir a SEARCH
CHASE_BLIND_SPEED    = 120  # velocidad cuando persigue sin ver la pelota
CHASE_BLIND_MS       = 150  # duración del avance ciego (ms)
CHASE_BLIND_SCAN_SECS = 0.3 # pausa entre avances ciegos (s)

# ── Parámetros de AVOID ──────────────────────────────────────────────────────
AVOID_REVERSE_SPEED = 110   # velocidad de retroceso al esquivar
AVOID_REVERSE_MS    = 220   # duración del retroceso (ms)
AVOID_TURN_SPEED    = 115   # velocidad de giro al esquivar
AVOID_TURN_MS       = 180   # duración del giro de esquive (ms)
AVOID_FORWARD_SPEED = 105   # velocidad de avance tras esquivar
AVOID_FORWARD_MS    = 170   # duración del avance de reincorporación (ms)
AVOID_MAX_STEPS     = 5     # número máximo de pasos en el plan de evasión
