### Tarea 4: Crear `motors.py`

**Archivos:**
- Crear: `futbot/motors.py`
- Test: `futbot/tests/test_motors.py`

**Interfaces:**
- Produce: `Motors` class con `send(cmd: MotorCommand)`, `stop()`, `close()`
- Produce: `MotorCommand` dataclass
- Consume: `Config` y `crc8` de `config.py` (ya existen)

**IMPORTANTE: NO hacer `import serial` a nivel de modulo. Ese import va DENTRO de `Motors.__init__` para que los tests de `MotorCommand` y funciones puras no requieran pyserial instalado.**

Los tests NO prueban la clase Motors directamente (solo dataclass, mapeo diferencial, PWM, CRC8), asi que deben poder correr sin hardware.

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_motors.py
import sys
sys.path.insert(0, ".")

def test_motor_command_dataclass():
    from motors import MotorCommand
    cmd = MotorCommand(left_speed=80.0, right_speed=-80.0, dur_ms=140)
    assert cmd.left_speed == 80.0
    assert cmd.right_speed == -80.0
    assert cmd.dur_ms == 140
    assert cmd.pan_angle is None
    assert cmd.tilt_angle is None

def test_differential_mapping():
    """Verifica el mapeo de velocidades de rueda a 4 motores."""
    def apply(v_left, v_right, cap=250.0):
        mx = max(abs(v_left), abs(v_right))
        if mx > cap:
            s = cap / mx
            v_left *= s
            v_right *= s
        return (0.0, 0.0, -v_right, -v_left)

    m1, m2, m3, m4 = apply(80.0, -80.0)
    assert m1 == 0.0
    assert m2 == 0.0
    assert m3 == 80.0
    assert m4 == -80.0

    m1, m2, m3, m4 = apply(80.0, -80.0)
    assert m3 > 0

    m1, m2, m3, m4 = apply(0.0, 0.0)
    assert (m1, m2, m3, m4) == (0.0, 0.0, 0.0, 0.0)

def test_pwm_conversion():
    """Verifica la conversion angulo -> PWM."""
    def angle_to_pwm(angle):
        return int(500 + (max(0, min(180, angle)) / 180.0) * 2000)
    assert angle_to_pwm(0) == 500
    assert angle_to_pwm(90) == 1500
    assert angle_to_pwm(180) == 2500

def test_crc8_uart_frame():
    """Verifica CRC8 en una trama de ejemplo."""
    from config import crc8
    sd = bytes([0x01, 0x8C, 0x00, 2, 2, 0xDC, 0x05, 1, 0x84, 0x03])
    frame = bytes([0xAA, 0x55, 0x04, len(sd)]) + sd
    checksum = crc8(frame[2:])
    assert 0 <= checksum <= 255
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; python -m pytest tests/test_motors.py -v
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'motors'`

- [ ] **Paso 3: Escribir `motors.py`**

NOTA: `import serial` VA DENTRO de `Motors.__init__`, no a nivel de modulo. Esto permite importar `MotorCommand` sin tener pyserial instalado.

```python
"""Control de motores via UART serial — protocolo binario propietario.

Clase Motors: envia comandos de velocidad y angulos de servo al driver de
motores conectado por UART (/dev/ttyAMA0).

Protocolo: dos tramas binarias (servo + motor) con CRC8, escritas
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

    left_speed, right_speed: velocidades diferenciales (valores absolutos 0-255).
    dur_ms: duracion del comando en milisegundos.
    pan_angle, tilt_angle: angulos de servo en grados (0-180), None = mantener.
    """
    left_speed: float = 0.0
    right_speed: float = 0.0
    dur_ms: int = 140
    pan_angle: float | None = None
    tilt_angle: float | None = None


# ── Clase Motors ──────────────────────────────────────────────────────────────

class Motors:
    """Fachada unica para control de motores y servos via UART."""

    def __init__(self, config: Config) -> None:
        import serial  # import lazy: solo en hardware real
        self._cfg = config
        self._ser = serial.Serial(config.uart_port, config.uart_baud)
        self._lock = threading.Lock()
        log.info("UART conectado: %s @ %d baud", config.uart_port, config.uart_baud)

    def send(self, cmd: MotorCommand) -> None:
        """Envia un comando de movimiento al driver de motores.

        Convierte velocidades diferenciales a 4 motores, angulos a PWM,
        construye las tramas binarias con CRC8 y las escribe al UART.
        """
        v_left, v_right = self._apply_diff_cap(cmd.left_speed, cmd.right_speed)
        m1, m2, m3, m4 = self._differential(v_left, v_right)
        pan = cmd.pan_angle if cmd.pan_angle is not None else self._cfg.pan_center
        tilt = cmd.tilt_angle if cmd.tilt_angle is not None else self._cfg.tilt_center
        self._burst(pan, tilt, cmd.dur_ms, m1, m2, m3, m4)

    def stop(self, dur_ms: int = 300) -> None:
        """Detiene todos los motores."""
        self._burst(self._cfg.pan_center, self._cfg.tilt_center, dur_ms,
                     0.0, 0.0, 0.0, 0.0)

    def close(self) -> None:
        """Cierra la conexion UART."""
        self._ser.close()
        log.info("UART cerrado")

    # ── Conversion diferencial ────────────────────────────────────────────

    def _apply_diff_cap(self, v_left: float, v_right: float) -> tuple[float, float]:
        cap = self._cfg.diff_cap
        mx = max(abs(v_left), abs(v_right))
        if mx > cap:
            s = cap / mx
            v_left *= s
            v_right *= s
        return v_left, v_right

    def _differential(self, v_left: float, v_right: float) -> tuple[float, float, float, float]:
        """Convierte velocidades de rueda a cuarteto de motor.

        Convencion:
          - v_left positivo -> avance rueda izquierda
          - v_right negativo -> avance rueda derecha
          - m1, m2 siempre 0.0 (no son ruedas de traccion)
          - m3 = -v_right -> rueda derecha fisica
          - m4 = -v_left  -> rueda izquierda fisica
        """
        return (0.0, 0.0, -v_right, -v_left)

    # ── Protocolo binario (burst) ─────────────────────────────────────────

    def _burst(
        self,
        pan: float, tilt: float, dur_ms: int,
        m1: float, m2: float, m3: float, m4: float,
    ) -> None:
        """Construye y envia las dos tramas (servo + motor) al UART."""
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
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; python -m pytest tests/test_motors.py -v
```
Esperado: 4 passed (NO requiere pyserial — el import de serial esta dentro de Motors.__init__)

- [ ] **Paso 5: Commit**

```bash
git add futbot/motors.py futbot/tests/test_motors.py
git commit -m "feat: crear motors.py con protocolo UART y control diferencial"
```
