"""Constantes del sensor ultrasónico.

Fuente única de verdad para dirección I2C (0x77), registro LED (0x02),
y umbral de detección de obstáculos.
"""

# Bus I2C de la Raspberry Pi (1 = /dev/i2c-1).
I2C_BUS_NUM = 1

# Dirección I2C del sensor ultrasónico.
ULTRASONIC_ADDR = 0x77

# Registro donde se escriben los bytes de control del LED RGB.
ULTRASONIC_LED_REG = 0x02

# Distancia (mm) a partir de la cual se considera obstáculo cercano.
DIST_TRIGGER_MM = 250

# Color inicial del LED al arrancar el servicio (verde tenue).
LED_INIT_R = 0x00
LED_INIT_G = 0x10
LED_INIT_B = 0x00