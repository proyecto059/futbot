from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "/home/raspi/futbot-v2/src")

from vision import HybridVisionService
from vision.commands.vision_config_command import VisionConfigCommand
from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.utils.vision_constants import (
    HSV_GOAL_BLUE_DARK_HI,
    HSV_GOAL_BLUE_DARK_LO,
    HSV_GOAL_BLUE_HI,
    HSV_GOAL_BLUE_LO,
    HSV_GOAL_YELLOW_HI,
    HSV_GOAL_YELLOW_LO,
    resolve_yolo_model_path,
)
from chase.attack_geometry import behind_ball_point, route_curve_points
from chase.ball_goal_controller import BallGoalController


def mask_bbox(mask: np.ndarray) -> list[int] | None:
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return [int(x), int(y), int(w), int(h)]


def _goal_masks(frame: np.ndarray) -> dict:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, HSV_GOAL_YELLOW_LO, HSV_GOAL_YELLOW_HI)
    blue = cv2.bitwise_or(
        cv2.inRange(hsv, HSV_GOAL_BLUE_LO, HSV_GOAL_BLUE_HI),
        cv2.inRange(hsv, HSV_GOAL_BLUE_DARK_LO, HSV_GOAL_BLUE_DARK_HI),
    )
    k = np.ones((5, 5), np.uint8)
    yellow = cv2.morphologyEx(cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    blue = cv2.morphologyEx(cv2.morphologyEx(blue, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    goals = GoalColorDetectionOperator().detect(frame)
    return {
        "yellow_mask": yellow,
        "blue_mask": blue,
        "yellow_bbox": goals.yellow_bbox,
        "blue_bbox": goals.blue_bbox,
    }


def _draw_bbox(img, bbox, color, label):
    if bbox is None:
        return
    x, y, w, h = bbox
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 2)
    cv2.putText(img, label, (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def _capture_score(snapshot: dict, target_key: str) -> tuple[int, float]:
    ball = snapshot.get("ball")
    goals = snapshot.get("goals", {})
    has_target = bool(goals.get(target_key, False))
    radius = float(ball.get("r", 0.0)) if ball else 0.0
    return (1 if ball else 0) + (1 if has_target else 0), radius


def is_better_capture(candidate: dict, current: dict | None, target_key: str) -> bool:
    if current is None:
        return True
    return _capture_score(candidate, target_key) > _capture_score(current, target_key)


def _attack_status(snapshot: dict, target_key: str, frame_width: int, frame_height: int) -> str:
    ball = snapshot.get("ball")
    if ball is None:
        return "SEARCH"

    goals = snapshot.get("goals", {})
    line = snapshot.get("line", {})
    command = BallGoalController(
        frame_width=float(frame_width),
        frame_height=float(frame_height),
    ).compute(
        ball_cx=float(ball["cx"]),
        ball_cy=ball.get("cy"),
        ball_r=float(ball["r"]),
        goal_cx=goals.get(f"{target_key}_cx"),
        goal_cy=goals.get(f"{target_key}_cy"),
        line_detected=bool(line.get("detected", False)),
    )
    return command.mode


def annotate_attack_geometry(frame: np.ndarray, snapshot: dict, masks: dict, target_key: str) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]
    ball = snapshot.get("ball")
    goals = snapshot.get("goals", {})
    cv2.line(img, (w // 2, 0), (w // 2, h - 1), (180, 180, 180), 1)
    blue_bbox = goals.get("blue_bbox")
    yellow_bbox = goals.get("yellow_bbox")
    _draw_bbox(img, blue_bbox, (255, 0, 0), "blue bbox")
    _draw_bbox(img, yellow_bbox, (0, 255, 255), "yellow bbox")

    target_cx = goals.get(f"{target_key}_cx")
    target_cy = goals.get(f"{target_key}_cy")
    if target_cx is not None:
        x = int(target_cx)
        cv2.line(img, (x, 0), (x, h - 1), (255, 255, 0), 1)
        cv2.putText(img, f"target {target_key}", (max(0, x - 45), 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)

    status = _attack_status(snapshot, target_key, frame_width=w, frame_height=h)
    if ball is not None:
        cx = int(ball["cx"])
        cy = int(ball["cy"])
        r = max(2, int(round(ball["r"])))
        cv2.circle(img, (cx, cy), r, (0, 80, 255), 2)
        cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), (0, 80, 255), 1)
        cv2.putText(img, f"ball {ball.get('source')} r={ball.get('r'):.1f}", (max(0, cx - 55), max(16, cy - r - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 80, 255), 1)
        if target_cx is not None:
            goal_y = int(target_cy) if target_cy is not None else h // 2
            goal_point = (int(target_cx), goal_y)
            behind_x, behind_y = behind_ball_point(
                cx,
                cy,
                float(target_cx),
                float(goal_y),
            )
            behind_point = (int(round(behind_x)), int(round(behind_y)))
            route_start = (w // 2, h - 1)
            curve_points = route_curve_points(route_start, behind_point)
            curve_pixels = np.array(
                [[(int(round(x)), int(round(y))) for x, y in curve_points]],
                dtype=np.int32,
            )
            cv2.polylines(
                img,
                curve_pixels,
                False,
                (255, 255, 0),
                4,
            )
            arrow_start = curve_pixels[0, max(0, len(curve_pixels[0]) - 3)]
            cv2.arrowedLine(
                img,
                tuple(int(v) for v in arrow_start),
                behind_point,
                (255, 255, 0),
                4,
                tipLength=0.35,
            )
            cv2.putText(
                img,
                "route",
                (max(0, route_start[0] - 28), min(h - 8, route_start[1] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 0),
                1,
            )
            cv2.arrowedLine(img, (cx, cy), goal_point, (0, 255, 0), 2, tipLength=0.18)
            cv2.putText(
                img,
                "push",
                (max(0, (cx + goal_point[0]) // 2 - 12), max(16, (cy + goal_point[1]) // 2 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
            )
            cv2.circle(img, behind_point, 6, (255, 0, 255), 2)
            cv2.putText(
                img,
                "behind",
                (max(0, behind_point[0] - 24), min(h - 8, behind_point[1] + 18)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 0, 255),
                1,
            )

    cv2.putText(img, f"status={status}", (8, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    return img


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def capture(out_root: Path, frames: int, target_key: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / f"attack_geometry_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    width = int(os.environ.get("VISION_CAMERA_WIDTH", "320"))
    height = int(os.environ.get("VISION_CAMERA_HEIGHT", "240"))
    config = VisionConfigCommand(camera_width=width, camera_height=height, yolo_model_path=resolve_yolo_model_path())
    vision = HybridVisionService(config=config)
    snapshot = {}
    frame = None
    best_snapshot = None
    best_frame = None
    try:
        time.sleep(1.0)
        for _ in range(frames):
            snapshot = vision.tick()
            frame = vision.last_frame()
            if frame is not None and is_better_capture(snapshot, best_snapshot, target_key):
                best_snapshot = snapshot
                best_frame = frame.copy()
            time.sleep(0.03)
    finally:
        vision.close()
    if frame is None:
        raise RuntimeError("No frame captured")
    if best_frame is not None and best_snapshot is not None:
        frame = best_frame
        snapshot = best_snapshot
    masks = _goal_masks(frame)
    annotated = annotate_attack_geometry(frame, snapshot, masks, target_key=target_key)
    cv2.imwrite(str(out_dir / "raw.jpg"), frame)
    cv2.imwrite(str(out_dir / "annotated.jpg"), annotated)
    _write_json(out_dir / "snapshot.json", {"snapshot": snapshot, "fallback_masks": {k: v for k, v in masks.items() if not k.endswith("_mask")}, "target_key": target_key})
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output")
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--target", choices=("blue", "yellow"), default="blue")
    args = parser.parse_args()
    out_dir = capture(Path(args.out), args.frames, args.target)
    print(out_dir, flush=True)


if __name__ == "__main__":
    main()
