#!/usr/bin/env python3
import time
from smbus2 import SMBus

bus = SMBus(1)
ADDR = 0x78

print("Pon el sensor SOBRE LINEA BLANCA y espera 3s...")
time.sleep(3)

print("\n=== SOBRE LINEA BLANCA ===")
white = {}
for reg in range(0x21):
    try:
        val = bus.read_byte_data(ADDR, reg)
        white[reg] = val
        print(f"  reg 0x{reg:02X}: {val:3d} (0x{val:02X})")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: ERROR ({e})")

print("\nAhora pon el sensor SOBRE PASTO VERDE y espera 3s...")
time.sleep(3)

print("\n=== SOBRE PASTO VERDE ===")
black = {}
for reg in range(0x21):
    try:
        val = bus.read_byte_data(ADDR, reg)
        black[reg] = val
        print(f"  reg 0x{reg:02X}: {val:3d} (0x{val:02X})")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: ERROR ({e})")

print("\n=== DIFERENCIAS ===")
found = False
for reg in range(0x21):
    w = white.get(reg)
    b = black.get(reg)
    if w is not None and b is not None and w != b:
        print(f"  reg 0x{reg:02X}: blanco={w:3d} oscuro={b:3d} diff={w - b:+d}")
        found = True
if not found:
    print("  Ningun registro cambio entre blanco y oscuro!")

bus.close()