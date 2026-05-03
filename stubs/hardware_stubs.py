"""stubs/hardware_stubs.py — Stubs de hardware para desarrollo local.

Permite importar módulos que dependen de hardware real (serial, smbus2)
en una laptop/PC sin que fallen los imports.

Uso automático: el conftest.py ya los instala antes de cada test.
Uso manual en scripts de desarrollo:

    from stubs.hardware_stubs import install
    install()

    # Ahora puedes importar módulos que usan serial/smbus2 sin RPi
    from src.motors import MotorService
"""

import sys
import types


def install():
    """Instala stubs de serial y smbus2 en sys.modules."""

    # ── smbus2 stub ──────────────────────────────────────────────────────
    if 'smbus2' not in sys.modules:
        smbus2 = types.ModuleType('smbus2')

        class SMBus:
            def __init__(self, *a, **kw): pass
            def read_byte_data(self, *a, **kw): return 0
            def write_byte_data(self, *a, **kw): pass
            def i2c_rdwr(self, *a, **kw): pass
            def close(self): pass

        class i2c_msg:
            data = [0, 0]
            @staticmethod
            def write(*a, **kw): return i2c_msg()
            @staticmethod
            def read(*a, **kw): return i2c_msg()

        smbus2.SMBus   = SMBus
        smbus2.i2c_msg = i2c_msg
        sys.modules['smbus2'] = smbus2

    # ── serial stub ──────────────────────────────────────────────────────
    if 'serial' not in sys.modules:
        serial = types.ModuleType('serial')

        class Serial:
            def __init__(self, *a, **kw): pass
            def write(self, data): pass
            def read(self, n=1): return b'\x00' * n
            def close(self): pass
            @property
            def in_waiting(self): return 0

        serial.Serial = Serial
        sys.modules['serial'] = serial

    # ── cv2 stub (headless check) ─────────────────────────────────────────
    # cv2 se instala como opencv-python-headless, funciona en laptop sin display.
    # Si falla (p.ej. en CI sin libGL), este stub lo reemplaza.
    try:
        import cv2  # noqa: F401
    except ImportError:
        cv2_stub = types.ModuleType('cv2')
        cv2_stub.VideoCapture = lambda *a, **kw: None
        cv2_stub.CAP_PROP_FRAME_WIDTH  = 3
        cv2_stub.CAP_PROP_FRAME_HEIGHT = 4
        sys.modules['cv2'] = cv2_stub

    print("✅ Hardware stubs instalados (serial, smbus2)")


if __name__ == '__main__':
    install()
    print("Stubs listos para desarrollo local.")
