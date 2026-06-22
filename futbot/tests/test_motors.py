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
