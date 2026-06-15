"""Hardware + shims de visión del robot Turbopi.

Después de la migración a `vision/`, este módulo conserva:
    - Control de hardware: `SerialBus` (UART→servos/motores), `SharedI2CBus`
      (ultrasónico + line follower), helpers de differential/servo mapping.
    - Constantes de hardware (puertos, IDs de servo, thresholds de ultrasónico).
    - Re-export de constantes de visión desde `vision.utils.vision_constants`
      para que scripts legados (`test-robot/diag_*.py`) no se rompan.
    - Shims de compatibilidad (`find_camera`, `create_detector`, `detect_ball`,
      `detect_white_line`, `get_ball_detection_debug`) que delegan a un
      singleton de `HybridVisionService`.

Para código nuevo, usar directamente `from vision import HybridVisionService`.
"""

import logging
import struct
import time
from threading import Lock

import serial
from smbus2 import SMBus, i2c_msg

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")

# ── Constantes de hardware ───────────────────────────────────────────────────

SERIAL_PORT = "/dev/ttyAMA0"
SERIAL_BAUD = 1000000
I2C_BUS_NUM = 1
ULTRASONIC_ADDR = 0x77
ULTRASONIC_LED_REG = 0x02
LINE_FOLLOWER_ADDR = 0x78
LINE_FOLLOWER_REG = 0x01
SERVO_PAN_ID = 2
SERVO_TILT_ID = 1
SERVO_MIN_ANGLE = 0
SERVO_MAX_ANGLE = 180
SERVO_PAN_INVERTED = True
SERVO_TILT_INVERTED = True
PAN_CENTER = 70
TILT_CENTER = 45
PAN_MIN = SERVO_MIN_ANGLE
PAN_MAX = SERVO_MAX_ANGLE
PAN_STEP = 5
DEFAULT_SPEED = 250.0
SPIN_360_SEC = 4.0
OBSTACLE_MM = 150
CENTER_THRESH = 50
AIM_STRAFE_SEC = 1.0
SHOT_SEC = 1.5
SHOT_SPEED = 300.0
RETREAT_SEC = 0.5
RETREAT_SPEED = 200.0
CALIB_SAMPLES = 20
LINE_MIN_CHANGED = 2

# ── Re-export de constantes de visión (fuente única en vision/utils) ─────────
# Mantener estas re-exportaciones permite que scripts legados que hacen
# `from cam import HSV_LO, BALL_MIN_RADIUS, ...` sigan funcionando sin tocar.
from vision.utils.vision_constants import (  # noqa: E402,F401
    ADAPTIVE_HUE_EMA_ALPHA,
    ADAPTIVE_MAX_RADIUS,
    ADAPTIVE_MIN_CIRCULARITY,
    ADAPTIVE_MISS_RESET_FRAMES,
    ADAPTIVE_ORANGE_HUE_MAX,
    ADAPTIVE_ORANGE_HUE_MIN,
    ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES,
    ADAPTIVE_RELAXED_RECENT_SEC,
    ADAPTIVE_STRICT_BASE_MARGIN,
    BALL_CLOSE_RADIUS,
    BALL_MIN_AREA,
    BALL_MIN_RADIUS,
    BORDER_MARGIN,
    CAMERA_BRIGHTNESS,
    CAMERA_EXPOSURE_DEFAULT,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    EXPOSURE_ADJUST_EVERY,
    EXPOSURE_MAX,
    EXPOSURE_MIN,
    HOT_PIXEL_Y_MAX,
    HSV_GOAL_BLUE_HI,
    HSV_GOAL_BLUE_LO,
    HSV_GOAL_YELLOW_HI,
    HSV_GOAL_YELLOW_LO,
    HSV_HI,
    HSV_HI2,
    HSV_LO,
    HSV_LO2,
    HSV_WHITE_HI,
    HSV_WHITE_LO,
    LINE_DETECT_MIN_PIXELS,
    YOLO_BALL_CLASS_ID,
    YOLO_CONF_THRESHOLD,
    YOLO_IMGSZ,
    YOLO_ROBOT_CLASS_ID,
    YOLO_THREAD_SLEEP_SEC,
)

# Alias retrocompat
CAMERA_EXPOSURE = CAMERA_EXPOSURE_DEFAULT

# ── CRC8 ─────────────────────────────────────────────────────────────────────

CRC8_TABLE = [
    0,
    94,
    188,
    226,
    97,
    63,
    221,
    131,
    194,
    156,
    126,
    32,
    163,
    253,
    31,
    65,
    157,
    195,
    33,
    127,
    252,
    162,
    64,
    30,
    95,
    1,
    227,
    189,
    62,
    96,
    130,
    220,
    35,
    125,
    159,
    193,
    66,
    28,
    254,
    160,
    225,
    191,
    93,
    3,
    128,
    222,
    60,
    98,
    190,
    224,
    2,
    92,
    223,
    129,
    99,
    61,
    124,
    34,
    192,
    158,
    29,
    67,
    161,
    255,
    70,
    24,
    250,
    164,
    39,
    121,
    155,
    197,
    132,
    218,
    56,
    102,
    229,
    187,
    89,
    7,
    219,
    133,
    103,
    57,
    186,
    228,
    6,
    88,
    25,
    71,
    165,
    251,
    120,
    38,
    196,
    154,
    101,
    59,
    217,
    135,
    4,
    90,
    184,
    230,
    167,
    249,
    27,
    69,
    198,
    152,
    122,
    36,
    248,
    166,
    68,
    26,
    153,
    199,
    37,
    123,
    58,
    100,
    134,
    216,
    91,
    5,
    231,
    185,
    140,
    210,
    48,
    110,
    237,
    179,
    81,
    15,
    78,
    16,
    242,
    172,
    47,
    113,
    147,
    205,
    17,
    79,
    173,
    243,
    112,
    46,
    204,
    146,
    211,
    141,
    111,
    49,
    178,
    236,
    14,
    80,
    175,
    241,
    19,
    77,
    206,
    144,
    114,
    44,
    109,
    51,
    209,
    143,
    12,
    82,
    176,
    238,
    50,
    108,
    142,
    208,
    83,
    13,
    239,
    177,
    240,
    174,
    76,
    18,
    145,
    207,
    45,
    115,
    202,
    148,
    118,
    40,
    171,
    245,
    23,
    73,
    8,
    86,
    180,
    234,
    105,
    55,
    213,
    139,
    87,
    9,
    235,
    181,
    54,
    104,
    138,
    212,
    149,
    203,
    41,
    119,
    244,
    170,
    72,
    22,
    233,
    183,
    85,
    11,
    136,
    214,
    52,
    106,
    43,
    117,
    151,
    201,
    74,
    20,
    246,
    168,
    116,
    42,
    200,
    150,
    21,
    75,
    169,
    247,
    182,
    232,
    10,
    84,
    215,
    137,
    107,
    53,
]


def crc8(data):
    c = 0
    for b in data:
        c = CRC8_TABLE[c ^ b]
    return c


# ── SerialBus (UART) – Servos + Motores ──────────────────────────────────────


class SerialBus:
    def __init__(self, port=SERIAL_PORT, baud=SERIAL_BAUD):
        self.ser = serial.Serial(port, baud)
        log.info("UART conectado: %s @ %d baud", port, baud)

    def burst(self, pan, tilt, dur_ms, m1, m2, m3, m4):
        pp = int(500 + (max(0, min(180, pan)) / 180.0) * 2000)
        tp = int(500 + (max(0, min(180, tilt)) / 180.0) * 2000)
        d = int(dur_ms)

        sd = bytearray(
            [
                0x01,
                d & 0xFF,
                (d >> 8) & 0xFF,
                2,
                SERVO_PAN_ID,
                pp & 0xFF,
                (pp >> 8) & 0xFF,
                SERVO_TILT_ID,
                tp & 0xFF,
                (tp >> 8) & 0xFF,
            ]
        )
        fs = bytearray(b"\xaa\x55") + bytes([0x04, len(sd)]) + sd
        fs.append(crc8(fs[2:]))

        md = bytearray([0x05, 4])
        for mid, val in ((1, m1), (2, m2), (3, m3), (4, m4)):
            md += struct.pack("<Bf", mid - 1, float(val))
        fm = bytearray(b"\xaa\x55") + bytes([0x03, len(md)]) + md
        fm.append(crc8(fm[2:]))

        self.ser.write(fs + fm)

    def stop(self, pan=PAN_CENTER, tilt=TILT_CENTER):
        self.burst(pan, tilt, 300, 0, 0, 0, 0)

    def close(self):
        self.ser.close()
        log.info("UART cerrado")


# ── SharedI2CBus – Ultrasonico (0x77) + Line Follower (0x78) ─────────────────


class SharedI2CBus:
    def __init__(self, bus_num=I2C_BUS_NUM):
        self._bus = SMBus(bus_num)
        self._lock = Lock()
        log.info(
            "I2C bus %d listo (ultrasonico=0x%02X, line_follower=0x%02X)",
            bus_num,
            ULTRASONIC_ADDR,
            LINE_FOLLOWER_ADDR,
        )
        self.set_ultrasonic_led(0x00, 0x10, 0x00)

    def set_ultrasonic_led(self, r, g, b, blink=False):
        mode = 0x01 if blink else 0x00
        data = [mode, r, g, b, r, g, b]
        with self._lock:
            try:
                self._bus.write_i2c_block_data(
                    ULTRASONIC_ADDR, ULTRASONIC_LED_REG, data
                )
            except Exception as e:
                log.warning("Ultrasonic LED error: %s", e)

    def read_ultrasonic(self):
        with self._lock:
            try:
                w = i2c_msg.write(ULTRASONIC_ADDR, [0])
                self._bus.i2c_rdwr(w)
                r = i2c_msg.read(ULTRASONIC_ADDR, 2)
                self._bus.i2c_rdwr(r)
                return min(int.from_bytes(bytes(list(r)), "little"), 5000)
            except Exception as e:
                log.warning("Ultrasonico error: %s", e)
                return None

    def read_line(self):
        with self._lock:
            try:
                v = self._bus.read_byte_data(LINE_FOLLOWER_ADDR, LINE_FOLLOWER_REG)
                return [bool(v & b) for b in (0x01, 0x02, 0x04, 0x08)]
            except Exception as e:
                log.warning("Line follower error: %s", e)
                return [False, False, False, False]

    def calibrate_line(self):
        log.info("Calibrando line follower digital (%d muestras)...", CALIB_SAMPLES)
        counts = [0] * 4
        n = 0
        for _ in range(CALIB_SAMPLES):
            r = self.read_line()
            for i in range(4):
                if r[i]:
                    counts[i] += 1
            n += 1
            time.sleep(0.05)
        baseline = [counts[i] > n // 2 for i in range(4)]
        log.info(
            "Line follower calibrado: baseline=%s (True=pasto dominante)",
            baseline,
        )
        return baseline

    def line_changed(self, baseline):
        cur = self.read_line()
        changed = [cur[i] != baseline[i] for i in range(4)]
        count = sum(changed)
        if count >= LINE_MIN_CHANGED:
            return True, cur
        return False, cur

    def close(self):
        self._bus.close()
        log.info("I2C cerrado")


# ── Motor / servo helpers ────────────────────────────────────────────────────


def differential(v_left, v_right, cap=DEFAULT_SPEED):
    mx = max(abs(v_left), abs(v_right))
    if mx > cap:
        s = cap / mx
        v_left *= s
        v_right *= s
    return (v_left, -v_right, v_left, -v_right)


def _clamp_int(value, lo, hi):
    """Clamp and truncate to int (toward zero)."""
    return max(lo, min(hi, int(value)))


def map_x_to_pan(cx, frame_width, pan_inverted=SERVO_PAN_INVERTED):
    if frame_width <= 0:
        return PAN_CENTER
    pan = (float(cx) / float(frame_width)) * float(SERVO_MAX_ANGLE)
    if pan_inverted:
        pan = float(SERVO_MAX_ANGLE) - pan
    return _clamp_int(pan, PAN_MIN, PAN_MAX)


def map_y_to_tilt(cy, frame_height, tilt_inverted=SERVO_TILT_INVERTED):
    if frame_height <= 0:
        return TILT_CENTER
    tilt = float(SERVO_MAX_ANGLE) - (float(cy) / float(frame_height)) * float(
        SERVO_MAX_ANGLE
    )
    if tilt_inverted:
        tilt = float(SERVO_MAX_ANGLE) - tilt
    return _clamp_int(tilt, SERVO_MIN_ANGLE, SERVO_MAX_ANGLE)


def map_ball_to_servos(
    cx,
    cy,
    frame_width,
    frame_height,
    pan_inverted=SERVO_PAN_INVERTED,
    tilt_inverted=SERVO_TILT_INVERTED,
):
    pan = map_x_to_pan(cx, frame_width, pan_inverted=pan_inverted)
    tilt = map_y_to_tilt(cy, frame_height, tilt_inverted=tilt_inverted)
    return pan, tilt


# ── Shims de visión (delegan en HybridVisionService) ─────────────────────────
# Código nuevo: usar `from vision import HybridVisionService` directamente.
# Código viejo (diag_*.py, etc.) puede seguir llamando estas funciones sueltas.

_VISION_SINGLETON = None


def _vision():
    """Singleton lazy de HybridVisionService para los shims de compatibilidad."""
    global _VISION_SINGLETON
    if _VISION_SINGLETON is None:
        from vision import HybridVisionService

        _VISION_SINGLETON = HybridVisionService()
    return _VISION_SINGLETON


class _LegacyDetectorShim:
    """Reemplaza al antiguo `HybridBallDetector`.

    Expone la misma API que usaban `main.py` y los scripts de diagnóstico:
    `detect`, `get_latest_output`, `get_ball_source`, `set_exposure_cap`,
    `get_debug_snapshot`, `close`.
    """

    def __init__(self, service):
        self._service = service
        self._last_source = "none"

    def detect(self, frame, now_ts=None):  # noqa: ARG002 — frame se ignora
        """Devuelve (cx, cy, r) como la API vieja. Usa el tick más reciente."""
        snap = self._service.tick()
        ball = snap.get("ball")
        if ball is None:
            self._last_source = "none"
            return None
        self._last_source = ball.get("source", "none")
        return ball["cx"], ball["cy"], ball["r"]

    def get_latest_output(self):
        """Dict con robots/goals como el antiguo YOLOThreadedHybridDetector."""
        snap = self._service.tick(None)
        goals = snap.get("goals", {})
        return {
            "ball": snap.get("ball"),
            "robots": snap.get("robots", []),
            "goals": {
                "goal_yellow": bool(goals.get("yellow", False)),
                "goal_yellow_cx": goals.get("yellow_cx"),
                "goal_blue": bool(goals.get("blue", False)),
                "goal_blue_cx": goals.get("blue_cx"),
            },
            "ts": snap.get("ts", 0.0),
        }

    def get_ball_source(self):
        return self._last_source

    def set_exposure_cap(self, cap):  # noqa: ARG002 — el servicio maneja la cap interna
        pass

    def get_debug_snapshot(self):
        snap = self._service.tick()
        return snap.get("debug", {})

    def close(self):
        self._service.close()


def create_detector():
    """Shim: devuelve un detector con la API histórica del `HybridBallDetector`."""
    return _LegacyDetectorShim(_vision())


def detect_ball(frame):  # noqa: ARG001 — preservamos firma antigua
    """Shim: `detect_ball(frame)` → (cx, cy, r) o None."""
    return create_detector().detect(frame)


def get_ball_detection_debug():
    """Shim: snapshot de debug del detector."""
    return create_detector().get_debug_snapshot()


def detect_white_line(frame):  # noqa: ARG001 — el servicio usa su propio frame
    """Shim: (detected, cx, pixels) usando la detección interna del servicio."""
    snap = _vision().tick()
    line = snap.get("line", {})
    return (
        bool(line.get("detected", False)),
        line.get("cx"),
        int(line.get("pixels", 0)),
    )


def find_camera(threaded=False, downscale=False):  # noqa: ARG001
    """Shim obsoleto: el servicio ya resuelve la cámara internamente.

    Devuelve un objeto con la API mínima (`read`, `get`, `release`) para que
    scripts legados que iteran con `cap.read()` sigan funcionando. El frame
    devuelto es el último que capturó el hilo OpenCV del servicio.
    """
    import cv2

    service = _vision()

    class _LegacyCapShim:
        def read(self):
            frame_dto = service._capture.read_latest()
            if frame_dto is None:
                return False, None
            return True, frame_dto.image

        def get(self, prop):
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return service.frame_width
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return CAMERA_HEIGHT
            return 0

        def set(self, prop, value):  # noqa: ARG002
            return False

        def release(self):
            service.close()

        def isOpened(self):
            return True

    return _LegacyCapShim(), service.frame_width, CAMERA_EXPOSURE_DEFAULT
