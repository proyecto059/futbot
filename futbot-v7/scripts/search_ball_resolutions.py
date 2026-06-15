from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from vision import HybridVisionService
from vision.commands.vision_config_command import VisionConfigCommand
from vision.utils.vision_constants import resolve_yolo_model_path


DEFAULT_RESOLUTIONS = "320x240,424x240,512x384,640x480"
DEFAULT_FRAMES = 80


def parse_resolutions(value: str) -> list[tuple[int, int]]:
    resolutions: list[tuple[int, int]] = []
    for raw_part in value.split(","):
        part = raw_part.strip().lower()
        if not part:
            continue
        pieces = part.split("x")
        if len(pieces) != 2:
            raise ValueError(f"invalid resolution: {raw_part.strip()}")
        try:
            width = int(pieces[0])
            height = int(pieces[1])
        except ValueError as exc:
            raise ValueError(f"invalid resolution: {raw_part.strip()}") from exc
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid resolution: {raw_part.strip()}")
        resolutions.append((width, height))
    if not resolutions:
        raise ValueError("at least one resolution is required")
    return resolutions


def fps_from_times(frame_count: int, start: float, end: float) -> float:
    elapsed = float(end) - float(start)
    if elapsed <= 0.0:
        return 0.0
    return round(float(frame_count) / elapsed, 2)


def build_summary(
    mode: str,
    width: int,
    height: int,
    fps: float,
    records: list[dict],
    error: str | None = None,
) -> dict:
    summary = {
        "mode": mode,
        "width": int(width),
        "height": int(height),
        "fps": float(fps),
        "frames": len(records),
        "ball_count": sum(1 for record in records if record.get("ball") is not None),
        "blue_goal_count": sum(
            1 for record in records if record.get("goals", {}).get("blue")
        ),
        "yellow_goal_count": sum(
            1 for record in records if record.get("goals", {}).get("yellow")
        ),
        "line_count": sum(
            1 for record in records if record.get("line", {}).get("detected")
        ),
        "sources": {},
        "ball_samples": [],
        "error": error,
    }
    for record in records:
        ball = record.get("ball")
        if ball is None:
            continue
        source = ball.get("source", "unknown")
        summary["sources"][source] = summary["sources"].get(source, 0) + 1
        if len(summary["ball_samples"]) < 20:
            summary["ball_samples"].append(
                {
                    "i": record.get("i"),
                    "cx": ball.get("cx"),
                    "cy": ball.get("cy"),
                    "r": ball.get("r"),
                    "source": source,
                }
            )
    return summary


def _safe_name(mode: str, width: int, height: int) -> str:
    return f"{mode}_{width}x{height}"


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _annotate_pipeline_frame(frame, snap: dict):
    img = frame.copy()
    h, w = img.shape[:2]
    cv2.line(img, (w // 2, 0), (w // 2, h - 1), (255, 255, 255), 1)
    goals = snap.get("goals", {})
    line = snap.get("line", {})
    ball = snap.get("ball")

    if goals.get("blue_cx") is not None:
        x = int(goals["blue_cx"])
        cv2.line(img, (x, 0), (x, h - 1), (255, 0, 0), 2)
        cv2.putText(
            img,
            "blue",
            (max(0, x - 24), 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 0, 0),
            1,
        )
    if goals.get("yellow_cx") is not None:
        x = int(goals["yellow_cx"])
        cv2.line(img, (x, 0), (x, h - 1), (0, 255, 255), 2)
        cv2.putText(
            img,
            "yellow",
            (max(0, x - 30), 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )
    if line.get("detected") and line.get("cx") is not None:
        x = int(line["cx"])
        cv2.line(img, (x, h // 2), (x, h - 1), (255, 255, 255), 2)
        cv2.putText(
            img,
            "line",
            (max(0, x - 20), h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
        )
    if ball is not None:
        cx = int(ball["cx"])
        cy = int(ball["cy"])
        r = int(round(ball["r"]))
        label = "{} r={:.1f}".format(ball.get("source"), ball.get("r"))
        cv2.circle(img, (cx, cy), max(2, r), (0, 0, 255), 2)
        cv2.putText(
            img,
            label,
            (max(0, cx - 55), max(14, cy - r - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 255),
            1,
        )
    return img


def _annotate_raw_frame(frame, width: int, height: int, fps: float | None = None):
    img = frame.copy()
    label = f"raw {width}x{height}"
    if fps is not None:
        label += f" fps={fps:.1f}"
    cv2.putText(img, label, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return img


def _save_frame_pair(base_dir: Path, index: int, raw_frame, annotated_frame) -> None:
    cv2.imwrite(str(base_dir / f"raw_{index:03d}.jpg"), raw_frame)
    cv2.imwrite(str(base_dir / f"annotated_{index:03d}.jpg"), annotated_frame)


def run_pipeline_resolution(
    width: int,
    height: int,
    frames: int,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    config = VisionConfigCommand(
        camera_width=width,
        camera_height=height,
        yolo_model_path=resolve_yolo_model_path(),
    )
    service = HybridVisionService(config=config)
    error = None
    start = time.perf_counter()
    try:
        time.sleep(1.0)
        for i in range(frames):
            snap = service.tick()
            frame = service.last_frame()
            record = {
                "i": i,
                "ball": snap.get("ball"),
                "goals": snap.get("goals", {}),
                "line": snap.get("line", {}),
                "debug": snap.get("debug", {}),
            }
            records.append(record)
            if frame is not None:
                _save_frame_pair(out_dir, i, frame, _annotate_pipeline_frame(frame, snap))
            time.sleep(0.01)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        end = time.perf_counter()
        service.close()

    fps = fps_from_times(len(records), start, end)
    summary = build_summary("pipeline", width, height, fps, records, error=error)
    _write_json(out_dir / "records.json", records)
    _write_json(out_dir / "summary.json", summary)
    return summary


def _open_raw_opencv_capture(width: int, height: int):
    raw_device = os.environ.get("BALL_SEARCH_RAW_DEVICE", "0").strip()
    device: int | str = int(raw_device) if raw_device.isdigit() else raw_device
    cap = cv2.VideoCapture(device)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, "videocapture"
        cap.release()

    pipeline = (
        f"libcamerasrc ! video/x-raw,width={width},height={height},format=BGRx "
        "! videoconvert ! video/x-raw,format=BGR "
        "! appsink drop=1 max-buffers=2 sync=false"
    )
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if cap.isOpened():
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, "gstreamer"
        cap.release()
    return None, "unavailable"


def run_raw_resolution(
    width: int,
    height: int,
    frames: int,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    cap, backend = _open_raw_opencv_capture(width, height)
    error = None
    start = time.perf_counter()
    try:
        if cap is None:
            error = "raw OpenCV capture unavailable"
        else:
            for i in range(frames):
                ok, frame = cap.read()
                if not ok or frame is None:
                    records.append({"i": i, "ok": False, "backend": backend})
                    continue
                h, w = frame.shape[:2]
                record = {
                    "i": i,
                    "ok": True,
                    "backend": backend,
                    "frame_width": int(w),
                    "frame_height": int(h),
                    "ball": None,
                    "goals": {},
                    "line": {},
                }
                records.append(record)
                _save_frame_pair(out_dir, i, frame, _annotate_raw_frame(frame, width, height))
    finally:
        end = time.perf_counter()
        if cap is not None:
            cap.release()

    fps = fps_from_times(sum(1 for record in records if record.get("ok")), start, end)
    summary = build_summary("raw_opencv", width, height, fps, records, error=error)
    summary["backend"] = backend
    _write_json(out_dir / "records.json", records)
    _write_json(out_dir / "summary.json", summary)
    return summary


def run_search(resolutions: Iterable[tuple[int, int]], frames: int, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for width, height in resolutions:
        for mode, runner in (
            ("pipeline", run_pipeline_resolution),
            ("raw_opencv", run_raw_resolution),
        ):
            name = _safe_name(mode, width, height)
            print(f"=== {name} frames={frames} ===", flush=True)
            summary = runner(width, height, frames, output / name)
            summaries.append(summary)
            print(json.dumps(summary), flush=True)

    combined = {"output": str(output), "summaries": summaries}
    _write_json(output / "summary.json", combined)
    return combined


def main() -> int:
    resolutions = parse_resolutions(
        os.environ.get("BALL_SEARCH_RESOLUTIONS", DEFAULT_RESOLUTIONS)
    )
    frames = int(os.environ.get("BALL_SEARCH_FRAMES", str(DEFAULT_FRAMES)))
    output = Path(os.environ.get("BALL_SEARCH_OUTPUT", "output/resolution_search_1"))
    run_search(resolutions, frames, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
