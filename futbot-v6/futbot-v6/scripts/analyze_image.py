#!/usr/bin/env python3
"""Analyze a static image with the exported YOLO model.

The script prefers the Ultralytics PyTorch export, then falls back to ONNX and
NCNN when earlier backends fail. It prints detections and writes an annotated
copy of the input image.
"""

from __future__ import annotations

import argparse
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

NCNN_MODEL_DIR = PROJECT_ROOT / "models" / "ncnn" / "best_ncnn_model"
NCNN_PARAM_PATH = NCNN_MODEL_DIR / "model.ncnn.param"
NCNN_BIN_PATH = NCNN_MODEL_DIR / "model.ncnn.bin"
ONNX_MODEL_PATH = PROJECT_ROOT / "models" / "onnx" / "best.onnx"
PT_MODEL_PATH = PROJECT_ROOT / "models" / "yolo26n_futbot" / "best.pt"
DEFAULT_IMAGE_PATH = PROJECT_ROOT / "image.png"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "image_annotated.png"

MODEL_IMAGE_SIZE = 640
DEFAULT_CONF_THRESHOLD = 0.40
LOW_CONF_THRESHOLD = 0.001
CLASS_NAMES = {0: "ball", 1: "robot"}
CLASS_COLORS = {
    "ball": (0, 180, 255),
    "robot": (255, 80, 80),
}
CANDIDATE_COLOR = (180, 80, 255)


@dataclass(frozen=True)
class RunnerOutput:
    output: np.ndarray
    model_image_size: int = MODEL_IMAGE_SIZE
    class_names: dict[int, str] | None = None
    boxes_in_image_space: bool = False


@dataclass(frozen=True)
class BackendResult:
    backend: str
    model_path: Path
    output: np.ndarray
    model_image_size: int = MODEL_IMAGE_SIZE
    fallback_reason: str | None = None
    class_names: dict[int, str] | None = None
    boxes_in_image_space: bool = False


def preprocess_image(frame: np.ndarray, image_size: int = MODEL_IMAGE_SIZE) -> np.ndarray:
    resized = cv2.resize(frame, (image_size, image_size), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    blob = rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(blob)


def run_ncnn_inference(frame: np.ndarray) -> RunnerOutput:
    if not NCNN_PARAM_PATH.exists() or not NCNN_BIN_PATH.exists():
        raise FileNotFoundError(
            f"NCNN model files not found: {NCNN_PARAM_PATH} / {NCNN_BIN_PATH}"
        )

    import ncnn

    blob = preprocess_image(frame, MODEL_IMAGE_SIZE)[0]
    with ncnn.Net() as net:
        param_status = net.load_param(str(NCNN_PARAM_PATH))
        model_status = net.load_model(str(NCNN_BIN_PATH))
        if param_status not in (None, 0) or model_status not in (None, 0):
            raise RuntimeError(
                f"NCNN load failed: param={param_status} model={model_status}"
            )

        with net.create_extractor() as extractor:
            input_status = extractor.input("in0", ncnn.Mat(blob).clone())
            if input_status not in (None, 0):
                raise RuntimeError(f"NCNN input failed: status={input_status}")

            extract_status, out0 = extractor.extract("out0")
            if extract_status != 0:
                raise RuntimeError(f"NCNN extract failed: status={extract_status}")

    return RunnerOutput(np.array(out0), MODEL_IMAGE_SIZE)


def run_onnx_inference(frame: np.ndarray) -> RunnerOutput:
    if not ONNX_MODEL_PATH.exists():
        raise FileNotFoundError(f"ONNX model not found: {ONNX_MODEL_PATH}")

    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = 4
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    session = ort.InferenceSession(
        str(ONNX_MODEL_PATH), sess_options=opts, providers=["CPUExecutionProvider"]
    )
    input_meta = session.get_inputs()[0]
    image_size = _model_image_size_from_shape(input_meta.shape)
    blob = preprocess_image(frame, image_size)
    output = session.run(None, {input_meta.name: blob})[0]
    return RunnerOutput(np.asarray(output), image_size)


def run_pt_inference(frame: np.ndarray) -> RunnerOutput:
    if not PT_MODEL_PATH.exists():
        raise FileNotFoundError(f"PT model not found: {PT_MODEL_PATH}")

    from ultralytics import YOLO

    model = YOLO(str(PT_MODEL_PATH))
    class_names = {int(key): str(value) for key, value in model.names.items()}
    results = model.predict(
        source=frame,
        imgsz=MODEL_IMAGE_SIZE,
        conf=LOW_CONF_THRESHOLD,
        verbose=False,
    )
    if not results:
        return RunnerOutput(
            np.empty((0, 6), dtype=np.float32),
            MODEL_IMAGE_SIZE,
            class_names=class_names,
            boxes_in_image_space=True,
        )
    return RunnerOutput(
        ultralytics_result_to_rows(results[0]),
        MODEL_IMAGE_SIZE,
        class_names=class_names,
        boxes_in_image_space=True,
    )


def ultralytics_result_to_rows(result: object) -> np.ndarray:
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return np.empty((0, 6), dtype=np.float32)

    xyxy = _tensor_like_to_numpy(getattr(boxes, "xyxy", []))
    conf = _tensor_like_to_numpy(getattr(boxes, "conf", []))
    cls = _tensor_like_to_numpy(getattr(boxes, "cls", []))
    if xyxy.size == 0:
        return np.empty((0, 6), dtype=np.float32)

    conf = conf.reshape(-1, 1)
    cls = cls.reshape(-1, 1)
    return np.concatenate([xyxy.reshape(-1, 4), conf, cls], axis=1).astype(np.float32)


def run_with_fallback(
    frame: np.ndarray,
    pt_runner: Callable[[np.ndarray], RunnerOutput | np.ndarray] = run_pt_inference,
    ncnn_runner: Callable[[np.ndarray], RunnerOutput | np.ndarray] = run_ncnn_inference,
    onnx_runner: Callable[[np.ndarray], RunnerOutput | np.ndarray] = run_onnx_inference,
) -> BackendResult:
    try:
        pt_output = _normalize_runner_output(pt_runner(frame))
        return BackendResult(
            backend="pt",
            model_path=PT_MODEL_PATH,
            output=pt_output.output,
            model_image_size=pt_output.model_image_size,
            class_names=pt_output.class_names,
            boxes_in_image_space=pt_output.boxes_in_image_space,
        )
    except Exception as pt_exc:  # noqa: BLE001 - fallback should catch any PT failure.
        pt_reason = str(pt_exc)

    try:
        onnx_output = _normalize_runner_output(onnx_runner(frame))
        return BackendResult(
            backend="onnx",
            model_path=ONNX_MODEL_PATH,
            output=onnx_output.output,
            model_image_size=onnx_output.model_image_size,
            fallback_reason=pt_reason,
            class_names=onnx_output.class_names,
            boxes_in_image_space=onnx_output.boxes_in_image_space,
        )
    except Exception as onnx_exc:  # noqa: BLE001 - fallback should catch any ONNX failure.
        onnx_reason = str(onnx_exc)

    try:
        ncnn_output = _normalize_runner_output(ncnn_runner(frame))
        return BackendResult(
            backend="ncnn",
            model_path=NCNN_PARAM_PATH,
            output=ncnn_output.output,
            model_image_size=ncnn_output.model_image_size,
            fallback_reason=f"{pt_reason}; {onnx_reason}",
            class_names=ncnn_output.class_names,
            boxes_in_image_space=ncnn_output.boxes_in_image_space,
        )
    except Exception as ncnn_exc:  # noqa: BLE001 - report every backend failure.
        raise RuntimeError(
            f"PT: {pt_reason} | ONNX: {onnx_reason} | NCNN: {ncnn_exc}"
        ) from ncnn_exc


def run_vision_inference(frame: np.ndarray) -> BackendResult:
    from vision.utils.vision_constants import resolve_yolo_model_path, resolve_yolo_ncnn_model_dir
    from vision.utils.yolo_backend_factory import YoloBackendFactory

    backend = YoloBackendFactory.create()
    output = backend.run(frame)
    backend_name = str(getattr(backend, "name", "vision"))
    model_path = (
        resolve_yolo_ncnn_model_dir() / "model.ncnn.param"
        if backend_name == "ncnn"
        else resolve_yolo_model_path()
    )
    return BackendResult(
        backend=backend_name,
        model_path=model_path,
        output=output,
        model_image_size=int(getattr(backend, "image_size", MODEL_IMAGE_SIZE)),
    )


def capture_rpi_frame(
    capture_factory: Callable[[], object] | None = None,
    timeout_sec: float = 3.0,
    poll_sec: float = 0.02,
) -> np.ndarray:
    from vision.operators.frame_capture_operator import FrameCaptureOperator

    factory = capture_factory or FrameCaptureOperator
    capture = factory()
    deadline = time.time() + timeout_sec
    try:
        capture.start()
        while time.time() < deadline:
            frame_dto = capture.read_latest()
            if frame_dto is not None:
                return frame_dto.image
            time.sleep(poll_sec)
        raise RuntimeError(f"timed out waiting for Raspberry camera frame ({timeout_sec:.1f}s)")
    finally:
        capture.close()


def run_ncnn_runtime_only(
    frame: np.ndarray,
    backend_factory: Callable[[], object] | None = None,
) -> BackendResult:
    from vision.utils.vision_constants import resolve_yolo_ncnn_model_dir
    from vision.utils.yolo_backend_factory import NcnnYoloBackend

    try:
        backend = (backend_factory or NcnnYoloBackend)()
        output = backend.run(frame)
    except Exception as exc:  # noqa: BLE001 - rpi mode requires a clear NCNN error.
        raise RuntimeError(f"NCNN runtime failed: {exc}") from exc

    return BackendResult(
        backend="ncnn",
        model_path=resolve_yolo_ncnn_model_dir() / "model.ncnn.param",
        output=output,
        model_image_size=int(getattr(backend, "image_size", MODEL_IMAGE_SIZE)),
    )


def parse_detections(
    output: np.ndarray,
    image_shape: tuple[int, ...],
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    model_image_size: int = MODEL_IMAGE_SIZE,
    valid_conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    class_names: dict[int, str] | None = None,
    boxes_in_image_space: bool = False,
) -> list[dict]:
    rows = _as_detection_rows(output)
    image_h, image_w = image_shape[:2]
    scale_x = 1.0 if boxes_in_image_space else image_w / float(model_image_size)
    scale_y = 1.0 if boxes_in_image_space else image_h / float(model_image_size)
    names = class_names or CLASS_NAMES

    detections = []
    for row in rows:
        if row.shape[0] < 6:
            continue
        x1, y1, x2, y2, conf, cls_id = row[:6]
        conf = float(conf)
        if conf < conf_threshold:
            continue

        class_id = int(round(float(cls_id)))
        class_name = names.get(class_id, f"class_{class_id}")
        left, right = sorted((float(x1), float(x2)))
        top, bottom = sorted((float(y1), float(y2)))
        bbox = (
            _clip_int(round(left * scale_x), 0, image_w - 1),
            _clip_int(round(top * scale_y), 0, image_h - 1),
            _clip_int(round(right * scale_x), 0, image_w - 1),
            _clip_int(round(bottom * scale_y), 0, image_h - 1),
        )
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "conf": conf,
                "bbox": bbox,
                "kind": "detection" if conf >= valid_conf_threshold else "candidate",
            }
        )

    return sorted(detections, key=lambda det: det["conf"], reverse=True)


def draw_detections(frame: np.ndarray, detections: Sequence[dict]) -> np.ndarray:
    annotated = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        class_name = str(det["class_name"])
        conf = float(det["conf"])
        is_candidate = det.get("kind") == "candidate"
        color = CANDIDATE_COLOR if is_candidate else CLASS_COLORS.get(class_name, (230, 230, 230))
        label = f"LOW {class_name} {conf:.3f}" if is_candidate else f"{class_name} {conf:.3f}"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label_size, baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        )
        label_y = max(y1, label_size[1] + baseline + 2)
        cv2.rectangle(
            annotated,
            (x1, label_y - label_size[1] - baseline - 2),
            (x1 + label_size[0] + 4, label_y + baseline),
            color,
            thickness=-1,
        )
        cv2.putText(
            annotated,
            label,
            (x1 + 2, label_y - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return annotated


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--vision",
        action="store_true",
        help="use src/vision YOLO backend selection (NCNN then ONNX)",
    )
    parser.add_argument(
        "--rpi",
        action="store_true",
        help="capture one frame through src/vision Raspberry camera and require NCNN",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF_THRESHOLD,
        help="minimum confidence for real detections",
    )
    parser.add_argument(
        "--debug-low-conf",
        "--debug",
        dest="debug_low_conf",
        action="store_true",
        help="also show weak candidates below --conf",
    )
    parser.add_argument(
        "--low-conf",
        type=float,
        default=LOW_CONF_THRESHOLD,
        help="minimum confidence for --debug-low-conf candidates",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    output_path = args.output.expanduser()

    if args.rpi:
        image_path = Path("rpi-camera")
        try:
            frame = capture_rpi_frame()
        except Exception as exc:  # noqa: BLE001 - CLI should print a clean camera error.
            print(f"ERROR: no se pudo leer cámara RPi con src/vision: {exc}", file=sys.stderr)
            return 1
    else:
        image_path = args.image.expanduser()
        frame = cv2.imread(str(image_path))
        if frame is None:
            print(f"ERROR: no se pudo leer la imagen: {image_path}", file=sys.stderr)
            return 1

    try:
        if args.rpi:
            result = run_ncnn_runtime_only(frame)
        else:
            result = run_vision_inference(frame) if args.vision else run_with_fallback(frame)
    except Exception as exc:  # noqa: BLE001 - CLI should print a clean error.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    parse_threshold = float(args.low_conf if args.debug_low_conf else args.conf)
    detections = parse_detections(
        result.output,
        frame.shape,
        conf_threshold=parse_threshold,
        model_image_size=result.model_image_size,
        valid_conf_threshold=float(args.conf),
        class_names=result.class_names,
        boxes_in_image_space=result.boxes_in_image_space,
    )
    annotated = draw_detections(frame, detections)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), annotated):
        print(f"ERROR: no se pudo escribir la imagen: {output_path}", file=sys.stderr)
        return 1

    print(f"backend: {result.backend}")
    print(f"model: {result.model_path}")
    if result.fallback_reason:
        print(f"fallback_reason: {result.fallback_reason}")
    print(f"image: {image_path}")
    print(f"output: {output_path}")
    real_detections = [det for det in detections if det.get("kind") != "candidate"]
    candidates = [det for det in detections if det.get("kind") == "candidate"]
    print(f"detections: {len(real_detections)}")
    if args.debug_low_conf:
        print(f"low_conf_candidates: {len(candidates)}")
    for index, det in enumerate(detections, start=1):
        x1, y1, x2, y2 = det["bbox"]
        prefix = "LOW " if det.get("kind") == "candidate" else ""
        print(
            f"{index}. {prefix}{det['class_name']} conf={det['conf']:.3f} "
            f"bbox=({x1},{y1},{x2},{y2})"
        )
    return 0


def _normalize_runner_output(value: RunnerOutput | np.ndarray) -> RunnerOutput:
    if isinstance(value, RunnerOutput):
        return value
    if isinstance(value, np.ndarray):
        return RunnerOutput(value, MODEL_IMAGE_SIZE)
    return RunnerOutput(np.asarray(value), MODEL_IMAGE_SIZE)


def _model_image_size_from_shape(shape: Sequence[object]) -> int:
    if len(shape) >= 4:
        height, width = shape[-2:]
        if isinstance(height, int) and isinstance(width, int) and height == width:
            return int(height)
    return MODEL_IMAGE_SIZE


def _tensor_like_to_numpy(value: object) -> np.ndarray:
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy(), dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def _as_detection_rows(output: np.ndarray) -> np.ndarray:
    rows = np.asarray(output, dtype=np.float32)
    if rows.ndim == 3 and rows.shape[0] == 1:
        rows = rows[0]
    if rows.ndim == 2 and rows.shape[0] >= 6 and rows.shape[1] != 6:
        rows = rows.T
    if rows.ndim == 1:
        rows = rows.reshape(1, -1)
    if rows.ndim > 2:
        rows = rows.reshape(-1, rows.shape[-1])
    return rows


def _clip_int(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(value, max_value))


if __name__ == "__main__":
    raise SystemExit(main())
