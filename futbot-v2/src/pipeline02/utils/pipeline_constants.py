"""Constantes de configuración para Pipeline 5.

Valores mantenidos bajos por eficiencia energética (batería).
Todos los PWM están en rango 0-255.
"""

# ── Nombres de estados de la FSM ──
SEARCH = "SEARCH"    # Estado de búsqueda: gira en sitio buscando la pelota
ADVANCE = "ADVANCE"  # Estado de avance: persigue la pelota detectada
SHOOT = "SHOOT"      # ⚠️ Definido pero nunca implementado (no hay lógica ni operador)

# ── Velocidades y duraciones de búsqueda ──
SEARCH_SPEED = 23           # PWM durante el giro de búsqueda (bajo para no derrapar)
SEARCH_TURN_DUR_MS = 500    # Milisegundos de giro por ciclo de búsqueda
SEARCH_PAUSE_DUR_MS = 800   # Milisegundos de pausa entre giros (tiempo para visión)

# ── Control de motores ──
STOP_DUR_MS = 100           # Duración del pulso de parada/freno

# ── Velocidades de avance ──
ADVANCE_SPEED = 150         # PWM base para avance hacia la pelota
SHOOT_SPEED = 255           # PWM máxima para disparo (no usado, reservado para estado SHOOT)
