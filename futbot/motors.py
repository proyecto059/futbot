"""Control de motores via UART serial — protocolo binario propietario.

Clase Motors: envia comandos de velocidad y angulos de servo al driver de
motores conectado por UART (/dev/ttyAMA0 a 1 MBaud).

Protocolo: dos tramas binarias consecutivas por cada burst:
  1. Trama de servos (cmd 0x04) — posicion pan/tilt como PWM 500-2500us
  2. Trama de motores (cmd 0x03) — 4 motores como float32 little-endian

Ambas tramas incluyen CRC8 (polinomio 0x07) como byte final y se escriben
atomicamente bajo threading.Lock.

MotorCommand: dataclass con velocidades diferenciales y angulos de servo.
"""

from __future__ import annotations

import logging
import struct
import threading
from dataclasses import dataclass

from config import Config, crc8

log = logging.getLogger("futbot.motors")


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class MotorCommand:
    """Comando de movimiento para el driver de motores.

    Representa una intencion de movimiento diferencial con duracion
    controlada. Los servos son opcionales: si son None, se mantienen
    en su posicion actual.

    Atributos:
        left_speed: Velocidad de la rueda izquierda (0-255).
            Positivo = avance de la rueda izquierda.
        right_speed: Velocidad de la rueda derecha (0-255).
            Negativo = avance de la rueda derecha.
        dur_ms: Duracion del comando en milisegundos.
        pan_angle: Angulo del servo de paneo en grados (0-180).
            None = mantener posicion actual.
        tilt_angle: Angulo del servo de inclinacion en grados (0-180).
            None = mantener posicion actual.
    """
    left_speed: float = 0.0
    right_speed: float = 0.0
    dur_ms: int = 140
    pan_angle: float | None = None
    tilt_angle: float | None = None


# ── Clase Motors ──────────────────────────────────────────────────────────────

class Motors:
    """Fachada unica para control de motores y servos via UART.

    Abre la conexion serial al driver en /dev/ttyAMA0 a 1 MBaud.
    El import de pyserial es lazy (dentro de __init__) para permitir
    importar MotorCommand sin tener pyserial instalado (util en tests
    y modo stub).

    Thread-safety: el envio de tramas esta protegido por threading.Lock
    para evitar que comandos concurrentes intercalen bytes en el UART.

    Atributos:
        _cfg: Instancia de Config con puerto, baudios, IDs de servo, etc.
        _ser: Objeto serial.Serial conectado al driver.
        _lock: Lock para escritura atomica de tramas.
    """

    def __init__(self, config: Config) -> None:
        """Inicializa la conexion UART con el driver de motores.

        Args:
            config: Instancia de Config con uart_port, uart_baud, IDs de
                servos y centros.

        Raises:
            serial.SerialException: Si el puerto UART no existe o no se
                puede abrir.
        """
        import serial
        self._cfg = config
        self._ser = serial.Serial(config.uart_port, config.uart_baud)
        self._lock = threading.Lock()
        log.info("UART conectado: %s @ %d baud", config.uart_port, config.uart_baud)

    def send(self, cmd: MotorCommand) -> None:
        """Envia un comando de movimiento al driver de motores.

        Flujo interno:
          1. Aplicar cap de velocidad (diff_cap = 250.0)
          2. Convertir velocidades diferenciales a 4 motores
          3. Convertir angulos de servo a PWM (500-2500us)
          4. Construir trama de servos (cmd 0x04) con CRC8
          5. Construir trama de motores (cmd 0x03) con CRC8
          6. Escribir ambas tramas atomicamente al UART

        Args:
            cmd: Comando con velocidades, duracion y angulos de servo.
        """
        v_left, v_right = self._apply_diff_cap(cmd.left_speed, cmd.right_speed)
        m1, m2, m3, m4 = self._differential(v_left, v_right)
        pan = cmd.pan_angle if cmd.pan_angle is not None else self._cfg.pan_center
        tilt = cmd.tilt_angle if cmd.tilt_angle is not None else self._cfg.tilt_center
        self._burst(pan, tilt, cmd.dur_ms, m1, m2, m3, m4)

    def stop(self, dur_ms: int = 300) -> None:
        """Detiene todos los motores y centra los servos.

        Args:
            dur_ms: Duracion del comando de parada en ms (default 300).
        """
        self._burst(self._cfg.pan_center, self._cfg.tilt_center, dur_ms,
                     0.0, 0.0, 0.0, 0.0)

    def close(self) -> None:
        """Cierra la conexion UART con el driver de motores.

        Debe llamarse durante el apagado del robot para liberar el puerto.
        """
        self._ser.close()
        log.info("UART cerrado")

    # ── Conversion diferencial ────────────────────────────────────────────

    def _apply_diff_cap(self, v_left: float, v_right: float) -> tuple[float, float]:
        """Satura las velocidades al maximo configurado (diff_cap).

        Si max(|v_left|, |v_right|) supera diff_cap, ambas velocidades se
        escalan proporcionalmente para mantener la relacion sin exceder
        el limite del driver de motores.

        Args:
            v_left: Velocidad deseada rueda izquierda.
            v_right: Velocidad deseada rueda derecha.

        Returns:
            Tupla (v_left_saturada, v_right_saturada).
        """
        cap = self._cfg.diff_cap
        mx = max(abs(v_left), abs(v_right))
        if mx > cap:
            s = cap / mx
            v_left *= s
            v_right *= s
        return v_left, v_right

    def _differential(self, v_left: float, v_right: float) -> tuple[float, float, float, float]:
        """Convierte velocidades de rueda al cuarteto de motores (m1-m4).

        Convencion de signos:
          - v_left positivo  → la rueda izquierda avanza
          - v_right negativo  → la rueda derecha avanza
          - m1, m2 siempre 0.0 (no son ruedas de traccion)
          - m3 = -v_right     → controla la rueda derecha fisica
          - m4 = -v_left      → controla la rueda izquierda fisica

        Ejemplo — avance recto:
          v_left=80, v_right=-80  →  (0, 0, 80, -80)

        Args:
            v_left: Velocidad rueda izquierda.
            v_right: Velocidad rueda derecha.

        Returns:
            Tupla (m1, m2, m3, m4) como float32.
        """
        return (0.0, 0.0, -v_right, -v_left)

    # ── Protocolo binario (burst) ─────────────────────────────────────────

    def _burst(
        self,
        pan: float, tilt: float, dur_ms: int,
        m1: float, m2: float, m3: float, m4: float,
    ) -> None:
        """Construye y envia las dos tramas binarias (servo + motor) al UART.

        Formato de cada trama:
          Header: 0xAA 0x55
          Cmd:    0x04 (servos) o 0x03 (motores)
          Len:    longitud del payload
          Payload: datos especificos
          CRC8:   checksum sobre bytes[2:] (cmd + len + payload)

        Conversion PWM: pwm = 500 + (angle / 180.0) * 2000
          - 0°   → 500us
          - 90°  → 1500us
          - 180° → 2500us

        Args:
            pan: Angulo del servo de paneo (0-180).
            tilt: Angulo del servo de inclinacion (0-180).
            dur_ms: Duracion del comando en ms.
            m1..m4: Valores float32 para los 4 motores.
        """
        pp = int(500 + (max(0, min(180, pan)) / 180.0) * 2000)
        tp = int(500 + (max(0, min(180, tilt)) / 180.0) * 2000)
        d = int(dur_ms)

        # Trama de servos (cmd 0x04)
        sd = bytearray([
            0x01,
            d & 0xFF,
            (d >> 8) & 0xFF,
            2,
            self._cfg.servo_pan_id,
            pp & 0xFF,
            (pp >> 8) & 0xFF,
            self._cfg.servo_tilt_id,
            tp & 0xFF,
            (tp >> 8) & 0xFF,
        ])
        fs = bytearray(b"\xaa\x55") + bytes([0x04, len(sd)]) + sd
        fs.append(crc8(fs[2:]))

        # Trama de motores (cmd 0x03)
        md = bytearray([0x05, 4])
        for mid, val in ((1, m1), (2, m2), (3, m3), (4, m4)):
            md += struct.pack("<Bf", mid - 1, float(val))
        fm = bytearray(b"\xaa\x55") + bytes([0x03, len(md)]) + md
        fm.append(crc8(fm[2:]))

        with self._lock:
            self._ser.write(fs + fm)
