"""Diagnostico de direccion de mapeo servo.

Centra servos, espera deteccion, y muestra en que direccion
se mueve el servo vs donde esta la pelota en el frame.
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

    cap.set(cv2.CAP_PROP_EXPOSURE, 1023)
    time.sleep(0.5)
    for _ in range(5):
        cap.grab()

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.8)

    log.info("=== DIAGNOSTICO DE MAPEO SERVO ===")
    log.info(
        "Frame: %dx%d  Pan center=%d  Tilt center=%d", fw, fh, PAN_CENTER, TILT_CENTER
    )
    log.info("Pon la pelota a la DERECHA del robot. Observa si pan sube o baja.")
    log.info(
        "Si pan SUBE (se aleja del center=%d) cuando pelota esta a la derecha, el mapeo esta INVERTIDO.",
        PAN_CENTER,
    )
    log.info("")

    t0 = time.time()
    last_log = 0
    while time.time() - t0 < 30:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.02)
            continue

        ball = detect_ball(frame)
        now = time.time()

        if ball and (now - last_log >= 0.3):
            cx, cy, r = ball
            pan, tilt = map_ball_to_servos(cx, cy, fw, fh)

            side_x = (
                "LEFT" if cx < fw // 3 else "CENTER" if cx < 2 * fw // 3 else "RIGHT"
            )
            side_y = "TOP" if cy < fh // 3 else "MID" if cy < 2 * fh // 3 else "BOTTOM"

            pan_dir = (
                "RIGHT"
                if pan > PAN_CENTER
                else "LEFT"
                if pan < PAN_CENTER
                else "CENTER"
            )
            tilt_dir = (
                "DOWN"
                if tilt > TILT_CENTER
                else "UP"
                if tilt < TILT_CENTER
                else "CENTER"
            )

            log.info(
                "ball %s-%s (cx=%d cy=%d) -> servo pan=%d(%s) tilt=%d(%s)  [pan_off=%+d tilt_off=%+d]",
                side_x,
                side_y,
                cx,
                cy,
                pan,
                pan_dir,
                tilt,
                tilt_dir,
                pan - PAN_CENTER,
                tilt - TILT_CENTER,
            )
            last_log = now

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.3)
    cap.release()
    sbus.stop()
    sbus.close()


if __name__ == "__main__":
    main()