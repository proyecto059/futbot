import logging
import struct
import time
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
import onnxruntime as ort
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
BALL_MIN_AREA = 700
BALL_MIN_RADIUS = 15
BALL_CLOSE_RADIUS = 60
CENTER_THRESH = 50
AIM_STRAFE_SEC = 1.0
SHOT_SEC = 1.5
SHOT_SPEED = 300.0
RETREAT_SEC = 0.5
RETREAT_SPEED = 200.0
CALIB_SAMPLES = 20
LINE_MIN_CHANGED = 2
HSV_LO = (0, 230, 20)
HSV_HI = (10, 255, 255)
HSV_LO2 = (168, 230, 20)
HSV_HI2 = (179, 255, 255)
ADAPTIVE_ORANGE_HUE_MIN = 0
ADAPTIVE_ORANGE_HUE_MAX = 15
ADAPTIVE_MIN_CIRCULARITY = 0.20
ADAPTIVE_MAX_RADIUS = 150
ADAPTIVE_STRICT_BASE_MARGIN = 8
ADAPTIVE_HUE_EMA_ALPHA = 0.15
ADAPTIVE_RELAXED_RECENT_SEC = 1.2
ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES = 2
ADAPTIVE_MISS_RESET_FRAMES = 30
HOT_PIXEL_Y_MAX = 82
BORDER_MARGIN = 25
EXPOSURE_MIN = 150
EXPOSURE_MAX = 450
EXPOSURE_ADJUST_EVERY = 10

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


# ── Vision ───────────────────────────────────────────────────────────────────


class AdaptiveOrangeBallDetector:
    _GAMMA_LUT_CACHE = {}

    def __init__(self):
        self.hue_center = float((HSV_LO[0] + HSV_HI[0]) / 2.0)
        self.last_seen_ts = 0.0
        self.miss_streak = 0
        self.last_mode = "strict"
        self._current_gamma = 1.0
        self._cap = None
        self._current_exp = 200
        self._exp_frame_count = 0
        self._debug_snapshot = {
            "mode": "strict",
            "v_median": 0,
            "v_median_raw": 0,
            "sat_min": int(HSV_LO[1]),
            "val_min": int(HSV_LO[2]),
            "hue_center": float(self.hue_center),
            "hue_half_width": int(max(6, (HSV_HI[0] - HSV_LO[0]) // 2)),
            "gamma": 1.0,
            "exposure": 200,
        }

    @staticmethod
    def _circularity(contour):
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if area <= 0.0 or perimeter <= 0.0:
            return 0.0
        return float(4.0 * np.pi * area) / float(perimeter * perimeter)

    @staticmethod
    def _clamp_hue(value):
        return int(max(0, min(179, value)))

    def _build_hue_mask(
        self,
        hsv,
        hue_center,
        hue_half_width,
        sat_min=None,
        val_min=None,
    ):
        if sat_min is None:
            sat_min = int(self._debug_snapshot["sat_min"])
        if val_min is None:
            val_min = int(self._debug_snapshot["val_min"])

        lo_h = self._clamp_hue(hue_center - hue_half_width)
        hi_h = self._clamp_hue(hue_center + hue_half_width)

        if lo_h <= hi_h:
            mask = cv2.inRange(
                hsv,
                np.array((lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((hi_h, 255, 255), dtype=np.uint8),
            )
        else:
            mask_a = cv2.inRange(
                hsv,
                np.array((0, sat_min, val_min), dtype=np.uint8),
                np.array((hi_h, 255, 255), dtype=np.uint8),
            )
            mask_b = cv2.inRange(
                hsv,
                np.array((lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((179, 255, 255), dtype=np.uint8),
            )
            mask = cv2.bitwise_or(mask_a, mask_b)

        mask2 = cv2.inRange(
            hsv,
            np.array((HSV_LO2[0], sat_min, val_min), dtype=np.uint8),
            np.array((HSV_HI2[0], 255, 255), dtype=np.uint8),
        )
        mask = cv2.bitwise_or(mask, mask2)
        return mask

    @staticmethod
    def _extract_hue_patch(hsv, cx, cy, radius):
        r = int(max(3, min(12, radius * 0.4)))
        x0 = max(0, int(cx) - r)
        y0 = max(0, int(cy) - r)
        x1 = min(hsv.shape[1], int(cx) + r + 1)
        y1 = min(hsv.shape[0], int(cy) + r + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        return hsv[y0:y1, x0:x1, 0]

    def set_exposure_cap(self, cap):
        self._cap = cap
        self._current_exp = 200
        self._exp_frame_count = 0

    @classmethod
    def _get_gamma_lut(cls, gamma):
        gamma_key = round(gamma, 2)
        if gamma_key not in cls._GAMMA_LUT_CACHE:
            inv_gamma = 1.0 / gamma
            table = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
                dtype=np.uint8,
            )
            cls._GAMMA_LUT_CACHE[gamma_key] = table
        return cls._GAMMA_LUT_CACHE[gamma_key]

    def _apply_gamma(self, frame, v_median_raw):
        target_v = 120
        if v_median_raw <= 0:
            gamma = 2.0
        elif v_median_raw >= target_v:
            gamma = 1.0
        else:
            gamma = max(1.0, min(2.0, float(target_v) / float(v_median_raw)))
        gamma = round(gamma * 4) / 4
        self._current_gamma = gamma
        lut = self._get_gamma_lut(gamma)
        return cv2.LUT(frame, lut)

    def _adjust_exposure(self, frame_w=640, frame_h=480):
        if self._cap is None:
            return
        self._exp_frame_count += 1
        if self._exp_frame_count < EXPOSURE_ADJUST_EVERY:
            return
        self._exp_frame_count = 0

        old_exp = self._current_exp
        if self.miss_streak >= 10:
            self._current_exp = min(EXPOSURE_MAX, self._current_exp + 40)
        self._current_exp = max(EXPOSURE_MIN, min(EXPOSURE_MAX, self._current_exp))

        if self._current_exp != old_exp:
            self._cap.set(cv2.CAP_PROP_EXPOSURE, int(self._current_exp))
            log.info(
                "Exposure: %d->%d (miss=%d)",
                old_exp,
                self._current_exp,
                self.miss_streak,
            )
        self._debug_snapshot["exposure"] = int(self._current_exp)

    def _update_adaptive_thresholds(self, hsv, relaxed, v_median_raw=0):
        v_channel = hsv[::4, ::4, 2]
        v_median = int(np.median(v_channel))

        if relaxed:
            sat_min = 200
            val_min = 10
        else:
            sat_min = 220
            val_min = 15

        self._debug_snapshot.update(
            {
                "mode": "relaxed" if relaxed else "strict",
                "v_median": v_median,
                "v_median_raw": v_median_raw,
                "sat_min": sat_min,
                "val_min": val_min,
                "hue_center": float(self.hue_center),
                "gamma": float(self._current_gamma),
            }
        )

    def _candidate_mask(
        self,
        hsv,
        relaxed,
        hue_half_width=None,
        sat_min_override=None,
        val_min_override=None,
    ):
        self._update_adaptive_thresholds(hsv, relaxed)
        if hue_half_width is not None:
            pass
        elif relaxed:
            hue_half_width = 10
        else:
            vm = self._debug_snapshot.get("v_median", 120)
            if vm < 50 or vm > 200:
                hue_half_width = 12
            elif vm < 80 or vm > 180:
                hue_half_width = 9
            else:
                hue_half_width = 7
        sat_min = (
            int(self._debug_snapshot["sat_min"])
            if sat_min_override is None
            else int(sat_min_override)
        )
        val_min = (
            int(self._debug_snapshot["val_min"])
            if val_min_override is None
            else int(val_min_override)
        )
        self._debug_snapshot["sat_min"] = sat_min
        self._debug_snapshot["val_min"] = val_min
        self._debug_snapshot["hue_half_width"] = hue_half_width
        mask = self._build_hue_mask(
            hsv,
            self.hue_center,
            hue_half_width,
            sat_min=sat_min,
            val_min=val_min,
        )

        if not relaxed:
            base_lo_h = self._clamp_hue(HSV_LO[0] - 2)
            base_hi_h = self._clamp_hue(HSV_HI[0] + ADAPTIVE_STRICT_BASE_MARGIN)
            base_mask = cv2.inRange(
                hsv,
                np.array((base_lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((base_hi_h, 255, 255), dtype=np.uint8),
            )
            mask = cv2.bitwise_or(mask, base_mask)

        return mask

    def _scan_contours(self, hsv, mask):
        k = np.ones((3, 3), np.uint8)
        clean = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), k)
        contours, _ = cv2.findContours(
            clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []
        base_min_area = max(100.0, float(BALL_MIN_AREA) * 0.4)
        base_min_circ = ADAPTIVE_MIN_CIRCULARITY
        if self._current_gamma > 1.5:
            base_min_area *= 2.0
            base_min_circ = max(base_min_circ, 0.40)
        min_area = base_min_area
        min_radius = max(5.0, float(BALL_MIN_RADIUS) * 0.6)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue

            (x, y), radius = cv2.minEnclosingCircle(contour)
            if radius < min_radius:
                continue
            if radius > ADAPTIVE_MAX_RADIUS:
                continue

            circularity = self._circularity(contour)
            if circularity < base_min_circ:
                continue

            score = float(radius) * float(circularity)
            candidates.append((score, int(x), int(y), float(radius)))

        candidates.sort(key=lambda c: c[0], reverse=True)

        for score, x, y, radius in candidates[:3]:
            patch_h = self._extract_hue_patch(hsv, x, y, radius)
            if patch_h is None or patch_h.size == 0:
                continue

            patch_median_h = int(np.median(patch_h))
            if (
                patch_median_h < ADAPTIVE_ORANGE_HUE_MIN
                or patch_median_h > ADAPTIVE_ORANGE_HUE_MAX
            ):
                continue

            return (x, y, radius, patch_median_h)

        return None

    def _update_hue_center(self, observed_h):
        observed_h = float(
            max(ADAPTIVE_ORANGE_HUE_MIN, min(ADAPTIVE_ORANGE_HUE_MAX, observed_h))
        )
        self.hue_center = (1.0 - ADAPTIVE_HUE_EMA_ALPHA) * self.hue_center + (
            ADAPTIVE_HUE_EMA_ALPHA * observed_h
        )

    def detect(self, frame, now_ts=None):
        if now_ts is None:
            now_ts = time.time()

        v_median_raw = int(np.median(frame[::4, ::4, :]))
        corrected = self._apply_gamma(frame, v_median_raw)
        hsv = cv2.cvtColor(cv2.GaussianBlur(corrected, (11, 11), 0), cv2.COLOR_BGR2HSV)
        self._v_median_raw = v_median_raw
        frame_h, frame_w = frame.shape[:2]
        use_relaxed = (
            self.miss_streak > 0
            and (now_ts - self.last_seen_ts) <= ADAPTIVE_RELAXED_RECENT_SEC
        )
        should_try_reacquire = self.miss_streak >= ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES

        mode = "strict"

        primary_mask = self._candidate_mask(hsv, relaxed=False)
        best = self._scan_contours(hsv, primary_mask)
        if best is not None:
            cx, cy, r, h = best
            if (
                cy < HOT_PIXEL_Y_MAX
                or cx < BORDER_MARGIN
                or cx > frame_w - BORDER_MARGIN
            ):
                best = None

        if best is None and should_try_reacquire:
            reacquire_mask = self._candidate_mask(
                hsv,
                relaxed=False,
                hue_half_width=16,
                sat_min_override=max(80, int(self._debug_snapshot["sat_min"]) - 10),
                val_min_override=max(50, int(self._debug_snapshot["val_min"]) - 15),
            )
            best = self._scan_contours(hsv, reacquire_mask)
            if best is not None:
                cx, cy, r, h = best
                if (
                    cy < HOT_PIXEL_Y_MAX
                    or cx < BORDER_MARGIN
                    or cx > frame_w - BORDER_MARGIN
                ):
                    best = None
                else:
                    mode = "reacquire"

        if best is None and use_relaxed:
            relaxed_mask = self._candidate_mask(hsv, relaxed=True)
            best = self._scan_contours(hsv, relaxed_mask)
            if best is not None:
                cx, cy, r, h = best
                if (
                    cy < HOT_PIXEL_Y_MAX
                    or cx < BORDER_MARGIN
                    or cx > frame_w - BORDER_MARGIN
                ):
                    best = None
                else:
                    mode = "relaxed"

        if best is None:
            self.miss_streak += 1
            if self.miss_streak > ADAPTIVE_MISS_RESET_FRAMES:
                self.hue_center = float((HSV_LO[0] + HSV_HI[0]) / 2.0)
            self._adjust_exposure(frame_w=frame_w, frame_h=frame_h)
            return None

        cx, cy, radius, observed_h = best
        self._update_hue_center(observed_h)
        self.last_seen_ts = now_ts
        self.miss_streak = 0
        self.last_mode = mode
        self._debug_snapshot["hue_center"] = float(self.hue_center)
        self._debug_snapshot["mode"] = mode
        return cx, cy, radius

    def get_debug_snapshot(self):
        return dict(self._debug_snapshot)


_ADAPTIVE_ORANGE_DETECTOR = AdaptiveOrangeBallDetector()


CAMERA_EXPOSURE = CAMERA_EXPOSURE_DEFAULT = 200
CAMERA_BRIGHTNESS = 0


CAMERA_WIDTH = 320
CAMERA_HEIGHT = 240


class ThreadedCamera:
    def __init__(self, cap, downscale=False):
        self.cap = cap
        self._lock = Lock()
        self._frame = None
        self._new = False
        self._running = True
        self._downscale = downscale
        self._thread = __import__("threading").Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if ok and frame is not None:
                if self._downscale:
                    frame = cv2.resize(
                        frame,
                        (CAMERA_WIDTH, CAMERA_HEIGHT),
                        interpolation=cv2.INTER_AREA,
                    )
                with self._lock:
                    self._frame = frame
                    self._new = True

    def read(self):
        with self._lock:
            if self._new and self._frame is not None:
                self._new = False
                return True, self._frame.copy()
            return False, None

    def get(self, prop):
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return CAMERA_WIDTH if self._downscale else self.cap.get(prop)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return CAMERA_HEIGHT if self._downscale else self.cap.get(prop)
        return self.cap.get(prop)

    def release(self):
        self._running = False
        self._thread.join(timeout=2.0)
        self.cap.release()


def _calibrate_exposure(cap):
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
    cap.set(cv2.CAP_PROP_EXPOSURE, CAMERA_EXPOSURE_DEFAULT)
    for _ in range(8):
        cap.grab()
    ok, frame = cap.read()
    if ok and frame is not None:
        v_med = int(np.median(frame[::4, ::4, :]))
        log.info("Camara exp=%d v_median_raw=%d", CAMERA_EXPOSURE_DEFAULT, v_med)
    return CAMERA_EXPOSURE_DEFAULT


def find_camera(threaded=False, downscale=False):
    for i in range(6):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            ok, f = cap.read()
            if ok and f is not None:
                h, w = f.shape[:2]
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                exp = _calibrate_exposure(cap)
                for _ in range(8):
                    cap.grab()
                log.info("Camara detectada: /dev/video%d (%dx%d) exp=%d", i, w, h, exp)
                if threaded or downscale:
                    cap = ThreadedCamera(cap, downscale=downscale)
                return cap, CAMERA_WIDTH if downscale else w, exp
            cap.release()
    return None, 0, 0


YOLO_MODEL_PATH = Path(__file__).parent / "model.onnx"
YOLO_IMGSZ = 320
YOLO_BALL_CLASS_ID = 0
YOLO_CONF_THRESHOLD = 0.35


class YOLOBallDetector:
    def __init__(self):
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = 4
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            str(YOLO_MODEL_PATH), sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name
        self._debug_snapshot = {"detector": "yolo", "raw_detections": 0}

    def detect(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1.0 / 255.0, (YOLO_IMGSZ, YOLO_IMGSZ), swapRB=True
        ).astype(np.float32)
        outputs = self.session.run(None, {self.input_name: blob})
        predictions = outputs[0][0]

        best = None
        best_conf = 0.0
        raw_count = 0

        for pred in predictions:
            x1, y1, x2, y2, conf, cls_id = pred
            if conf < YOLO_CONF_THRESHOLD:
                continue
            if int(round(cls_id)) != YOLO_BALL_CLASS_ID:
                continue
            raw_count += 1
            if conf > best_conf:
                best_conf = conf
                best = (x1, y1, x2, y2, conf)

        self._debug_snapshot["raw_detections"] = raw_count
        self._debug_snapshot["best_conf"] = float(best_conf) if best else 0.0

        if best is None:
            return None

        x1, y1, x2, y2, conf = best
        scale_x = w / YOLO_IMGSZ
        scale_y = h / YOLO_IMGSZ
        x1 = x1 * scale_x
        y1 = y1 * scale_y
        x2 = x2 * scale_x
        y2 = y2 * scale_y

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        r = max(x2 - x1, y2 - y1) / 2.0

        return int(cx), int(cy), float(r)

    def get_debug_snapshot(self):
        return dict(self._debug_snapshot)


def create_detector():
    return _ADAPTIVE_ORANGE_DETECTOR


def detect_ball(frame):
    return _ADAPTIVE_ORANGE_DETECTOR.detect(frame)


def get_ball_detection_debug():
    return _ADAPTIVE_ORANGE_DETECTOR.get_debug_snapshot()