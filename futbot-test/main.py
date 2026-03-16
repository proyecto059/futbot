"""
FutBotMX — main pipeline entry point.

Thread layout:
  CameraThread      → shared frame (25 FPS)
  Main loop         → HSV detect + Kalman + Tracker + Game Logic (~50 Hz)
  AIInferenceThread → YOLO26n INT8 on full frame (~15-20 FPS async)
  MotorController   → applied on each game logic decision
"""
import os
import time
import signal
import sys
import platform
import argparse
import collections

import cv2
import numpy as np

from camera import CameraThread
from detector import detect_ball, extract_roi, BallKalman
from tracker import BallTracker
from ai_inference import AIInferenceThread
from game_logic import decide_action, Action
from motor_control import MotorController
from config import TRACKER_REINIT_INTERVAL, AI_INPUT_SIZE, MODEL_PATH, KALMAN_RESET_AFTER_N_FRAMES


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", action="store_true", help="Open debug window (requires display)")
    args = parser.parse_args()

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
        motors.cleanup()
        if args.ui:
            cv2.destroyAllWindows()
        os._exit(0)  # guaranteed immediate exit (sys.exit can block in signal handlers)

    signal.signal(signal.SIGINT, _shutdown)

    frame_count = 0
    tracker_frame_counter = 0
    _no_ball_frames = 0
    last_radius: int | None = None
    _prev_hsv_detected = False
    t_start = time.monotonic()
    t_prev = t_start

    # Rolling windows for FPS and loop-time stats
    _loop_times: collections.deque = collections.deque(maxlen=100)
    _hsv_times: collections.deque = collections.deque(maxlen=100)

    print("[main] Pipeline started. Press Ctrl+C to stop.\n")

    _cam_timeouts = 0
    while True:
        if not cam.wait_for_frame(timeout=1.0):
            _cam_timeouts += 1
            if _cam_timeouts % 5 == 1:
                print(f"[camera] no frame for {_cam_timeouts}s — check source")
            continue
        _cam_timeouts = 0
        frame = cam.get_frame()
        if frame is None:
            continue

        t_now = time.monotonic()
        dt = t_now - t_prev
        t_prev = t_now
        _loop_times.append(dt)

        tracked = None  # reset each frame so stats line is always defined

        # 1. Fast HSV detection (timed)
        t_hsv = time.monotonic()
        detection = detect_ball(frame)
        _hsv_times.append(time.monotonic() - t_hsv)

        if detection is not None:
            _no_ball_frames = 0
            cx, cy, radius = detection
            last_radius = radius
            if not _prev_hsv_detected:
                print(f"[hsv] ball found @ ({cx},{cy}) r={radius}")
            _prev_hsv_detected = True
            # 2. Kalman update
            cx, cy = kalman.update(cx, cy)
            cx, cy = int(cx), int(cy)
            # 3. Re-init tracker periodically
            if tracker_frame_counter % TRACKER_REINIT_INTERVAL == 0:
                tracker.init(frame, cx, cy, radius)
            tracker_frame_counter += 1
            # 4. Tracker re-init handled; AI submit moved below HSV block
        else:
            if _prev_hsv_detected:
                print("[hsv] ball lost")
            _prev_hsv_detected = False
            _no_ball_frames += 1
            # 5. Fall back to tracker
            tracked = tracker.update(frame)
            if tracked is not None:
                cx, cy = tracked
                radius = last_radius
            else:
                cx, cy, radius = None, None, last_radius
            # Kalman prediction only (no measurement)
            if cx is None:
                if kalman._initialized:
                    pred_cx, pred_cy = kalman.predict()
                    cx, cy = int(pred_cx), int(pred_cy)
                else:
                    cx, cy = None, None  # truly unknown — don't pass garbage to game logic

        # 6. Fuse YOLO26n result if available (overrides HSV when AI has detection)
        ai.submit_frame(frame)   # always, independent of HSV
        ai_dets = ai.get_detections()
        if ai_dets:
            best = max(ai_dets, key=lambda d: d["conf"])
            print(f"[ai]  ball @ ({best['cx']},{best['cy']}) w={best['w']} h={best['h']} conf={best['conf']:.2f}")
            cx, cy = best["cx"], best["cy"]
            radius = max(best["w"], best["h"]) // 2
            last_radius = radius
            cx, cy = kalman.update(cx, cy)
            cx, cy = int(cx), int(cy)
            _no_ball_frames = 0

        # Reset Kalman only if no detection from ANY source (HSV or AI) for too long
        if _no_ball_frames >= KALMAN_RESET_AFTER_N_FRAMES:
            kalman.reset()

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

        # 9. Debug UI
        if args.ui:
            vis = frame.copy()
            # HSV detection: green circle (raw, before Kalman)
            if detection is not None:
                hx, hy, hr = detection
                cv2.circle(vis, (hx, hy), hr, (0, 255, 0), 2)
                cv2.putText(vis, "HSV", (hx - hr, max(hy - hr - 4, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
            # AI detections: yellow bounding boxes
            for det in ai_dets:
                x1 = det["cx"] - det["w"] // 2
                y1 = det["cy"] - det["h"] // 2
                x2 = det["cx"] + det["w"] // 2
                y2 = det["cy"] + det["h"] // 2
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(vis, f"AI {det['conf']:.2f}", (x1, max(y1 - 4, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
            # Final estimated ball position: white crosshair
            if cx is not None:
                cv2.drawMarker(vis, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 14, 1)
            # Status overlay
            src_lbl = "AI" if ai_dets else ("HSV" if detection else ("TRK" if tracked else "KLM"))
            cv2.putText(vis, f"{src_lbl} | {action.name} | ({cx},{cy})",
                        (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            cv2.imshow("FutBotMX", vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

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
