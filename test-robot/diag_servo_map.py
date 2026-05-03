"""Diagnostico rapido de mapeo servo-pelota.

Uso: uv run diag_servo_map.py

Centra los servos, sube exposicion al maximo, y reporta
la posicion de la pelota + el mapeo a servos cada frame.
"""

import cv2
import time
import sys

from hardware import (
    PAN_CENTER,
    TILT_CENTER,
    detect_ball,
    find_camera,
    get_ball_detection_debug,
    log,
    map_ball_to_servos,
    SerialBus,
)


def main():
    cap, fw, _ = find_camera()
    if not cap:
        log.error("No se detecto camara")
        return

    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    sbus = SerialBus()
    time.sleep(0.3)

    cap.set(cv2.CAP_PROP_EXPOSURE, 1500)
    time.sleep(0.5)
    for _ in range(5):
        cap.grab()

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.8)

    log.info("Centrado. Exposicion=1500. Buscando pelota 10s...")
    log.info("Pon la pelota frente al robot (~50cm).")
    log.info(
        "Formato: cx,cy -> pan,tilt  (si pan~%d tilt~%d = correcto)",
        PAN_CENTER,
        TILT_CENTER,
    )

    t0 = time.time()
    detected_any = False
    while time.time() - t0 < 15:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.02)
            continue

        ball = detect_ball(frame)
        dbg = get_ball_detection_debug()
        vm = dbg.get("v_median", 0)

        if ball:
            cx, cy, r = ball
            pan, tilt = map_ball_to_servos(cx, cy, fw, fh)
            dist_pan = abs(pan - PAN_CENTER)
            dist_tilt = abs(tilt - TILT_CENTER)
            log.info(
                "DETECTED cx=%d cy=%d r=%.0f -> pan=%d tilt=%d (off: pan%+d tilt%+d) vm=%d",
                cx,
                cy,
                r,
                pan,
                tilt,
                pan - PAN_CENTER,
                tilt - TILT_CENTER,
                vm,
            )
            detected_any = True
        elif not detected_any:
            if int(time.time() - t0) % 3 == 0:
                log.info("No detecta. vm=%d (esperando pelota...)", vm)

    if not detected_any:
        log.info(
            "No se detecto pelota en 15s. Verifica que este en el campo de vision."
        )

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.3)
    cap.release()
    sbus.stop()
    sbus.close()


if __name__ == "__main__":
    main()