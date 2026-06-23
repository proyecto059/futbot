#!/usr/bin/env python3
"""Measure camera sharpness and save the sharpest captured frame."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analyze_image import BLURRY_SHARPNESS_THRESHOLD, compute_frame_sharpness
from vision.utils.vision_constants import CAMERA_HEIGHT, CAMERA_WIDTH

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "focus_best.png"
DEFAULT_DIAGNOSTIC_CROP_SIZE = 640
DEFAULT_LARGE_CENTER_CROP_SIZE = 1024


@dataclass(frozen=True)
class FocusSample:
    index: int
    frame: np.ndarray
    sharpness: float


def collect_focus_samples(
    sample_count: int,
    interval_sec: float,
    timeout_sec: float = 5.0,
    width: int = CAMERA_WIDTH,
    height: int = CAMERA_HEIGHT,
    sharpness: float | None = None,
    noise_reduction_mode: str | None = None,
    exposure_us: int | None = None,
    analogue_gain: float | None = None,
    capture_factory: Callable[..., object] | None = None,
) -> list[FocusSample]:
    from vision.operators.frame_capture_operator import FrameCaptureOperator

    factory = capture_factory or FrameCaptureOperator
    capture = factory(
        width=width,
        height=height,
        sharpness=sharpness,
        noise_reduction_mode=noise_reduction_mode,
        exposure_us=exposure_us,
        analogue_gain=analogue_gain,
    )
    samples: list[FocusSample] = []
    deadline = time.time() + timeout_sec
    try:
        capture.start()
        while len(samples) < sample_count and time.time() < deadline:
            frame_dto = capture.read_latest()
            if frame_dto is None:
                time.sleep(min(interval_sec, 0.01))
                continue
            frame = frame_dto.image
            samples.append(
                FocusSample(
                    index=len(samples) + 1,
                    frame=frame,
                    sharpness=compute_frame_sharpness(frame),
                )
            )
            time.sleep(interval_sec)
    finally:
        capture.close()

    if len(samples) < sample_count:
        raise RuntimeError(
            f"captured {len(samples)} of {sample_count} requested focus samples"
        )
    return samples


def select_best_sample(samples: Sequence[FocusSample]) -> FocusSample:
    if not samples:
        raise ValueError("no focus samples captured")
    return max(samples, key=lambda sample: sample.sharpness)


def center_crop(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    frame_h, frame_w = frame.shape[:2]
    crop_w = min(width, frame_w)
    crop_h = min(height, frame_h)
    x0 = (frame_w - crop_w) // 2
    y0 = (frame_h - crop_h) // 2
    return frame[y0 : y0 + crop_h, x0 : x0 + crop_w].copy()


def _corner_crop(frame: np.ndarray, x0: int, y0: int, size: int) -> np.ndarray:
    frame_h, frame_w = frame.shape[:2]
    crop_w = min(size, frame_w)
    crop_h = min(size, frame_h)
    x = min(max(x0, 0), frame_w - crop_w)
    y = min(max(y0, 0), frame_h - crop_h)
    return frame[y : y + crop_h, x : x + crop_w].copy()


def build_focus_diagnostic_images(frame: np.ndarray) -> dict[str, np.ndarray]:
    frame_h, frame_w = frame.shape[:2]
    size = min(DEFAULT_DIAGNOSTIC_CROP_SIZE, frame_w, frame_h)
    large_size = min(DEFAULT_LARGE_CENTER_CROP_SIZE, frame_w, frame_h)
    return {
        "full": frame.copy(),
        "center_640": center_crop(frame, size, size),
        "center_1024": center_crop(frame, large_size, large_size),
        "corner_tl": _corner_crop(frame, 0, 0, size),
        "corner_tr": _corner_crop(frame, frame_w - size, 0, size),
        "corner_bl": _corner_crop(frame, 0, frame_h - size, size),
        "corner_br": _corner_crop(frame, frame_w - size, frame_h - size, size),
    }


def write_focus_diagnostics(sample: FocusSample, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    images = build_focus_diagnostic_images(sample.frame)
    metrics = {"best_sample": sample.index, "best_sharpness": sample.sharpness}
    for name, image in images.items():
        path = output_dir / f"{name}.png"
        if not cv2.imwrite(str(path), image):
            raise RuntimeError(f"no se pudo escribir diagnostico de enfoque: {path}")
        h, w = image.shape[:2]
        metrics[name] = {
            "width": int(w),
            "height": int(h),
            "sharpness": compute_frame_sharpness(image),
        }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_best_sample(sample: FocusSample, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), sample.frame):
        raise RuntimeError(f"no se pudo escribir frame de enfoque: {output_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--width", type=int, default=CAMERA_WIDTH)
    parser.add_argument("--height", type=int, default=CAMERA_HEIGHT)
    parser.add_argument("--sharpness", type=float, default=None)
    parser.add_argument(
        "--denoise",
        choices=("off", "fast", "high_quality", "minimal", "zsl"),
        default=None,
    )
    parser.add_argument("--exposure-us", type=int, default=None)
    parser.add_argument("--gain", type=float, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--diag-grid", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        samples = collect_focus_samples(
            sample_count=args.samples,
            interval_sec=args.interval,
            timeout_sec=args.timeout,
            width=args.width,
            height=args.height,
            sharpness=args.sharpness,
            noise_reduction_mode=args.denoise,
            exposure_us=args.exposure_us,
            analogue_gain=args.gain,
        )
        best = select_best_sample(samples)
        if args.diag_grid:
            output_dir = (args.output_dir or args.output.with_suffix(""))
            output_dir = output_dir.expanduser()
            write_focus_diagnostics(best, output_dir)
            output_path = output_dir
        else:
            output_path = args.output.expanduser()
            write_best_sample(best, output_path)
    except Exception as exc:  # noqa: BLE001 - CLI should print clean errors.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for sample in samples:
        print(f"sample {sample.index}: sharpness={sample.sharpness:.2f}")
    print(f"best_sample: {best.index}")
    print(f"best_sharpness: {best.sharpness:.2f}")
    print(f"frame_shape: {best.frame.shape[1]}x{best.frame.shape[0]}")
    print(f"output: {output_path}")
    if best.sharpness < BLURRY_SHARPNESS_THRESHOLD:
        print(f"warning: frame appears blurry (sharpness < {BLURRY_SHARPNESS_THRESHOLD:.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
