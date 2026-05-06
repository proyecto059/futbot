import time
import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path
from hardware import (
    find_camera,
    SerialBus,
    log,
    PAN_CENTER,
    TILT_CENTER,
    PAN_MIN,
    PAN_MAX,
    SERVO_PAN_INVERTED,
    SERVO_TILT_INVERTED,
    detect_ball,
)

YOLO_MODEL = Path(__file__).parent / "model.onnx"
YOLO_IMGSZ = 320
YOLO_BALL_CLASS = 0
YOLO_CONF = 0.25

SWEEP_PAN_START = 40
SWEEP_PAN_END = 150
SWEEP_PAN_STEP = 8
SWEEP_TILT = 129
SWEEP_SETTLE_SEC = 1.5
SAMPLES_PER_POS = 5


def yolo_detect(session, input_name, frame):
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(
        frame, 1.0 / 255.0, (YOLO_IMGSZ, YOLO_IMGSZ), swapRB=True
    ).astype(np.float32)
    preds = session.run(None, {input_name: blob})[0][0]
    best = None
    best_conf = 0.0
    for pred in preds:
        x1, y1, x2, y2, conf, cls_id = pred
        if conf < YOLO_CONF or int(round(cls_id)) != YOLO_BALL_CLASS:
            continue
        if conf > best_conf:
            best_conf = conf
            best = (x1, y1, x2, y2, conf)
    if best is None:
        return None
    x1, y1, x2, y2, conf = best
    sx, sy = w / YOLO_IMGSZ, h / YOLO_IMGSZ
    return int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy), float(conf)


def main():
    cap, fw, _ = find_camera()
    if not cap:
        log.error("No camera")
        return
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    sbus = SerialBus()

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = 4
    session = ort.InferenceSession(
        str(YOLO_MODEL), sess_options=opts, providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name

    log.info(
        "Barrido pan=%d..%d step=%d buscando pelota...",
        SWEEP_PAN_START,
        SWEEP_PAN_END,
        SWEEP_PAN_STEP,
    )

    found_pan = None
    found_det = None

    for pan in range(SWEEP_PAN_START, SWEEP_PAN_END + 1, SWEEP_PAN_STEP):
        sbus.burst(pan, SWEEP_TILT, 500, 0, 0, 0, 0)
        time.sleep(SWEEP_SETTLE_SEC)

        for _ in range(SAMPLES_PER_POS):
            ok, frame = cap.read()
            if not ok:
                continue
            det = yolo_detect(session, input_name, frame)
            if det is not None:
                found_pan = pan
                found_det = det
                log.info("PELOTA ENCONTRADA! pan=%d det=%s", pan, det)
                break
        if found_det is not None:
            break

    if found_det is None:
        log.error("No se encontro pelota en el barrido. Abortando.")
        sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
        cap.release()
        sbus.close()
        return

    pan = found_pan
    sbus.burst(pan, SWEEP_TILT, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    all_h = []
    all_s = []
    all_v = []
    hsv_hits = 0
    hsv_in_yolo = 0
    hsv_out_yolo = 0
    total = 20

    log.info("Midiendo HSV en %d frames con pan=%d...", total, pan)
    for i in range(total):
        ok, frame = cap.read()
        if not ok:
            continue

        hsv = cv2.cvtColor(cv2.GaussianBlur(frame, (11, 11), 0), cv2.COLOR_BGR2HSV)
        yolo_det = yolo_detect(session, input_name, frame)
        hsv_det = detect_ball(frame)

        if yolo_det is not None:
            x1, y1, x2, y2, conf = yolo_det
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            margin = int(max(x2 - x1, y2 - y1) * 0.15)
            rx1 = max(0, x1 + margin)
            ry1 = max(0, y1 + margin)
            rx2 = min(fw, x2 - margin)
            ry2 = min(fh, y2 - margin)
            region = hsv[ry1:ry2, rx1:rx2]
            if region.size > 0:
                all_h.extend(region[:, :, 0].flatten().tolist())
                all_s.extend(region[:, :, 1].flatten().tolist())
                all_v.extend(region[:, :, 2].flatten().tolist())

            if hsv_det is not None:
                hsv_hits += 1
                hcx, hcy, hr = hsv_det
                if x1 <= hcx <= x2 and y1 <= hcy <= y2:
                    hsv_in_yolo += 1
                else:
                    hsv_out_yolo += 1
                    log.info(
                        "  HSV en (%d,%d) FUERA de bbox YOLO (%d,%d,%d,%d)",
                        hcx,
                        hcy,
                        x1,
                        y1,
                        x2,
                        y2,
                    )

            log.info(
                "[%d] YOLO conf=%.2f bbox=(%d,%d,%d,%d) | HSV: %s",
                i,
                conf,
                x1,
                y1,
                x2,
                y2,
                "detect" if hsv_det else "lost",
            )
        else:
            log.info("[%d] YOLO lost", i)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    cap.release()
    sbus.close()

    log.info("=" * 60)
    log.info("RESULTADOS")
    log.info("=" * 60)
    log.info("HSV dentro de bbox YOLO:  %d", hsv_in_yolo)
    log.info("HSV fuera de bbox YOLO:   %d (falsos positivos)", hsv_out_yolo)
    log.info("HSV no detecto nada:     %d", total - hsv_hits)

    if all_h:
        h_arr = np.array(all_h)
        s_arr = np.array(all_s)
        v_arr = np.array(all_v)
        log.info("-" * 60)
        log.info("HSV PIXELES de la pelota (n=%d):", len(h_arr))
        log.info(
            "  Hue: mean=%.1f median=%.1f p5=%.1f p10=%.1f p25=%.1f p75=%.1f p90=%.1f p95=%.1f",
            np.mean(h_arr),
            np.median(h_arr),
            np.percentile(h_arr, 5),
            np.percentile(h_arr, 10),
            np.percentile(h_arr, 25),
            np.percentile(h_arr, 75),
            np.percentile(h_arr, 90),
            np.percentile(h_arr, 95),
        )
        log.info(
            "  Sat: mean=%.1f median=%.1f p5=%.1f p10=%.1f min=%d max=%d",
            np.mean(s_arr),
            np.median(s_arr),
            np.percentile(s_arr, 5),
            np.percentile(s_arr, 10),
            np.min(s_arr),
            np.max(s_arr),
        )
        log.info(
            "  Val: mean=%.1f median=%.1f p5=%.1f p10=%.1f min=%d max=%d",
            np.mean(v_arr),
            np.median(v_arr),
            np.percentile(v_arr, 5),
            np.percentile(v_arr, 10),
            np.min(v_arr),
            np.max(v_arr),
        )
        log.info("-" * 60)
        h_lo = max(0, int(np.percentile(h_arr, 2)) - 2)
        h_hi = min(179, int(np.percentile(h_arr, 98)) + 2)
        s_lo = max(50, int(np.percentile(s_arr, 2)) - 10)
        v_lo = max(20, int(np.percentile(v_arr, 2)) - 10)
        log.info("HSV ACTUAL:  LO=(5, 160, 45)  HI=(20, 255, 255)")
        log.info(
            "HSV SUGERIDO: LO=(%d, %d, %d)  HI=(%d, 255, 255)", h_lo, s_lo, v_lo, h_hi
        )
    log.info("=" * 60)


if __name__ == "__main__":
    main()
