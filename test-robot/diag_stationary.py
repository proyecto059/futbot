#!/usr/bin/env python3
"""Detect ball with servos LOCKED at center - no movement."""

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
)

sbus = SerialBus()
sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
time.sleep(1.5)

cap, fw, _ = find_camera()
if not cap:
    log.error("No camera")
    sbus.close()
    exit(1)

fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
fcx = fw // 2
fcy = fh // 2

log.info("=== STATIONARY DETECTION (servos locked at center) ===")
log.info("Frame: %dx%d center=(%d,%d)", fw, fh, fcx, fcy)

detected = 0
lost = 0
for i in range(40):
    ok, frame = cap.read()
    if not ok:
        continue
    ball = detect_ball(frame)
    dbg = get_ball_detection_debug()
    if ball:
        cx, cy, r = ball
        detected += 1
        log.info(
            "  [%2d] DETECT cx=%3d cy=%3d r=%.0f | off_x=%+d off_y=%+d | h=%.1f sat=%d val=%d vm=%d mode=%s",
            i,
            cx,
            cy,
            r,
            cx - fcx,
            cy - fcy,
            dbg.get("hue_center", 0),
            dbg.get("sat_min", 0),
            dbg.get("val_min", 0),
            dbg.get("v_median", 0),
            dbg.get("mode", "-"),
        )
    else:
        lost += 1
        log.info("  [%2d] LOST | vm=%d", i, dbg.get("v_median", 0))

log.info("=== RESULT: detected=%d lost=%d ===", detected, lost)
cap.release()
sbus.close()