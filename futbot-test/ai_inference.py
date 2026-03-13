"""
ONNX Runtime inference thread — YOLO26n INT8.
Input: full frame (any size — resized internally to AI_INPUT_SIZE).
Output: list of detections {"cx", "cy", "w", "h", "conf", "class_id"} in original frame coords.
Runs at ~15-20 FPS on RPi3.

YOLO26n output shape: (1, 84, N) where:
  - 84 = 4 coords (cx,cy,w,h normalized) + 80 COCO class scores
  - N = grid cells (2100 for 320x320 input)
NMS is applied manually since YOLO26 has no built-in NMS.
"""
import threading
import queue
import cv2
import numpy as np
from pathlib import Path
from config import (
    MODEL_PATH, AI_THREADS, AI_INPUT_SIZE,
    AI_CONF_THRESHOLD, AI_NMS_THRESHOLD, BALL_CLASS_ID,
    FRAME_WIDTH, FRAME_HEIGHT,
)


class AIInferenceThread:

    def __init__(self):
        self._input_q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=2)
        self._output_q: queue.Queue[list | None] = queue.Queue(maxsize=2)
        self._session = None
        self._input_name: str = ""
        self._running = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._available = False

    def start(self):
        self._load_model()
        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False
        self._input_q.put(None)
        self._thread.join(timeout=2.0)

    @property
    def available(self) -> bool:
        return self._available

    def submit_frame(self, frame: np.ndarray):
        """Non-blocking: drops frame if queue full (preserves real-time behavior)."""
        try:
            self._input_q.put_nowait(frame)
        except queue.Full:
            pass

    def get_detections(self) -> list:
        """Non-blocking: returns latest detections or [] if no new result."""
        try:
            return self._output_q.get_nowait() or []
        except queue.Empty:
            return []

    def _load_model(self):
        if not Path(MODEL_PATH).exists():
            print(f"[AI] model.onnx not found at {MODEL_PATH} — AI thread disabled")
            return
        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = AI_THREADS
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            opts.enable_mem_pattern = True
            opts.enable_cpu_mem_arena = True
            self._session = ort.InferenceSession(
                MODEL_PATH,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._input_name = self._session.get_inputs()[0].name
            self._available = True
            print(f"[AI] YOLO26n INT8 loaded — input: {self._input_name}")
        except Exception as e:
            print(f"[AI] Failed to load model: {e}")

    def _run(self):
        while self._running:
            frame = self._input_q.get()
            if frame is None:
                break
            if self._session is None:
                continue
            detections = self._infer(frame)
            try:
                self._output_q.put_nowait(detections)
            except queue.Full:
                pass

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        """BGR frame → NCHW float32 normalized to [0,1]."""
        h, w = AI_INPUT_SIZE
        resized = cv2.resize(frame, (w, h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = rgb.astype(np.float32) / 255.0
        return np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]  # 1,3,H,W

    def _infer(self, frame: np.ndarray) -> list:
        """
        Returns list of dicts filtered to BALL_CLASS_ID.
        Coordinates in pixels of original frame (FRAME_WIDTH x FRAME_HEIGHT).
        """
        tensor = self._preprocess(frame)
        raw = self._session.run(None, {self._input_name: tensor})[0]  # (1, 84, N)
        return self._parse_yolo26_output(raw[0])  # (84, N)

    def _parse_yolo26_output(self, output: np.ndarray) -> list:
        """
        output: (84, N) — YOLO26 no NMS output.
        84 = [cx, cy, w, h, class0_conf, ..., class79_conf] — normalized coords.
        Scales to FRAME_WIDTH x FRAME_HEIGHT.
        """
        preds = output.T  # (N, 84)
        boxes_xywh = preds[:, :4]
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confs = class_scores[np.arange(len(class_ids)), class_ids]

        mask = (class_ids == BALL_CLASS_ID) & (confs >= AI_CONF_THRESHOLD)
        filtered_boxes = boxes_xywh[mask]
        filtered_confs = confs[mask]

        if len(filtered_boxes) == 0:
            return []

        scale_x = FRAME_WIDTH / AI_INPUT_SIZE[1]
        scale_y = FRAME_HEIGHT / AI_INPUT_SIZE[0]
        nms_boxes = []
        nms_scores = []
        for box, conf in zip(filtered_boxes, filtered_confs):
            cx, cy, w, h = box
            cx_px = cx * AI_INPUT_SIZE[1] * scale_x
            cy_px = cy * AI_INPUT_SIZE[0] * scale_y
            w_px  = w  * AI_INPUT_SIZE[1] * scale_x
            h_px  = h  * AI_INPUT_SIZE[0] * scale_y
            x1 = int(cx_px - w_px / 2)
            y1 = int(cy_px - h_px / 2)
            nms_boxes.append([x1, y1, int(w_px), int(h_px)])
            nms_scores.append(float(conf))

        indices = cv2.dnn.NMSBoxes(nms_boxes, nms_scores, AI_CONF_THRESHOLD, AI_NMS_THRESHOLD)
        if len(indices) == 0:
            return []

        results = []
        for i in indices.flatten():
            x1, y1, w, h = nms_boxes[i]
            results.append({
                "cx": x1 + w // 2,
                "cy": y1 + h // 2,
                "w": w,
                "h": h,
                "conf": nms_scores[i],
                "class_id": BALL_CLASS_ID,
            })
        return results
