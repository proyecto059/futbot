import logging
import math
import struct
import time
from threading import Lock

import cv2
import numpy as np
import serial
from smbus2 import SMBus, i2c_msg

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")

# ── Constants ────────────────────────────────────────────────────────────────

SERIAL_PORT = "/dev/ttyAMA0"
SERIAL_BAUD = 1000000
I2C_BUS_NUM = 1
ULTRASONIC_ADDR = 0x77
LINE_FOLLOWER_ADDR = 0x78
LINE_FOLLOWER_REG = 0x01
SERVO_PAN_ID = 2
SERVO_TILT_ID = 1
PAN_CENTER = 90
TILT_CENTER = 90
PAN_MIN = 0
PAN_MAX = 180
PAN_STEP = 5
MEC_A = 67
MEC_B = 59
DEFAULT_SPEED = 250.0
SPIN_360_SEC = 4.0
OBSTACLE_MM = 150
BALL_MIN_AREA = 500
BALL_MIN_RADIUS = 10
BALL_CLOSE_RADIUS = 60
CENTER_THRESH = 50
AIM_STRAFE_SEC = 1.0
SHOT_SEC = 1.5
SHOT_SPEED = 300.0
RETREAT_SEC = 0.5
RETREAT_SPEED = 200.0
CALIB_SAMPLES = 20
HSV_LO = (5, 120, 120)
HSV_HI = (20, 255, 255)

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
                return 9999

    def read_line(self):
        with self._lock:
            try:
                v = self._bus.read_byte_data(LINE_FOLLOWER_ADDR, LINE_FOLLOWER_REG)
                return [bool(v & b) for b in (0x01, 0x02, 0x04, 0x08)]
            except Exception as e:
                log.warning("Line follower error: %s", e)
                return [False, False, False, False]

    def calibrate_line(self):
        log.info("Calibrando line follower (%d muestras)...", CALIB_SAMPLES)
        base = [False] * 4
        for _ in range(CALIB_SAMPLES):
            r = self.read_line()
            for i in range(4):
                base[i] = base[i] or r[i]
            time.sleep(0.05)
        log.info("Line follower baseline: %s", base)
        return base

    def line_changed(self, baseline):
        cur = self.read_line()
        return cur != baseline, cur

    def close(self):
        self._bus.close()
        log.info("I2C cerrado")


# ── Mecanum kinematics ───────────────────────────────────────────────────────
#
# motor1 v1|  ↑  |v2 motor2    layout oficial Hiwonder TurboPi
#          |     |
# motor3 v3|     |v4 motor4
#
# burst_simultaneo usa:  m1=-v1, m2=v2, m3=-v3, m4=v4
# referencia: HiwonderSDK/mecanum.py


def mecanum(vel, deg, omega, cap=DEFAULT_SPEED):
    r = math.radians(deg)
    vx = vel * math.cos(r)
    vy = vel * math.sin(r)
    vp = -omega * (MEC_A + MEC_B)
    m = (-(vy + vx - vp), vy - vx + vp, -(vy - vx - vp), vy + vx + vp)
    mx = max(abs(x) for x in m)
    if mx > cap:
        s = cap / mx
        m = tuple(x * s for x in m)
    return m


# ── Vision ───────────────────────────────────────────────────────────────────


def find_camera():
    for i in range(6):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ok, f = cap.read()
            if ok and f is not None:
                h, w = f.shape[:2]
                log.info("Camara detectada: /dev/video%d (%dx%d)", i, w, h)
                return cap, w
            cap.release()
    return None, 0


def detect_ball(frame):
    hsv = cv2.cvtColor(cv2.GaussianBlur(frame, (11, 11), 0), cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(HSV_LO), np.array(HSV_HI))
    k = np.ones((5, 5), np.uint8)
    mask = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), k)
    best = None
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        if cv2.contourArea(c) > BALL_MIN_AREA:
            (x, y), rad = cv2.minEnclosingCircle(c)
            if rad > BALL_MIN_RADIUS and (best is None or rad > best[2]):
                best = (int(x), int(y), rad)
    return best
