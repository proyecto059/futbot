"""Constantes de configuración para Pipeline 4 — rutina de disparo a portería.

Valores mantenidos bajos por eficiencia energética (batería).
Todos los PWM están en rango 0-255.
"""

# ── Nombres de estados de la FSM ──
SEARCH = "SEARCH"    # Gira buscando la pelota (turn + pause cíclico)
ADVANCE = "ADVANCE"  # Avanza hacia la pelota con control proporcional
ALIGN = "ALIGN"      # Rota lentamente para alinear pelota + portería al centro
PUSH = "PUSH"        # Avanza recto a máxima velocidad empujando la pelota

# ── Velocidades y duraciones de búsqueda ──
SEARCH_SPEED = 23           # PWM durante el giro de búsqueda (bajo para no derrapar)
SEARCH_TURN_DUR_MS = 500    # Milisegundos de giro por ciclo de búsqueda
SEARCH_PAUSE_DUR_MS = 800   # Milisegundos de pausa entre giros (tiempo para visión)

# ── Control de motores ──
STOP_DUR_MS = 100           # Duración del pulso de parada/freno

# ── Velocidades de avance ──
ADVANCE_SPEED = 150         # PWM base para avance hacia la pelota

# ── Alineación a portería ──
ALIGN_SPEED = 30            # PWM para rotación lenta durante alineación
ALIGN_TURN_DUR_MS = 150     # Duración del pulso de giro en alineación
ALIGN_CENTER_TOLERANCE = 20 # Píxeles de tolerancia para considerar "centrado"

# ── Disparo (push) ──
PUSH_SPEED = 255            # PWM máxima para empujar la pelota a portería
PUSH_DUR_MS = 1500          # Duración total del empuje en milisegundos

# ── Umbrales de pelota ──
BALL_CLOSE_RADIUS = 45      # Radio mínimo (px) para considerar pelota "cerca"
