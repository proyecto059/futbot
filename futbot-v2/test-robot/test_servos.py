import time

from hardware import (
    PAN_CENTER,
    PAN_MAX,
    PAN_MIN,
    SERVO_MAX_ANGLE,
    SERVO_MIN_ANGLE,
    SERVO_PAN_INVERTED,
    SERVO_TILT_INVERTED,
    TILT_CENTER,
    create_detector,
    find_camera,
    log,
    map_ball_to_servos,
)
import cv2
import numpy as np

TEST_SERVO_DURATION = 60.0
TRACK_CONFIRM_FRAMES = 2
LOST_CONFIRM_FRAMES = 15
HOLD_NO_DETECT_SEC = 2.0
TRACK_ALPHA = 0.6
RECENTER_ALPHA = 0.1
MAX_TRACK_DELTA_PER_FRAME = 15
TRACK_DEADBAND_PX = 30
MAX_TRACK_DELTA_NEAR_CENTER = 4
PAN_GAIN = 0.02
TILT_GAIN = 0.02
MAX_BALL_JUMP_PX = 400
MIN_RADIUS_RATIO = 0.25
TRACKING_LOCKED_JUMP_PX = 200
TRACKING_LOCKED_RADIUS_RATIO = 0.3
BALL_EMA_ALPHA = 0.7
RADIUS_CONSISTENCY_MIN = 0.5
RADIUS_CONSISTENCY_MAX = 2.0
PAN_GAIN_ROTATION = 0.04
MAX_TRACK_DELTA_ROTATION = 30


# ── Servo ball tracker ──────────────────────────────────────────────────────


def recenter_step(current, target, alpha):
    next_value = int(current + (target - current) * alpha)
    if next_value != current:
        return next_value
    if target > current:
        return current + 1
    if target < current:
        return current - 1
    return current


def tracking_step(current, target, alpha, max_delta_per_frame):
    raw_next = int(current + (target - current) * alpha)
    delta = raw_next - current
    if delta == 0 and target != current:
        delta = 1 if target > current else -1
    if delta > max_delta_per_frame:
        delta = max_delta_per_frame
    elif delta < -max_delta_per_frame:
        delta = -max_delta_per_frame
    return current + delta


def should_hold_pan(cx, frame_center_x, deadband_px):
    return abs(cx - frame_center_x) <= deadband_px


def max_tracking_delta(
    cx,
    frame_center_x,
    deadband_px,
    near_center_delta,
    far_delta,
):
    if should_hold_pan(cx, frame_center_x, deadband_px):
        return near_center_delta
    return far_delta


def should_enter_tracking(consecutive_detect, tracking_locked, track_confirm_frames):
    return tracking_locked or consecutive_detect >= track_confirm_frames


def should_keep_lock_on_miss(consecutive_miss, hold_window_active, lost_confirm_frames):
    return consecutive_miss < lost_confirm_frames or hold_window_active


def detection_is_consistent(
    previous_ball,
    current_ball,
    max_jump_px,
    min_radius_ratio,
):
    if previous_ball is None or current_ball is None:
        return True

    px, py, pr = previous_ball
    cx, cy, cr = current_ball
    if pr <= 0 or cr <= 0:
        return False

    dx = cx - px
    dy = cy - py
    jump = (dx * dx + dy * dy) ** 0.5
    if jump > max_jump_px:
        return False

    ratio = float(cr) / float(pr)
    max_radius_ratio = 1.0 / min_radius_ratio
    return min_radius_ratio <= ratio <= max_radius_ratio


def should_validate_detection(
    previous_ball,
    has_seen_ball,
    tracking_locked,
    last_seen_ts,
    now_ts,
    hold_no_detect_sec,
):
    return (
        previous_ball is not None
        and has_seen_ball
        and tracking_locked
        and (now_ts - last_seen_ts) < hold_no_detect_sec
    )


class BallKalmanFilter:
    def __init__(self):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        self.kf.transitionMatrix = np.array(
            [[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]],
            np.float32,
        )
        self.kf.processNoiseCov = np.diag([4, 4, 1, 1]).astype(np.float32)
        self.kf.measurementNoiseCov = np.diag([10, 10]).astype(np.float32)
        self.initialized = False

    def init(self, cx, cy):
        self.kf.statePost = np.array([[cx], [cy], [0], [0]], np.float32)
        self.initialized = True

    def predict(self):
        if not self.initialized:
            return None
        p = self.kf.predict()
        return int(p[0]), int(p[1])

    def correct(self, cx, cy):
        if not self.initialized:
            self.init(cx, cy)
            return cx, cy
        meas = np.array([[np.float32(cx)], [np.float32(cy)]])
        c = self.kf.correct(meas)
        return int(c[0]), int(c[1])

    def reset(self):
        self.initialized = False


class ServoBallTracker:
    def __init__(
        self,
        fw,
        fh,
        track_confirm_frames=TRACK_CONFIRM_FRAMES,
        lost_confirm_frames=LOST_CONFIRM_FRAMES,
        hold_no_detect_sec=HOLD_NO_DETECT_SEC,
        track_alpha=TRACK_ALPHA,
        recenter_alpha=RECENTER_ALPHA,
        max_track_delta=MAX_TRACK_DELTA_PER_FRAME,
        track_deadband_px=TRACK_DEADBAND_PX,
        max_track_delta_near_center=MAX_TRACK_DELTA_NEAR_CENTER,
        max_ball_jump_px=MAX_BALL_JUMP_PX,
        min_radius_ratio=MIN_RADIUS_RATIO,
        tracking_locked_jump_px=TRACKING_LOCKED_JUMP_PX,
        tracking_locked_radius_ratio=TRACKING_LOCKED_RADIUS_RATIO,
        ball_ema_alpha=BALL_EMA_ALPHA,
        radius_consistency_min=RADIUS_CONSISTENCY_MIN,
        radius_consistency_max=RADIUS_CONSISTENCY_MAX,
        sweep_enabled=False,
        sweep_step=5,
    ):
        self.fw = fw
        self.fh = fh
        self.fcx = fw // 2
        self.track_confirm_frames = track_confirm_frames
        self.lost_confirm_frames = lost_confirm_frames
        self.hold_no_detect_sec = hold_no_detect_sec
        self.track_alpha = track_alpha
        self.recenter_alpha = recenter_alpha
        self.max_track_delta = max_track_delta
        self.track_deadband_px = track_deadband_px
        self.max_track_delta_near_center = max_track_delta_near_center
        self.max_ball_jump_px = max_ball_jump_px
        self.min_radius_ratio = min_radius_ratio
        self.tracking_locked_jump_px = tracking_locked_jump_px
        self.tracking_locked_radius_ratio = tracking_locked_radius_ratio
        self.ball_ema_alpha = ball_ema_alpha
        self.radius_consistency_min = radius_consistency_min
        self.radius_consistency_max = radius_consistency_max
        self.sweep_enabled = sweep_enabled
        self.sweep_step = sweep_step

        self.pan = PAN_CENTER
        self.tilt = TILT_CENTER
        self.consecutive_detect = 0
        self.consecutive_miss = 0
        self.last_seen_ts = 0.0
        self.has_seen_ball = False
        self.tracking_locked = False
        self.last_valid_ball = None
        self.ema_cx = None
        self.ema_cy = None
        self.last_radius = None
        self.sweep_dir = 1
        self.frames_since_rotation = 0
        self.kf = BallKalmanFilter()
        self.kf_pred = None

    def _recenter_alpha(self):
        if self.frames_since_rotation < 5:
            return 0.4
        if self.frames_since_rotation < 15:
            return 0.2
        return self.recenter_alpha

    def update(self, raw_ball, now, rotation_ff=0.0):
        ball = raw_ball
        reject_reason = "-"
        has_rotation = abs(rotation_ff) > 0.01
        if has_rotation:
            self.frames_since_rotation = 0
        else:
            self.frames_since_rotation += 1

        if raw_ball is not None:
            sv = should_validate_detection(
                previous_ball=self.last_valid_ball,
                has_seen_ball=self.has_seen_ball,
                tracking_locked=self.tracking_locked,
                last_seen_ts=self.last_seen_ts,
                now_ts=now,
                hold_no_detect_sec=self.hold_no_detect_sec,
            )
            mj = (
                self.tracking_locked_jump_px
                if self.tracking_locked
                else self.max_ball_jump_px
            )
            if has_rotation:
                mj = int(mj * 1.5)
            mr = (
                self.tracking_locked_radius_ratio
                if self.tracking_locked
                else self.min_radius_ratio
            )
            if sv and not detection_is_consistent(
                self.last_valid_ball, raw_ball, mj, mr
            ):
                ball = None
                reject_reason = "jump/radius"
            else:
                self.last_valid_ball = raw_ball

        detected = False
        mode = "hold"

        if ball:
            cx, cy, r = ball
            self.consecutive_detect += 1
            self.consecutive_miss = 0
            self.last_seen_ts = now
            self.has_seen_ball = True
            detected = True

            if self.ema_cx is None:
                self.ema_cx = cx
                self.ema_cy = cy
                self.last_radius = r
            else:
                if self.last_radius is not None and self.last_radius > 0:
                    r_ratio = r / self.last_radius
                    if (
                        r_ratio < self.radius_consistency_min
                        or r_ratio > self.radius_consistency_max
                    ):
                        self.ema_cx = int(
                            self.ema_cx + self.ball_ema_alpha * 0.2 * (cx - self.ema_cx)
                        )
                        self.ema_cy = int(
                            self.ema_cy + self.ball_ema_alpha * 0.2 * (cy - self.ema_cy)
                        )
                        self.last_radius = self.last_radius * 0.8 + r * 0.2
                    else:
                        self.ema_cx = int(
                            self.ema_cx + self.ball_ema_alpha * (cx - self.ema_cx)
                        )
                        self.ema_cy = int(
                            self.ema_cy + self.ball_ema_alpha * (cy - self.ema_cy)
                        )
                        self.last_radius = self.last_radius * 0.6 + r * 0.4
                else:
                    self.ema_cx = int(
                        self.ema_cx + self.ball_ema_alpha * (cx - self.ema_cx)
                    )
                    self.ema_cy = int(
                        self.ema_cy + self.ball_ema_alpha * (cy - self.ema_cy)
                    )
                    self.last_radius = r

            kf_cx, kf_cy = self.kf.correct(cx, cy)
            self.kf_pred = (kf_cx, kf_cy)

            if should_enter_tracking(
                self.consecutive_detect,
                self.tracking_locked,
                self.track_confirm_frames,
            ):
                self.tracking_locked = True

                offset_x = cx - self.fcx
                offset_y = cy - (self.fh // 2)

                if abs(offset_x) <= self.track_deadband_px:
                    offset_x = 0

                pan_gain = PAN_GAIN_ROTATION if has_rotation else PAN_GAIN
                max_delta = (
                    MAX_TRACK_DELTA_ROTATION if has_rotation else self.max_track_delta
                )

                if SERVO_PAN_INVERTED:
                    pan_delta = -pan_gain * offset_x
                else:
                    pan_delta = pan_gain * offset_x

                if SERVO_TILT_INVERTED:
                    tilt_delta = TILT_GAIN * offset_y
                else:
                    tilt_delta = -TILT_GAIN * offset_y

                pan_delta = max(-max_delta, min(max_delta, pan_delta))
                tilt_delta = max(-max_delta, min(max_delta, tilt_delta))

                self.pan = int(self.pan + pan_delta + rotation_ff)
                self.tilt = int(self.tilt + tilt_delta)

                self.pan = max(PAN_MIN, min(PAN_MAX, self.pan))
                self.tilt = max(0, min(180, self.tilt))
                mode = "tracking"
            else:
                if has_rotation:
                    self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + rotation_ff)))
                mode = "acquire"
        else:
            self.consecutive_miss += 1
            self.consecutive_detect = max(0, self.consecutive_detect - 1)
            pred = self.kf.predict()
            if pred is not None:
                self.kf_pred = pred
            hold_window_active = (
                self.has_seen_ball
                and (now - self.last_seen_ts) < self.hold_no_detect_sec
            )

            if should_keep_lock_on_miss(
                self.consecutive_miss,
                hold_window_active,
                self.lost_confirm_frames,
            ):
                mode = "hold"
                if has_rotation:
                    self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + rotation_ff)))
                elif self.kf_pred is not None and self.consecutive_miss <= 5:
                    pred_cx, pred_cy = self.kf_pred
                    offset_x = pred_cx - self.fcx
                    if abs(offset_x) > self.track_deadband_px:
                        if SERVO_PAN_INVERTED:
                            pan_delta = -PAN_GAIN * offset_x
                        else:
                            pan_delta = PAN_GAIN * offset_x
                        pan_delta = max(
                            -self.max_track_delta,
                            min(self.max_track_delta, pan_delta),
                        )
                        self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + pan_delta)))
                        mode = "kf_track"
            else:
                self.tracking_locked = False
                self.last_valid_ball = None
                self.ema_cx = None
                self.ema_cy = None
                self.last_radius = None
                self.kf.reset()
                self.kf_pred = None
                if has_rotation:
                    self.pan = max(PAN_MIN, min(PAN_MAX, int(self.pan + rotation_ff)))
                    mode = "ff_hold"
                else:
                    near_center = abs(self.pan - PAN_CENTER) <= 3
                    if self.sweep_enabled and near_center:
                        self.pan += self.sweep_step * self.sweep_dir
                        if self.pan >= PAN_MAX:
                            self.pan = PAN_MAX
                            self.sweep_dir = -1
                        elif self.pan <= PAN_MIN:
                            self.pan = PAN_MIN
                            self.sweep_dir = 1
                        mode = "sweep"
                    else:
                        alpha = self._recenter_alpha()
                        self.pan = recenter_step(self.pan, PAN_CENTER, alpha)
                        self.tilt = recenter_step(self.tilt, TILT_CENTER, alpha)
                        self.pan = max(PAN_MIN, min(PAN_MAX, self.pan))
                        self.tilt = max(0, min(180, self.tilt))
                        mode = "recenter"

        return {
            "detected": detected,
            "mode": mode,
            "reject_reason": reject_reason,
            "pan": self.pan,
            "tilt": self.tilt,
            "tracking_locked": self.tracking_locked,
            "ema_cx": self.ema_cx,
            "ema_cy": self.ema_cy,
        }


# ── Servo tracking test (--test-servo) ───────────────────────────────────────


def run_diag_servos(sbus):
    move_ms = 700
    pause_sec = 1.0
    pan_left_nominal = max(PAN_MIN, PAN_CENTER - 60)
    pan_right_nominal = min(PAN_MAX, PAN_CENTER + 60)
    tilt_up_nominal = min(SERVO_MAX_ANGLE, TILT_CENTER + 50)
    tilt_down_nominal = max(SERVO_MIN_ANGLE, TILT_CENTER - 50)

    if SERVO_PAN_INVERTED:
        pan_left = pan_right_nominal
        pan_right = pan_left_nominal
    else:
        pan_left = pan_left_nominal
        pan_right = pan_right_nominal

    if SERVO_TILT_INVERTED:
        tilt_up = tilt_down_nominal
        tilt_down = tilt_up_nominal
    else:
        tilt_up = tilt_up_nominal
        tilt_down = tilt_down_nominal

    log.info("=" * 55)
    log.info("[DIAG-SERVO] === DIAGNOSTICO DE SERVOS ===")
    log.info("[DIAG-SERVO] Movimiento 1: TILT arriba/abajo")
    log.info("[DIAG-SERVO] Movimiento 2: PAN izquierda/derecha")
    log.info(
        "[DIAG-SERVO] Inversion activa: pan=%s tilt=%s",
        SERVO_PAN_INVERTED,
        SERVO_TILT_INVERTED,
    )
    log.info("=" * 55)

    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Tilt arriba (tilt=%d)", tilt_up)
    sbus.burst(PAN_CENTER, tilt_up, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Tilt abajo (tilt=%d)", tilt_down)
    sbus.burst(PAN_CENTER, tilt_down, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Tilt arriba (tilt=%d)", tilt_up)
    sbus.burst(PAN_CENTER, tilt_up, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)
    log.info("[DIAG-SERVO] Tilt arriba (tilt=%d)", tilt_up)
    sbus.burst(PAN_CENTER, tilt_up, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Tilt arriba (tilt=%d)", tilt_up)
    sbus.burst(PAN_CENTER, tilt_up, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(pause_sec)

    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Pan izquierda (pan=%d)", pan_left)
    sbus.burst(pan_left, TILT_CENTER, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] Pan derecha (pan=%d)", pan_right)
    sbus.burst(pan_right, TILT_CENTER, move_ms, 0, 0, 0, 0)
    time.sleep(pause_sec)

    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(pause_sec)

    sbus.burst(PAN_CENTER, TILT_CENTER, 1000, 0, 0, 0, 0)
    time.sleep(pause_sec)

    log.info("[DIAG-SERVO] === FIN DIAGNOSTICO SERVOS ===")


def run_test_servos(sbus):
    cap, fw, exp = find_camera()
    if not cap:
        log.error("[TEST-SERVO] No se detecto camara. Abortando.")
        return

    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
    fcx = fw // 2
    fcy = fh // 2
    detector = create_detector()
    if hasattr(cap, "cap"):
        detector.set_exposure_cap(cap.cap)
    elif hasattr(cap, "set"):
        detector.set_exposure_cap(cap)

    log.info("=" * 55)
    log.info(
        "[TEST-SERVO] === SEGUIMIENTO YOLO (%.0fs) ===",
        TEST_SERVO_DURATION,
    )
    log.info("[TEST-SERVO] Resolucion: %dx%d center=(%d,%d)", fw, fh, fcx, fcy)
    log.info(
        "[TEST-SERVO] pan_gain=%.3f tilt_gain=%.3f max_delta=%d",
        PAN_GAIN,
        TILT_GAIN,
        MAX_TRACK_DELTA_PER_FRAME,
    )
    log.info(
        "[TEST-SERVO] inv_pan=%s inv_tilt=%s", SERVO_PAN_INVERTED, SERVO_TILT_INVERTED
    )
    log.info("=" * 55)

    sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
    time.sleep(0.5)

    pan = float(PAN_CENTER)
    tilt = float(TILT_CENTER)
    ema_cx = float(fcx)
    ema_cy = float(fcy)
    EMA_ALPHA = 0.4
    t0 = time.time()
    frame_count = 0
    detect_count = 0
    last_fps_log = t0

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= TEST_SERVO_DURATION:
                break

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue

            frame_count += 1
            ball = detector.detect(frame)

            if ball is not None:
                detect_count += 1
                cx, cy, r = ball

                ema_cx = ema_cx + EMA_ALPHA * (cx - ema_cx)
                ema_cy = ema_cy + EMA_ALPHA * (cy - ema_cy)

                offset_x = ema_cx - fcx
                offset_y = ema_cy - fcy

                if abs(offset_x) <= TRACK_DEADBAND_PX:
                    offset_x = 0

                if SERVO_PAN_INVERTED:
                    pan_delta = -PAN_GAIN * offset_x
                else:
                    pan_delta = PAN_GAIN * offset_x

                if SERVO_TILT_INVERTED:
                    tilt_delta = TILT_GAIN * offset_y
                else:
                    tilt_delta = -TILT_GAIN * offset_y

                pan_delta = max(
                    -MAX_TRACK_DELTA_PER_FRAME,
                    min(MAX_TRACK_DELTA_PER_FRAME, pan_delta),
                )
                tilt_delta = max(
                    -MAX_TRACK_DELTA_PER_FRAME,
                    min(MAX_TRACK_DELTA_PER_FRAME, tilt_delta),
                )

                pan = max(PAN_MIN, min(PAN_MAX, pan + pan_delta))
                tilt = max(0, min(180, tilt + tilt_delta))

                if frame_count % 10 == 0:
                    dbg = detector.get_debug_snapshot()
                    log.info(
                        "[TEST-SERVO] %.1fs | TRACK cx=%d cy=%d r=%.0f ema=(%.0f,%.0f) off=(%d,%d) delta=(%.2f,%.2f) pan=%.1f tilt=%.1f conf=%.2f",
                        elapsed,
                        cx,
                        cy,
                        r,
                        ema_cx,
                        ema_cy,
                        int(offset_x),
                        int(offset_y),
                        pan_delta,
                        tilt_delta,
                        pan,
                        tilt,
                        float(dbg.get("best_conf", 0.0)),
                    )
            else:
                if frame_count % 30 == 0:
                    log.info(
                        "[TEST-SERVO] %.1fs | LOST pan=%.1f tilt=%.1f",
                        elapsed,
                        pan,
                        tilt,
                    )

            sbus.burst(int(pan), int(tilt), 200, 0, 0, 0, 0)

            now = time.time()
            if now - last_fps_log >= 5.0:
                fps = frame_count / elapsed if elapsed > 0 else 0
                pct = detect_count / frame_count * 100 if frame_count > 0 else 0
                log.info(
                    "[TEST-SERVO] --- FPS: %.1f | Deteccion: %.0f%% (%d/%d) ---",
                    fps,
                    pct,
                    detect_count,
                    frame_count,
                )
                last_fps_log = now

    except KeyboardInterrupt:
        log.info("[TEST-SERVO] Interrumpido por usuario")
    finally:
        sbus.burst(PAN_CENTER, TILT_CENTER, 500, 0, 0, 0, 0)
        time.sleep(0.5)
        cap.release()
        total = time.time() - t0
        pct = detect_count / frame_count * 100 if frame_count > 0 else 0
        log.info("=" * 55)
        log.info("[TEST-SERVO] === FIN (%.1fs) ===", total)
        log.info(
            "[TEST-SERVO] Frames: %d | Detecciones: %d (%.0f%%) | pan=%.1f tilt=%.1f",
            frame_count,
            detect_count,
            pct,
            pan,
            tilt,
        )
        log.info("=" * 55)
