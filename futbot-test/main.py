"""
FutBotMX — main pipeline entry point.

Thread layout:
  CameraThread      → shared frame (25 FPS)
  Main loop         → HSV detect + Kalman + Tracker + Game Logic (~50 Hz)
  AIInferenceThread → YOLO26n INT8 on full frame (~15-20 FPS async)
  MotorController   → applied on each game logic decision
"""
import time
import signal
import sys
import platform
import collections

import cv2
import numpy as np

from camera import CameraThread
from detector import detect_ball, extract_roi, BallKalman
from tracker import BallTracker
from ai_inference import AIInferenceThread
from game_logic import decide_action, Action
from motor_control import MotorController
from config import TRACKER_REINIT_INTERVAL, AI_INPUT_SIZE, MODEL_PATH


def _log_startup(ai: AIInferenceThread):
    """Print hardware + runtime context on startup."""
    import onnxruntime as ort
    print("=" * 52)
    print("[main] FutBotMX Vision Pipeline")
    print(f"  Platform  : {platform.system()} {platform.machine()} ({platform.node()})")
    print(f"  Python    : {platform.python_version()}")
    print(f"  OpenCV    : {cv2.__version__}")
    print(f"  ORT       : {ort.__version__}")
    print(f"  AI model  : {MODEL_PATH}  ({'loaded' if ai.available else 'NOT FOUND — disabled'})")
    print(f"  AI input  : {AI_INPUT_SIZE[1]}x{AI_INPUT_SIZE[0]}")
    print("=" * 52)


def main():
    cam = CameraThread()
    kalman = BallKalman()
    tracker = BallTracker()
    ai = AIInferenceThread()
    motors = MotorController()

    motors.setup()
    cam.start()
    ai.start()

    _log_startup(ai)

    def _shutdown(sig, frame):
        elapsed = time.monotonic() - t_start
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"\n[main] Shutdown — {frame_count} frames in {elapsed:.1f}s ({avg_fps:.1f} FPS avg)")
        motors.stop()
        cam.stop()
        ai.stop()
        motors.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    frame_count = 0
    tracker_frame_counter = 0
    t_start = time.monotonic()
    t_prev = t_start

    # Rolling windows for FPS and loop-time stats
    _loop_times: collections.deque = collections.deque(maxlen=100)
    _hsv_times: collections.deque = collections.deque(maxlen=100)

    print("[main] Pipeline started. Press Ctrl+C to stop.\n")

    while True:
        frame = cam.get_frame()
        if frame is None:
            continue

        t_now = time.monotonic()
        dt = t_now - t_prev
        t_prev = t_now
        _loop_times.append(dt)

        # 1. Fast HSV detection (timed)
        t_hsv = time.monotonic()
        detection = detect_ball(frame)
        _hsv_times.append(time.monotonic() - t_hsv)

        if detection is not None:
            cx, cy, radius = detection
            # 2. Kalman update
            cx, cy = kalman.update(cx, cy)
            cx, cy = int(cx), int(cy)
            # 3. Re-init tracker periodically
            if tracker_frame_counter % TRACKER_REINIT_INTERVAL == 0:
                tracker.init(frame, cx, cy, radius)
            tracker_frame_counter += 1
            # 4. Submit full frame to YOLO26n AI thread (non-blocking)
            ai.submit_frame(frame)
        else:
            # 5. Fall back to tracker
            tracked = tracker.update(frame)
            if tracked is not None:
                cx, cy = tracked
                radius = None
            else:
                cx, cy, radius = None, None, None
            # Kalman prediction only (no measurement)
            if cx is None:
                pred_cx, pred_cy = kalman.predict()
                cx, cy = int(pred_cx), int(pred_cy)

        # 6. Fuse YOLO26n result if available (overrides HSV when AI has detection)
        ai_dets = ai.get_detections()
        if ai_dets:
            best = max(ai_dets, key=lambda d: d["conf"])
            cx, cy = best["cx"], best["cy"]
            radius = max(best["w"], best["h"]) // 2

        # 7. Game logic
        action = decide_action(cx, cy, radius)

        # 8. Motor output
        if action == Action.FORWARD:
            motors.forward()
        elif action == Action.TURN_RIGHT:
            motors.turn_right()
        elif action == Action.TURN_LEFT:
            motors.turn_left()
        elif action == Action.STOP:
            motors.stop()
        elif action == Action.SEARCH:
            motors.turn_right(speed=30)

        frame_count += 1

        # Stats log every 100 frames
        if frame_count % 100 == 0:
            avg_loop_ms = sum(_loop_times) / len(_loop_times) * 1000
            fps = 1000 / avg_loop_ms if avg_loop_ms > 0 else 0
            hsv_ms = sum(_hsv_times) / len(_hsv_times) * 1000
            elapsed = time.monotonic() - t_start
            source = "AI" if ai_dets else ("HSV" if detection else "TRACKER" if tracked else "KALMAN")
            print(
                f"[main] {frame_count:6d} frames | {elapsed:6.1f}s | "
                f"loop {avg_loop_ms:5.1f}ms ({fps:5.1f} FPS) | "
                f"HSV {hsv_ms:.1f}ms | "
                f"src={source} | action={action.name} | ball=({cx},{cy})"
            )


if __name__ == "__main__":
    main()
