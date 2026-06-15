"""Backends YOLO para `src/vision` con prioridad NCNN -> ONNX."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

import cv2
import numpy as np

from vision.utils.vision_constants import (
    YOLO_BALL_CLASS_IDS,
    YOLO_IMGSZ,
    YOLO_ROBOT_CLASS_IDS,
    resolve_yolo_model_path,
    resolve_yolo_ncnn_model_dir,
)

YOLO_PRE_NMS_CONF_THRESHOLD = 0.001
YOLO_NMS_IOU_THRESHOLD = 0.45


class YoloBackend(Protocol):
    name: str

    def run(self, frame: np.ndarray) -> np.ndarray:
        """Returns rows shaped `(N, 6)` as x1, y1, x2, y2, conf, cls_id."""


def preprocess_yolo_frame(frame: np.ndarray, image_size: int = YOLO_IMGSZ) -> np.ndarray:
    resized = cv2.resize(frame, (image_size, image_size), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return np.ascontiguousarray(rgb.transpose(2, 0, 1).astype(np.float32) / 255.0)


class NcnnYoloBackend:
    name = "ncnn"
    image_size = YOLO_IMGSZ

    def __init__(self, model_dir: Path | None = None) -> None:
        self._model_dir = model_dir or resolve_yolo_ncnn_model_dir()
        self._param_path = self._model_dir / "model.ncnn.param"
        self._bin_path = self._model_dir / "model.ncnn.bin"
        if not self._param_path.exists() or not self._bin_path.exists():
            raise FileNotFoundError(
                f"NCNN model files not found: {self._param_path} / {self._bin_path}"
            )

        import ncnn

        self._ncnn = ncnn
        self._net = ncnn.Net()
        param_status = self._net.load_param(str(self._param_path))
        model_status = self._net.load_model(str(self._bin_path))
        if param_status not in (None, 0) or model_status not in (None, 0):
            raise RuntimeError(
                f"NCNN load failed: param={param_status} model={model_status}"
            )

    def run(self, frame: np.ndarray) -> np.ndarray:
        blob = preprocess_yolo_frame(frame, self.image_size)
        with self._net.create_extractor() as extractor:
            status = extractor.input("in0", self._ncnn.Mat(blob).clone())
            if status not in (None, 0):
                raise RuntimeError(f"NCNN input failed: status={status}")
            status, output = extractor.extract("out0")
            if status != 0:
                raise RuntimeError(f"NCNN extract failed: status={status}")
        return _as_detection_rows(np.asarray(output, dtype=np.float32))


class OnnxYoloBackend:
    name = "onnx"

    def __init__(self, session: object) -> None:
        self._session = session
        input_meta = session.get_inputs()[0]
        self._input_name = input_meta.name
        self.image_size = _model_image_size_from_shape(input_meta.shape)

    @classmethod
    def create(cls, model_path: Path | None = None) -> "OnnxYoloBackend":
        from vision.utils.onnx_session_factory import OnnxSessionFactory

        return cls(OnnxSessionFactory.create(model_path or resolve_yolo_model_path()))

    def run(self, frame: np.ndarray) -> np.ndarray:
        blob = preprocess_yolo_frame(frame, self.image_size)[None]
        output = self._session.run(None, {self._input_name: blob})[0]
        return _as_detection_rows(np.asarray(output, dtype=np.float32))


class YoloBackendFactory:
    @staticmethod
    def create(
        ncnn_factory: Callable[[], object] | None = None,
        onnx_factory: Callable[[], object] | None = None,
    ) -> object:
        make_ncnn = ncnn_factory or (lambda: NcnnYoloBackend())
        make_onnx = onnx_factory or (lambda: OnnxYoloBackend.create())
        try:
            return make_ncnn()
        except Exception as ncnn_exc:  # noqa: BLE001 - fallback should capture load issues.
            ncnn_reason = str(ncnn_exc)
        try:
            return make_onnx()
        except Exception as onnx_exc:  # noqa: BLE001 - report both backend failures.
            raise RuntimeError(f"NCNN: {ncnn_reason} | ONNX: {onnx_exc}") from onnx_exc


def _model_image_size_from_shape(shape: object) -> int:
    if isinstance(shape, (list, tuple)) and len(shape) >= 4:
        height, width = shape[-2:]
        if isinstance(height, int) and isinstance(width, int) and height == width:
            return int(height)
    return YOLO_IMGSZ


def _as_detection_rows(output: np.ndarray) -> np.ndarray:
    rows = np.asarray(output, dtype=np.float32)
    if rows.ndim == 3 and rows.shape[0] == 1:
        rows = rows[0]
    if rows.ndim == 2 and rows.shape[0] >= 6 and rows.shape[1] != 6:
        return _decode_yolov8_channels_first(rows)
    if rows.ndim == 1:
        rows = rows.reshape(1, -1)
    if rows.ndim > 2:
        rows = rows.reshape(-1, rows.shape[-1])
    return rows


def _decode_yolov8_channels_first(output: np.ndarray) -> np.ndarray:
    boxes = output[:4]
    class_count = max(YOLO_BALL_CLASS_IDS | YOLO_ROBOT_CLASS_IDS) + 1
    scores = output[4 : 4 + class_count]
    if scores.size == 0:
        return np.empty((0, 6), dtype=np.float32)

    class_ids = np.argmax(scores, axis=0).astype(np.float32)
    confidences = np.max(scores, axis=0)
    keep = confidences >= YOLO_PRE_NMS_CONF_THRESHOLD
    if not np.any(keep):
        return np.empty((0, 6), dtype=np.float32)

    cx, cy, width, height = boxes[:, keep]
    confidences = confidences[keep]
    class_ids = class_ids[keep]
    rows = np.stack(
        [
            cx - width / 2.0,
            cy - height / 2.0,
            cx + width / 2.0,
            cy + height / 2.0,
            confidences,
            class_ids,
        ],
        axis=1,
    ).astype(np.float32)
    return _nms_detection_rows(rows)


def _nms_detection_rows(
    rows: np.ndarray,
    iou_threshold: float = YOLO_NMS_IOU_THRESHOLD,
) -> np.ndarray:
    if rows.size == 0:
        return np.empty((0, 6), dtype=np.float32)

    kept = []
    groups = np.array([_semantic_group_id(class_id) for class_id in rows[:, 5]])
    for group_id in np.unique(groups):
        class_rows = rows[groups == group_id]
        order = np.argsort(-class_rows[:, 4])
        while order.size > 0:
            current_index = order[0]
            current = class_rows[current_index]
            kept.append(current)
            if order.size == 1:
                break
            rest = order[1:]
            ious = _bbox_iou(current[:4], class_rows[rest, :4])
            order = rest[ious <= iou_threshold]

    kept_rows = np.asarray(kept, dtype=np.float32).reshape(-1, 6)
    return kept_rows[np.argsort(-kept_rows[:, 4])]


def _semantic_group_id(class_id: float) -> int:
    rounded = int(round(float(class_id)))
    if rounded in YOLO_BALL_CLASS_IDS:
        return 0
    if rounded in YOLO_ROBOT_CLASS_IDS:
        return 1
    return 1000 + rounded


def _bbox_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    intersection = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)

    box_area = max(0.0, float(box[2] - box[0])) * max(0.0, float(box[3] - box[1]))
    boxes_area = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(
        0.0,
        boxes[:, 3] - boxes[:, 1],
    )
    union = box_area + boxes_area - intersection
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
