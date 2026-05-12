#!/usr/bin/env python3
import time
import os

import cv2
import numpy as np

from hardware import (
    HSV_HI,
    HSV_LO,
    detect_ball,
    find_camera,
    get_ball_detection_debug,
)

OUT_DIR = "/tmp/diag_vision"
os.makedirs(OUT_DIR, exist_ok=True)

cap, fw, _ = find_camera()
if not cap:
    print("No se encontro camara!")
    exit(1)

fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
print(f"HSV base: LO={HSV_LO} HI={HSV_HI}")
print("Apunta la camara a la pelota naranja.")
print(f"Guardando frames en {OUT_DIR}/ cada 2s por 20s...")
print()

t0 = time.time()
n = 0

while time.time() - t0 < 20:
    ok, frame = cap.read()
    if not ok:
        continue

    ball = detect_ball(frame)
    dbg = get_ball_detection_debug()

    hsv = cv2.cvtColor(cv2.GaussianBlur(frame, (11, 11), 0), cv2.COLOR_BGR2HSV)
    sat_min = int(dbg.get("sat_min", HSV_LO[1]))
    val_min = int(dbg.get("val_min", HSV_LO[2]))
    hue_center = int(round(float(dbg.get("hue_center", (HSV_LO[0] + HSV_HI[0]) / 2))))
    hue_half = int(dbg.get("hue_half_width", 8))

    lo_h = max(0, hue_center - hue_half)
    hi_h = min(179, hue_center + hue_half)
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

    k = np.ones((5, 5), np.uint8)
    mask_clean = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), k)

    overlay = frame.copy()
    ball_info = "NO DETECTADA"
    if ball is not None:
        cx, cy, r = ball
        cv2.circle(overlay, (int(cx), int(cy)), int(r), (0, 255, 0), 2)
        ball_info = (
            f"cx={int(cx)} cy={int(cy)} r={int(r)} "
            f"mode={dbg.get('mode', '-')} "
            f"h={float(dbg.get('hue_center', 0.0)):.1f} "
            f"sv=({sat_min},{val_min}) vm={int(dbg.get('v_median', 0))}"
        )
        region = hsv[int(cy) - 5 : int(cy) + 5, int(cx) - 5 : int(cx) + 5]
        if region.size > 0:
            h_vals = region[:, :, 0].flatten()
            s_vals = region[:, :, 1].flatten()
            v_vals = region[:, :, 2].flatten()
            print(
                f"  Pelota HSV: H=[{h_vals.min()}-{h_vals.max()}] "
                f"S=[{s_vals.min()}-{s_vals.max()}] "
                f"V=[{v_vals.min()}-{v_vals.max()}]"
            )

    mask_bgr = cv2.cvtColor(mask_clean, cv2.COLOR_GRAY2BGR)

    combined = np.hstack(
        [
            overlay,
            cv2.putText(
                mask_bgr.copy(),
                ball_info,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            ),
        ]
    )

    n += 1
    path = os.path.join(OUT_DIR, f"frame_{n:03d}.jpg")
    cv2.imwrite(path, combined)
    print(f"[{n}] {ball_info} -> {path}")
    time.sleep(2)

cap.release()
print(f"\nDone. {n} frames guardados en {OUT_DIR}/")
print("Copia a tu PC con: scp -r raspi@raspi.local:/tmp/diag_vision .")