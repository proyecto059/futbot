#!/usr/bin/env python3
"""Capture 10 consecutive frames showing raw + confirmed detection positions."""

import time
import cv2
from hardware import (
    find_camera,
    detect_ball,
    get_ball_detection_debug,
    SerialBus,
    PAN_CENTER,
    TILT_CENTER,
    log,
    SERVO_PAN_INVERTED,
    SERVO_TILT_INVERTED,
)

PAN_GAIN = 0.025
TILT_GAIN = 0.025
DEADBAND = 30
MAX_DELTA = 5

sbus = SerialBus()
sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
time.sleep(1.5)

cap, fw, _ = find_camera()
if not cap:
    sbus.close()
    exit(1)

fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
fcx, fcy = fw // 2, fh // 2
pan = float(PAN_CENTER)
tilt = float(TILT_CENTER)

log.info("=== 50 FRAME RAW DIAGNOSTIC ===")

all_detections = []
for i in range(50):
    ok, frame = cap.read()
    if not ok:
        continue
    ball = detect_ball(frame)
    if ball:
        cx, cy, r = ball
        off_x = cx - fcx
        off_y = cy - fcy

        if abs(off_x) > DEADBAND:
            pd = -PAN_GAIN * off_x if SERVO_PAN_INVERTED else PAN_GAIN * off_x
        else:
            pd = 0.0
        td = TILT_GAIN * off_y if SERVO_TILT_INVERTED else -TILT_GAIN * off_y
        pd = max(-MAX_DELTA, min(MAX_DELTA, pd))
        td = max(-MAX_DELTA, min(MAX_DELTA, td))
        pan = max(0, min(180, pan + pd))
        tilt = max(0, min(180, tilt + td))

        log.info(
            "[%2d] DET cx=%3d cy=%3d r=%5.1f | off=(%+4d,%+4d) | delta=(%+.2f,%+.2f) | pan=%.1f tilt=%.1f",
            i,
            cx,
            cy,
            r,
            off_x,
            off_y,
            pd,
            td,
            pan,
            tilt,
        )
        sbus.burst(int(pan), int(tilt), 200, 0, 0, 0, 0)
    else:
        log.info("[%2d] LOST | pan=%.1f tilt=%.1f", i, pan, tilt)

cap.release()
sbus.close()
log.info("=== END ===")
