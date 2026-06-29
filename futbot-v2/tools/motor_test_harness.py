"""Test harness interactivo para experimentar con la cadena de control de motores.

Uso:
    python tools/motor_test_harness.py          -> demo de comandos comunes
    python tools/motor_test_harness.py --demo   -> lo mismo
    python tools/motor_test_harness.py --manual -> modo interactivo: ingresa (vL, vR, dur_ms)
    python tools/motor_test_harness.py --trace 200 100 300 -> traza vL=200, vR=100, dur=300ms

La cadena completa para avanzar recto:
    Pipeline4Service.tick() -> (+-v, +-v, dur) -> motors.drive(-vL, vR) -> MovementOperator
    -> DifferentialOperator.apply(vL, vR) -> (0, 0, -vR, -vL)
    -> BurstOperator.send(pan, tilt, dur, 0, 0, m3, m4)
    -> Frame servo (0x04) + Frame motor (0x03) -> UART /dev/ttyAMA0 @ 1Mbaud

Requiere: pip install pyserial  (solo para estructura, no se necesita HW real)
"""

import io
import struct
import sys
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


SERVO_PAN_ID = 0
SERVO_TILT_ID = 1


CRC8_TABLE = [
    0x00, 0x5E, 0xBC, 0xE2, 0x61, 0x3F, 0xDD, 0x83,
    0xC2, 0x9C, 0x7E, 0x20, 0xA3, 0xFD, 0x1F, 0x41,
    0x9D, 0xC3, 0x21, 0x7F, 0xFC, 0xA2, 0x40, 0x1E,
    0x5F, 0x01, 0xE3, 0xBD, 0x3E, 0x60, 0x82, 0xDC,
    0x23, 0x7D, 0x9F, 0xC1, 0x42, 0x1C, 0xFE, 0xA0,
    0xE1, 0xBF, 0x5D, 0x03, 0x80, 0xDE, 0x3C, 0x62,
    0xBE, 0xE0, 0x02, 0x5C, 0xDF, 0x81, 0x63, 0x3D,
    0x7C, 0x22, 0xC0, 0x9E, 0x1D, 0x43, 0xA1, 0xFF,
    0x46, 0x18, 0xFA, 0xA4, 0x27, 0x79, 0x9B, 0xC5,
    0x84, 0xDA, 0x38, 0x66, 0xE5, 0xBB, 0x59, 0x07,
    0xDB, 0x85, 0x67, 0x39, 0xBA, 0xE4, 0x06, 0x58,
    0x19, 0x47, 0xA5, 0xFB, 0x78, 0x26, 0xC4, 0x9A,
    0x65, 0x3B, 0xD9, 0x87, 0x04, 0x5A, 0xB8, 0xE6,
    0xA7, 0xF9, 0x1B, 0x45, 0xC6, 0x98, 0x7A, 0x24,
    0xF8, 0xA6, 0x44, 0x1A, 0x99, 0xC7, 0x25, 0x7B,
    0x3A, 0x64, 0x86, 0xD8, 0x5B, 0x05, 0xE7, 0xB9,
    0x8C, 0xD2, 0x30, 0x6E, 0xED, 0xB3, 0x51, 0x0F,
    0x4E, 0x10, 0xF2, 0xAC, 0x2F, 0x71, 0x93, 0xCD,
    0x11, 0x4F, 0xAD, 0xF3, 0x70, 0x2E, 0xCC, 0x92,
    0xD3, 0x8D, 0x6F, 0x31, 0xB2, 0xEC, 0x0E, 0x50,
    0xAF, 0xF1, 0x13, 0x4D, 0xCE, 0x90, 0x72, 0x2C,
    0x6D, 0x33, 0xD1, 0x8F, 0x0C, 0x52, 0xB0, 0xEE,
    0x32, 0x6C, 0x8E, 0xD0, 0x53, 0x0D, 0xEF, 0xB1,
    0xF0, 0xAE, 0x4C, 0x12, 0x91, 0xCF, 0x2D, 0x73,
    0xCA, 0x94, 0x76, 0x28, 0xAB, 0xF5, 0x17, 0x49,
    0x08, 0x56, 0xB4, 0xEA, 0x69, 0x37, 0xD5, 0x8B,
    0x57, 0x09, 0xEB, 0xB5, 0x36, 0x68, 0x8A, 0xD4,
    0x95, 0xCB, 0x29, 0x77, 0xF4, 0xAA, 0x48, 0x16,
    0xE9, 0xB7, 0x55, 0x0B, 0x88, 0xD6, 0x34, 0x6A,
    0x2B, 0x75, 0x97, 0xC9, 0x4A, 0x14, 0xF6, 0xA8,
    0x74, 0x2A, 0xC8, 0x96, 0x15, 0x4B, 0xA9, 0xF7,
    0xB6, 0xE8, 0x0A, 0x54, 0xD7, 0x89, 0x6B, 0x35,
]


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = CRC8_TABLE[(c ^ b) & 0xFF]
    return c


def fmt_bytes(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def describe_frame(frame_type: str, frame: bytes) -> str:
    lines = [f"  {frame_type} frame ({len(frame)} bytes):  {fmt_bytes(frame)}"]
    lines.append(f"    +- preamble: {fmt_bytes(frame[0:2])}")
    lines.append(f"    +- cmd: 0x{frame[2]:02X}")
    lines.append(f"    +- len: {frame[3]}")
    lines.append(f"    +- payload: {fmt_bytes(frame[4:-1])}")
    lines.append(f"    +- crc8: 0x{frame[-1]:02X}")
    return "\n".join(lines)


def build_servo_frame(pan: float, tilt: float, dur_ms: int) -> bytes:
    pp = int(500 + (max(0, min(180, pan)) / 180.0) * 2000)
    tp = int(500 + (max(0, min(180, tilt)) / 180.0) * 2000)
    d = int(dur_ms)
    sd = bytearray([
        0x01, d & 0xFF, (d >> 8) & 0xFF, 2,
        SERVO_PAN_ID, pp & 0xFF, (pp >> 8) & 0xFF,
        SERVO_TILT_ID, tp & 0xFF, (tp >> 8) & 0xFF,
    ])
    fs = bytearray(b"\xAA\x55") + bytes([0x04, len(sd)]) + sd
    fs.append(crc8(fs[2:]))
    return bytes(fs)


def build_motor_frame(m1: float, m2: float, m3: float, m4: float) -> bytes:
    md = bytearray([0x05, 4])
    for mid, val in ((1, m1), (2, m2), (3, m3), (4, m4)):
        md += struct.pack("<Bf", mid - 1, float(val))
    fm = bytearray(b"\xAA\x55") + bytes([0x03, len(md)]) + md
    fm.append(crc8(fm[2:]))
    return bytes(fm)


def trace(v_left: float, v_right: float, dur_ms: int = 140) -> None:
    """Muestra la cadena completa desde (vL, vR) hasta los bytes UART."""
    PAN_CENTER = 70.0
    TILT_CENTER = 45.0
    print(f"\n{'='*60}")
    print(f"MOTOR CHAIN TRACE: v_left={v_left:+.0f}, v_right={v_right:+.0f}, dur_ms={dur_ms}")
    print(f"{'='*60}")

    print(f"\n1. Pipeline4Service llamaría a:")
    print(f"   motors.drive({-v_left:.0f}, {v_right:.0f}, {dur_ms})   (invierte v_left por polaridad HW)")

    print(f"\n2. MovementOperator.drive({-v_left:.0f}, {v_right:.0f}, {dur_ms})")
    print(f"   -> DifferentialOperator.apply(vL={-v_left:.0f}, vR={v_right:.0f})")

    cap = 250.0
    vL = float(-v_left)
    vR = float(v_right)
    mx = max(abs(vL), abs(vR))
    if mx > cap:
        s = cap / mx
        vL *= s
        vR *= s
        print(f"   -> CAP applied: max={mx:.0f} > {cap:.0f}, factor={s:.3f}")
        print(f"     scaled: vL={vL:+.0f}, vR={vR:+.0f}")

    m1, m2, m3, m4 = 0.0, 0.0, -vR, -vL
    print(f"   -> (m1={m1}, m2={m2}, m3={m3:+.0f}, m4={m4:+.0f})")
    print(f"     m3 = -vR = {-vR:+.0f}  (rueda derecha)")
    print(f"     m4 = -vL = {-vL:+.0f}  (rueda izquierda)")
    print(f"     NOTA: PWM negativo = avance en este firmware")

    print(f"\n3. BurstOperator.send(pan={PAN_CENTER}, tilt={TILT_CENTER}, dur_ms={dur_ms}")
    print(f"                       m1=0, m2=0, m3={m3:+.0f}, m4={m4:+.0f})")

    servo_frame = build_servo_frame(PAN_CENTER, TILT_CENTER, dur_ms)
    motor_frame = build_motor_frame(m1, m2, m3, m4)

    print(describe_frame("Servo (0x04)", servo_frame))
    print(describe_frame("Motor (0x03)", motor_frame))

    combined = servo_frame + motor_frame
    print(f"\n4. UART write: {len(combined)} bytes")
    print(f"   {fmt_bytes(combined)}")
    print(f"{'='*60}\n")


def demo() -> None:
    """Ejecuta una demo con los comandos típicos de pipeline4."""
    print("\n" + "#" * 60)
    print("#  DEMO: Comandos tipicos de Pipeline4")
    print("#" * 60 + "\n")

    trace(150, 150, 100)             # advance recto
    trace(150 + 60, 150 - 60, 100)   # advance girando a derecha
    trace(150 - 60, 150 + 60, 100)   # advance girando a izquierda
    trace(23, -23, 500)              # search turn (gira en el lugar)
    trace(30, -30, 150)              # align rotation
    trace(0, 0, 100)                 # stop


def manual() -> None:
    """Modo interactivo: ingresa valores y ve la traza."""
    print("\nModo interactivo. Ingresa 'q' para salir.\n")
    while True:
        try:
            inp = input("  vL vR [dur_ms=140]: ").strip()
            if inp.lower() in ("q", "quit", "exit", ""):
                break
            parts = inp.split()
            if len(parts) < 2:
                continue
            vL = float(parts[0])
            vR = float(parts[1])
            dur = int(parts[2]) if len(parts) > 2 else 140
            trace(vL, vR, dur)
        except (ValueError, IndexError):
            continue
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--manual":
            manual()
        elif arg == "--trace" and len(sys.argv) >= 4:
            vL = float(sys.argv[2])
            vR = float(sys.argv[3])
            dur = int(sys.argv[4]) if len(sys.argv) > 4 else 140
            trace(vL, vR, dur)
        else:
            demo()
    else:
        demo()
