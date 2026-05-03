#!/usr/bin/env python3
"""Save a frame and show ALL detections (not just best)."""

import time
import cv2
import numpy as np
from hardware import (
    find_camera,
    SerialBus,
    PAN_CENTER,
    TILT_CENTER,
    log,
    HSV_LO,
    ADAPTIVE_MIN_CIRCULARITY,
    ADAPTIVE_MAX_RADIUS,
    ADAPTIVE_ORANGE_HUE_MIN,
    ADAPTIVE_ORANGE_HUE_MAX,
)

sbus = SerialBus()
sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
time.sleep(1.5)

cap, fw, _ = find_camera()
if not cap:
    sbus.close()
    exit(1)

fh = 480
ok, frame = cap.read()
if not ok:
    cap.release()
    sbus.close()
    exit(1)

hsv = cv2.cvtColor(cv2.GaussianBlur(frame, (11, 11), 0), cv2.COLOR_BGR2HSV)

lo_h, hi_h = HSV_LO[0], 20
sat_min, val_min = HSV_LO[1], HSV_LO[2]

mask = cv2.inRange(
    hsv,
    np.array((lo_h, sat_min, val_min), dtype=np.uint8),
    np.array((hi_h, 255, 255), dtype=np.uint8),
)

k = np.ones((3, 3), np.uint8)
clean = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), k)
contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

log.info(
    "Frame %dx%d | HSV lo=(%d,%d,%d) hi_h=%d", fw, fh, lo_h, sat_min, val_min, hi_h
)
log.info("Found %d contours", len(contours))

for i, contour in enumerate(contours):
    area = cv2.contourArea(contour)
    if area < 220:
        continue
    (x, y), radius = cv2.minEnclosingCircle(contour)
    if radius < 7 or radius > ADAPTIVE_MAX_RADIUS:
        continue
    perimeter = cv2.arcLength(contour, True)
    circ = 4 * np.pi * area / (perimeter * perimeter) if perimeter > 0 else 0
    if circ < 0.20:
        continue

    patch_r = int(max(3, min(12, radius * 0.4)))
    px0 = max(0, int(x) - patch_r)
    py0 = max(0, int(y) - patch_r)
    px1 = min(fw, int(x) + patch_r + 1)
    py1 = min(fh, int(y) + patch_r + 1)
    patch = hsv[py0:py1, px0:px1, 0]
    patch_h = int(np.median(patch)) if patch.size > 0 else -1

    sat_patch = hsv[py0:py1, px0:px1, 1]
    val_patch = hsv[py0:py1, px0:px1, 2]
    sat_med = int(np.median(sat_patch)) if sat_patch.size > 0 else 0
    val_med = int(np.median(val_patch)) if val_patch.size > 0 else 0

    log.info(
        "  [%d] cx=%d cy=%d r=%.0f area=%.0f circ=%.2f h_median=%d s_median=%d v_median=%d hue_ok=%s",
        i,
        int(x),
        int(y),
        radius,
        area,
        circ,
        patch_h,
        sat_med,
        val_med,
        ADAPTIVE_ORANGE_HUE_MIN <= patch_h <= ADAPTIVE_ORANGE_HUE_MAX,
    )

cv2.imwrite("/tmp/diag_frame.png", frame)
log.info("Saved /tmp/diag_frame.png")
cap.release()
sbus.close()