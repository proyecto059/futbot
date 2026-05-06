#!/usr/bin/env python3
import time
from smbus2 import SMBus

bus = SMBus(1)
ADDR = 0x78
REG = 0x01

N = 100
INTERVAL = 0.05

print("Leyendo reg 0x01 rapidamente (%d muestras, %.1fs)..." % (N, N * INTERVAL))
print("Mueve el sensor entre pasto y linea blanca AHORA!")
print()

for i in range(N):
    v = bus.read_byte_data(ADDR, REG)
    bits = [(v >> b) & 1 for b in range(4)]
    bar = " ".join("█" if b else "·" for b in bits)
    tag = ""
    if v == 0x0F:
        tag = " ← PASTO (todo True)"
    elif v == 0x00:
        tag = " ← BLANCO/TAPADO (todo False)"
    elif v != 0:
        tag = " ← MIXTO"
    print(f"  [{i:3d}] 0x{v:02X} {bits} {bar}{tag}")
    time.sleep(INTERVAL)

print("\nDone.")
bus.close()
