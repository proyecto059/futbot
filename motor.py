import RPi.GPIO as GPIO
import time

# ================== CONFIGURACIÓN ==================
GPIO.setmode(GPIO.BCM)          # Usamos números BCM (no físicos)
GPIO.setwarnings(False)

# Pines según lo que pediste + IN4
IN1 = 2    # GPIO2  → IN1 (pin físico 3)
IN2 = 3    # GPIO3  → IN2 (pin físico 5)
IN3 = 4    # GPIO4  → IN3 (pin físico 7)
IN4 = 17   # GPIO17 → IN4 (pin físico 11)  ← CONÉCTALO AQUÍ

# Configuramos como salidas
GPIO.setup([IN1, IN2, IN3, IN4], GPIO.OUT)

# Secuencia half-step (más suave y con más torque) - 8 pasos
seq = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1]
]

# Velocidad (más pequeño = más rápido)
delay = 0.002   # 2 milisegundos (ajusta entre 0.001 y 0.005)

print("Motor girando... (Ctrl + C para parar)")

try:
    while True:
        for paso in seq:                    # Gira en una dirección
            GPIO.output(IN1, paso[0])
            GPIO.output(IN2, paso[1])
            GPIO.output(IN3, paso[2])
            GPIO.output(IN4, paso[3])
            time.sleep(delay)
            
except KeyboardInterrupt:
    print("\n¡Parado por el usuario!")
    GPIO.output([IN1, IN2, IN3, IN4], 0)   # Apaga todo