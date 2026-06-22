import sys
sys.path.insert(0, ".")  # permitir import desde raíz

def test_config_defaults():
    from config import Config
    cfg = Config()
    assert cfg.camera_width == 320
    assert cfg.camera_height == 240
    assert cfg.camera_backend == "libcamera"
    assert cfg.yolo_conf_threshold == 0.40
    assert cfg.search_turn_speed == 255
    assert cfg.chase_speed_base == 80
    assert cfg.uart_port == "/dev/ttyAMA0"
    assert cfg.uart_baud == 1000000
    assert cfg.servo_pan_id == 2
    assert cfg.servo_tilt_id == 1
    assert cfg.pan_center == 70
    assert cfg.tilt_center == 45

def test_crc8():
    from config import crc8
    assert crc8(b"\x04\x0b\x01") == crc8(b"\x04\x0b\x01")
    assert isinstance(crc8(b"test"), int)
    assert 0 <= crc8(b"test") <= 255
