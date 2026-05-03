#!/usr/bin/env python3
"""Debug script for the vision pipeline — validates FPS and ball detection.

Usage:
    uv run python debug_vision.py [--ticks N] [--save-frames]

Measures tick-to-tick FPS, ball detection rate (HSV/YOLO/cache breakdown),
YOLO inference time, goal/line detection, and optionally saves a debug frame
with bounding boxes drawn.
"""

import argparse
import logging
import statistics
import sys
import time

import cv2
import numpy as np

from vision.commands.detect_vision_command import DetectVisionCommand
from vision.hybrid_vision_service import HybridVisionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("debug_vision")


def _draw_ball(frame: np.ndarray, ball: dict) -> None:
    cx, cy, r = int(ball["cx"]), int(ball["cy"]), int(ball["r"])
    color = (0, 255, 0) if ball["source"] == "hsv" else (255, 0, 0)
    cv2.circle(frame, (cx, cy), int(r), color, 2)
    cv2.circle(frame, (cx, cy), 3, color, -1)
    label = f"{ball['source']} r={r:.0f}"
    if ball.get("conf"):
        label += f" conf={ball['conf']:.2f}"
    cv2.putText(
        frame,
        label,
        (cx - 40, cy - int(r) - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
    )


def run(ticks: int, save_frames: bool) -> None:
    log.info("Starting HybridVisionService...")
    try:
        vision = HybridVisionService()
    except Exception as exc:
        log.error("Failed to init vision: %s", exc)
        sys.exit(1)

    frame_width = vision.frame_width
    log.info("Camera ready (frame_width=%d)", frame_width)

    tick_times: list[float] = []
    ball_detected = 0
    ball_sources: dict[str, int] = {"hsv": 0, "yolo": 0, "cache": 0}
    ball_radii: list[float] = []
    ball_cxs: list[int] = []
    ball_cys: list[int] = []
    yolo_confs: list[float] = []
    yolo_ms: list[float] = []
    goal_yellow_count = 0
    goal_blue_count = 0
    line_count = 0
    robot_counts: list[int] = []
    capture_frames_start = 0
    best_debug_frame: np.ndarray | None = None
    best_debug_ball: dict | None = None
    best_debug_radius = 0.0

    warmup = 5
    log.info("Warming up (%d ticks)...", warmup)
    for _ in range(warmup):
        vision.tick(DetectVisionCommand(include_debug=False))
        time.sleep(0.01)

    snap0 = vision.tick(DetectVisionCommand(include_debug=True))
    capture_frames_start = snap0.get("debug", {}).get("frames_in", 0)

    log.info("Running %d ticks...", ticks)
    for i in range(ticks):
        t0 = time.perf_counter()
        snap = vision.tick(DetectVisionCommand(include_debug=True))
        dt = time.perf_counter() - t0
        tick_times.append(dt)

        ball = snap.get("ball")
        if ball is not None:
            ball_detected += 1
            src = ball.get("source", "?")
            if src in ball_sources:
                ball_sources[src] += 1
            ball_radii.append(ball["r"])
            ball_cxs.append(ball["cx"])
            ball_cys.append(ball["cy"])
            if ball.get("conf") and src == "yolo":
                yolo_confs.append(ball["conf"])

            if save_frames and ball["r"] > best_debug_radius:
                frame = vision.last_frame()
                if frame is not None:
                    best_debug_frame = frame.copy()
                    best_debug_ball = ball
                    best_debug_radius = ball["r"]

        goals = snap.get("goals", {})
        if goals.get("yellow"):
            goal_yellow_count += 1
        if goals.get("blue"):
            goal_blue_count += 1

        line = snap.get("line", {})
        if line.get("detected"):
            line_count += 1

        robots = snap.get("robots", [])
        robot_counts.append(len(robots))

        dbg = snap.get("debug", {})
        yolo_dbg = dbg.get("yolo", {})
        ms = yolo_dbg.get("inference_ms", 0.0)
        if ms > 0:
            yolo_ms.append(ms)

    snap_end = vision.tick(DetectVisionCommand(include_debug=True))
    capture_frames_end = snap_end.get("debug", {}).get(
        "frames_in", capture_frames_start
    )
    total_capture = capture_frames_end - capture_frames_start

    vision.close()

    fps_list = [1.0 / t for t in tick_times]
    avg_fps = statistics.mean(fps_list)
    min_fps = min(fps_list)
    max_fps = max(fps_list)
    p50_fps = statistics.median(fps_list)
    p95_fps = (
        statistics.quantiles(fps_list, n=20)[18] if len(fps_list) >= 20 else max_fps
    )

    print("\n" + "=" * 50)
    print("  VISION PIPELINE DEBUG RESULTS")
    print("=" * 50)
    print(f"  Ticks: {ticks} | Capture frames: {total_capture}")
    print()
    print("  --- FPS ---")
    print(f"  Avg: {avg_fps:.1f} | Min: {min_fps:.1f} | Max: {max_fps:.1f}")
    print(f"  P50: {p50_fps:.1f} | P95: {p95_fps:.1f}")
    print()
    print("  --- Ball Detection ---")
    pct = ball_detected / ticks * 100 if ticks else 0
    print(f"  Detected: {ball_detected}/{ticks} ({pct:.1f}%)")
    print(
        f"  By source: hsv={ball_sources['hsv']} yolo={ball_sources['yolo']} cache={ball_sources['cache']}"
    )
    if ball_radii:
        print(
            f"  Avg radius: {statistics.mean(ball_radii):.1f} px | "
            f"Min: {min(ball_radii):.0f} | Max: {max(ball_radii):.0f}"
        )
        print(
            f"  Avg position: cx={statistics.mean(ball_cxs):.0f} cy={statistics.mean(ball_cys):.0f}"
        )
    if yolo_confs:
        print(f"  YOLO avg conf: {statistics.mean(yolo_confs):.2f}")
    if yolo_ms:
        print(
            f"  YOLO avg inference: {statistics.mean(yolo_ms):.1f} ms | "
            f"Min: {min(yolo_ms):.1f} | Max: {max(yolo_ms):.1f}"
        )
    print()
    print("  --- Goals ---")
    print(f"  Yellow: {goal_yellow_count}/{ticks} | Blue: {goal_blue_count}/{ticks}")
    print()
    print("  --- Line ---")
    print(f"  Detected: {line_count}/{ticks}")
    print()
    print("  --- Robots ---")
    if robot_counts:
        print(
            f"  Avg per frame: {statistics.mean(robot_counts):.1f} | "
            f"Max: {max(robot_counts)}"
        )

    if save_frames and best_debug_frame is not None and best_debug_ball is not None:
        _draw_ball(best_debug_frame, best_debug_ball)
        path = "/tmp/futbot_debug_ball.jpg"
        cv2.imwrite(path, best_debug_frame)
        print(f"\n  Saved debug frame: {path}")
    elif save_frames:
        print("\n  No ball detected — no debug frame saved.")

    print("=" * 50)

    if ball_detected == 0:
        print("\n  WARNING: Ball was NOT detected in any tick!")
        print("  Check: orange ball in front of camera, good lighting")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug vision pipeline")
    parser.add_argument(
        "--ticks", type=int, default=100, help="Number of ticks (default: 100)"
    )
    parser.add_argument(
        "--save-frames",
        action="store_true",
        help="Save debug frame with detection overlay",
    )
    args = parser.parse_args()
    run(args.ticks, args.save_frames)


if __name__ == "__main__":
    main()