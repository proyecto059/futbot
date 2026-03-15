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
        raw = self._session.run(None, {self._input_name: tensor})[0]  # (1, 300, 6)
        return self._parse_output(raw[0])  # (300, 6)

    def _parse_output(self, output: np.ndarray) -> list:
        """
        Formato con NMS integrado (Ultralytics end-to-end):
          output: (N, 6) — cada fila: [x1, y1, x2, y2, conf, class_id]
          Coords en píxeles del input (AI_INPUT_SIZE). Se escalan al frame original.

        NOTA: si tu modelo es de una sola clase (pelota), usa BALL_CLASS_ID=0 en config.py.
        """
        scale_x = FRAME_WIDTH / AI_INPUT_SIZE[1]
        scale_y = FRAME_HEIGHT / AI_INPUT_SIZE[0]
        results = []
        for det in output:
            x1, y1, x2, y2, conf, class_id = det
            if conf < AI_CONF_THRESHOLD:
                continue
            if int(class_id) != BALL_CLASS_ID:
                continue
            x1s = int(x1 * scale_x)
            y1s = int(y1 * scale_y)
            x2s = int(x2 * scale_x)
            y2s = int(y2 * scale_y)
            w = x2s - x1s
            h = y2s - y1s
            results.append({
                "cx": x1s + w // 2,
                "cy": y1s + h // 2,
                "w": w,
                "h": h,
                "conf": float(conf),
                "class_id": int(class_id),
            })
        return results
