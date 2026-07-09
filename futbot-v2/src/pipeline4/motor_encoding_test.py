"""Test de codificacion de motores — rutina de movimientos programados.

Uso:
    # Simulado (no requiere hardware):
    uv run python -m pipeline4.motor_encoding_test

    # En el robot real (conexion UART a /dev/ttyAMA0):
    uv run python -m pipeline4.motor_encoding_test --real

Propósito:
    Demostrar qué convención de signos necesita un pipeline para mover
    los motores correctamente a través de MotorService / MovementOperator.

    La cadena de codificación es:
        pipeline.tick() → (v_left, v_right, dur_ms)
            → motors.drive(v_left, v_right, dur_ms)
            → MovementOperator.drive(vL, vR, dur)
            → DifferentialOperator.apply(vL, vR) → (0, 0, m3, m4)
            → BurstOperator.send(pan, tilt, dur, 0, 0, m3, m4)
            → UART: 0xAA 0x55 | 0x03 | len | payload (float32 LE) | CRC8

Convención de signos del firmware (confirmada en DifferentialOperator):
    m3 = -v_right  (rueda derecha)
    m4 = -v_left   (rueda izquierda)

    PWM negativo (m < 0) = avance para ambas ruedas

    Por lo tanto, para que un pipeline envíe un comando:
        drive(v_left, v_right)  con  v_left > 0, v_right > 0
        produce  m3 = -vR < 0 (avance derecha)
                 m4 = -vL < 0 (avance izquierda)
        => AVANCE RECTO

    drive(v_left, -v_right)  con  v_left > 0, v_right > 0
        produce  m3 = +vR > 0 (retroceso derecha)
                 m4 = -vL < 0 (avance izquierda)
        => GIRO

    drive(-v_left, v_right)  con  v_left > 0, v_right > 0
        produce  m3 = -vR < 0 (avance derecha)
                 m4 = +vL > 0 (retroceso izquierda)
        => GIRO OPUESTO

    ⚠ IMPORTANTE: Pipeline4Service actualmente hace:
        self._motors.drive(-v_left, v_right, dur_ms)
       Eso INVIERTE v_left, invirtiendo el sentido de giro esperado.
       Esta prueba usa drive(v_left, v_right) SIN negar.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import time

# ── Añadir src/ al PYTHONPATH para poder importar pipeline4 y motors ──
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# ── Forzar UTF-8 en Windows ──────────────────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi.test")


# ── Constantes de prueba ─────────────────────────────────────────────────
SPEED = 120           # Velocidad base para todos los movimientos (PWM 0-255)
DUR_MS = 300          # Duración de cada pulso en milisegundos
PAUSE_MS = 500        # Pausa entre movimientos
REPETITIONS = 4       # Veces que se repite cada tipo de giro


# ═══════════════════════════════════════════════════════════════════════════
# Clase: MotorTestPipeline
# ═══════════════════════════════════════════════════════════════════════════

class MotorTestPipeline:
    """Pipeline de prueba que ejecuta una rutina de movimientos programados.

    Esta clase ejemplifica CÓMO debe codificar un pipeline real los comandos
    de motor usando MotorService.

    Flujo:
        1. tick() llama a métodos privados que retornan (v_left, v_right, dur_ms)
        2. Envía a self._motors.drive(v_left, v_right, dur_ms)  SIN negar

    La rutina incluye:
        - 4 giros a la derecha
        - 4 giros a la izquierda
        - 2 avances rectos
        - 2 retrocesos rectos
    """

    def __init__(self, motors) -> None:
        """Inicializa el pipeline con una instancia de MotorService.

        Args:
            motors: Instancia de MotorService (real o simulada).
        """
        self._motors = motors
        self._step = 0
        self._total_steps = 0

    # ── Métodos de cómputo de comandos ────────────────────────────────────

    @staticmethod
    def _drive_forward(speed: float) -> tuple[float, float, int]:
        """Computa comando para avanzar recto.

        Codificación:
            v_left > 0, v_right > 0
            → DifferentialOperator.apply(vL, vR) → m3 = -vR (negativo = avance)
                                                   m4 = -vL (negativo = avance)
            → Ambos motores giran hacia adelante.

        Returns:
            (v_left, v_right, dur_ms)
        """
        return speed, speed, DUR_MS

    @staticmethod
    def _drive_backward(speed: float) -> tuple[float, float, int]:
        """Computa comando para retroceder recto.

        Codificación:
            v_left < 0, v_right < 0
            → m3 = -vR (positivo = retroceso)
            → m4 = -vL (positivo = retroceso)
            → Ambos motores giran hacia atrás.

        Returns:
            (v_left, v_right, dur_ms)
        """
        return -speed, -speed, DUR_MS

    @staticmethod
    def _turn_right(speed: float) -> tuple[float, float, int]:
        """Computa comando para girar a la derecha (CW).

        Codificación:
            v_left > 0, v_right < 0
            → m3 = -(-vR) = +vR  (positivo = retroceso para rueda derecha)
            → m4 = -vL           (negativo = avance para rueda izquierda)
            → Rueda derecha retrocede, izquierda avanza → giro CW

        Returns:
            (v_left, v_right, dur_ms)
        """
        return speed, -speed, DUR_MS

    @staticmethod
    def _turn_left(speed: float) -> tuple[float, float, int]:
        """Computa comando para girar a la izquierda (CCW).

        Codificación:
            v_left < 0, v_right > 0
            → m3 = -vR           (negativo = avance para rueda derecha)
            → m4 = -(-vL) = +vL  (positivo = retroceso para rueda izquierda)
            → Rueda derecha avanza, izquierda retrocede → giro CCW

        Returns:
            (v_left, v_right, dur_ms)
        """
        return -speed, speed, DUR_MS

    @staticmethod
    def _stop() -> tuple[float, float, int]:
        """Computa comando para detener los motores.

        Returns:
            (v_left, v_right, dur_ms) con ambas velocidades en 0.
        """
        return 0.0, 0.0, PAUSE_MS

    # ── Ejecutor ──────────────────────────────────────────────────────────

    def _execute(self, v_left: float, v_right: float, dur_ms: int) -> None:
        """Envía un comando a los motores.

        Este es el punto clave: la convención usada aquí es:
            drive(v_left, v_right)  SIN negar ningún valor.

        Pipeline4Service actual hace:
            drive(-v_left, v_right)  — NEGANDO v_left

        Returns:
            None
        """
        if v_left == 0 and v_right == 0:
            self._motors.stop(dur_ms)
        else:
            self._motors.drive(v_left, v_right, dur_ms)

        self._total_steps += 1

    # ── Rutina completa ──────────────────────────────────────────────────

    def tick(self) -> None:
        """Ejecuta un paso de la rutina.

        La secuencia completa es:
            Fase 1: Giro derecha  (REPETITIONS veces)
            Fase 2: Giro izquierda (REPETITIONS veces)
            Fase 3: Avance recto   (2 veces)
            Fase 4: Retroceso recto (2 veces)
            Fase 5: Stop final
        """
        max_steps = REPETITIONS * 2 + 2 + 2 + 1  # 13 pasos totales

        if self._step >= max_steps:
            return

        cmd = None
        action = ""

        if self._step < REPETITIONS:
            cmd = self._turn_right(SPEED)
            action = f"Giro DERECHA  ({self._step + 1}/{REPETITIONS})"

        elif self._step < REPETITIONS * 2:
            idx = self._step - REPETITIONS
            cmd = self._turn_left(SPEED)
            action = f"Giro IZQUIERDA ({idx + 1}/{REPETITIONS})"

        elif self._step < REPETITIONS * 2 + 1:
            cmd = self._drive_forward(SPEED)
            action = "Avance RECTO   (1/2)"

        elif self._step < REPETITIONS * 2 + 2:
            cmd = self._drive_forward(SPEED)
            action = "Avance RECTO   (2/2)"

        elif self._step < REPETITIONS * 2 + 3:
            cmd = self._drive_backward(SPEED)
            action = "Retroceso      (1/2)"

        elif self._step < REPETITIONS * 2 + 4:
            cmd = self._drive_backward(SPEED)
            action = "Retroceso      (2/2)"

        else:
            cmd = self._stop()
            action = "STOP final"

        if cmd is None:
            return

        v_left, v_right, dur_ms = cmd

        # Mostrar la codificación completa
        m3 = -v_right
        m4 = -v_left

        log.info("-" * 60)
        log.info("[PIPELINE] %s", action)
        log.info("  pipeline.compute  -> (v_left=%+5.0f, v_right=%+5.0f, dur=%d ms)", v_left, v_right, dur_ms)
        log.info("  motors.drive(%+5.0f, %+5.0f, %d)", v_left, v_right, dur_ms)
        log.info("  diff.apply       -> (m3=%+5.0f, m4=%+5.0f)", m3, m4)
        log.info("  burst.send       -> servo(70, 45) + motor(%.1f, %.1f)", m3, m4)

        self._execute(v_left, v_right, dur_ms)
        self._step += 1

        if self._step >= max_steps:
            log.info("=" * 60)
            log.info("[PIPELINE] Rutina completada (%d pasos).", self._total_steps)
            log.info("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════
# Mock de MotorService (para pruebas sin hardware)
# ═══════════════════════════════════════════════════════════════════════════
# NOTA: No importa serial / BurstOperator / MovementOperator reales para
#       poder ejecutarse en cualquier máquina sin pyserial instalado.

import struct


SERVO_PAN_ID = 0
SERVO_TILT_ID = 1


_CRC8_TABLE = [
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


def _crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c = _CRC8_TABLE[(c ^ b) & 0xFF]
    return c


class MockMotorService:
    """Simula MotorService sin necesidad de hardware real.

    No requiere pyserial — reconstruye los paquetes UART localmente
    para mostrar el resultado exacto que se enviaría al firmware.
    """

    def __init__(self) -> None:
        log.info("[MOCK] MockMotorService iniciado (sin hardware real)")

    @staticmethod
    def _build_burst(m3: float, m4: float, dur_ms: int) -> str:
        """Reconstruye los bytes UART exactos (servo frame + motor frame)."""
        PAN_CENTER = 70.0
        TILT_CENTER = 45.0

        pp = int(500 + (max(0, min(180, PAN_CENTER)) / 180.0) * 2000)
        tp = int(500 + (max(0, min(180, TILT_CENTER)) / 180.0) * 2000)
        d = int(dur_ms)

        sd = bytearray([0x01, d & 0xFF, (d >> 8) & 0xFF, 2,
                        SERVO_PAN_ID, pp & 0xFF, (pp >> 8) & 0xFF,
                        SERVO_TILT_ID, tp & 0xFF, (tp >> 8) & 0xFF])
        fs = bytearray(b"\xAA\x55") + bytes([0x04, len(sd)]) + sd
        fs.append(_crc8(fs[2:]))

        md = bytearray([0x05, 4])
        for mid, val in ((1, 0.0), (2, 0.0), (3, m3), (4, m4)):
            md += struct.pack("<Bf", mid - 1, float(val))
        fm = bytearray(b"\xAA\x55") + bytes([0x03, len(md)]) + md
        fm.append(_crc8(fm[2:]))

        combined = bytes(fs + fm)
        return " ".join(f"{b:02X}" for b in combined)

    def drive(self, v_left: float, v_right: float, dur_ms: int = 140) -> None:
        """Simula el envío de un comando de manejo.

        Internamente replica lo que haría:
            MovementOperator.drive() → DifferentialOperator.apply()
            → BurstOperator.send() → UART write
        """
        m3 = -v_right
        m4 = -v_left
        uart = self._build_burst(m3, m4, dur_ms)
        log.info("  UART write (%d bytes): %s", len(uart) // 3 + 1, uart)

    def stop(self, dur_ms: int = 300) -> None:
        """Simula el envío de un comando de parada."""
        uart = self._build_burst(0.0, 0.0, dur_ms)
        log.info("  UART write (%d bytes): %s", len(uart) // 3 + 1, uart)

    @staticmethod
    def close() -> None:
        log.info("[MOCK] MockMotorService cerrado")


# ═══════════════════════════════════════════════════════════════════════════
# Punto de entrada
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Punto de entrada: selecciona motor service (real o mock) y ejecuta.

    Usage:
        python -m pipeline4.motor_encoding_test        # simulado
        python -m pipeline4.motor_encoding_test --real # hardware real
    """
    use_real = "--real" in sys.argv

    if use_real:
        from motors import MotorService
        motors = MotorService()
        log.info("Modo REAL — conectado a /dev/ttyAMA0")
    else:
        motors = MockMotorService()
        log.info("Modo SIMULADO — mostrando comandos sin enviar")

    pipeline = MotorTestPipeline(motors)

    log.info("=" * 60)
    log.info("RUTINA DE PRUEBA — Codificación de motores")
    log.info("  Velocidad base: %d  (PWM 0-255)", SPEED)
    log.info("  Duración pulso: %d ms", DUR_MS)
    log.info("=" * 60)

    try:
        while pipeline._step < 13:
            pipeline.tick()
            time.sleep(0.05)
    except KeyboardInterrupt:
        log.info("Interrupción recibida.")
    finally:
        motors.stop(200)
        motors.close()
        log.info("Test finalizado.")


if __name__ == "__main__":
    main()
