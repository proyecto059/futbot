"""HILO 2 — Inferencia YOLO en un worker thread (ONNX Runtime).

Patrón productor-consumidor:
    - `submit(frame)`  → el caller deja el frame pendiente (reemplaza si había uno).
    - `_worker_loop`   → consume el pendiente, corre ONNX, guarda el resultado.
    - `get_latest_output()` → devuelve el ÚLTIMO resultado (last-known-good).

La inferencia toma ~30-60 ms por frame en la Raspberry Pi 5; correrla en el hilo
principal bajaría el FPS a 15-20. En este esquema el main loop puede correr a
30+ FPS mientras YOLO entrega "lo último que pudo procesar" (que el fusion
operator combina con la detección HSV fresca).

La salida cruda (raw bboxes) queda en `_latest_output`. El `YoloParserOperator`
la convierte a DTOs fuera de este worker para mantener el hilo liviano.
"""

from __future__ import annotations

import logging
import time
from threading import Lock, Thread
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from vision.utils.vision_constants import (
    YOLO_BALL_CLASS_ID,
    YOLO_CONF_THRESHOLD,
    YOLO_IMGSZ,
    YOLO_ROBOT_CLASS_ID,
    YOLO_THREAD_SLEEP_SEC,
)

log = logging.getLogger("turbopi.vision.yolo")


class YoloInferenceOperator:
    """Corre YOLO ONNX en un hilo dedicado y expone el último resultado."""

    def __init__(self, session: ort.InferenceSession) -> None:
        self._session = session
        self._input_name = session.get_inputs()[0].name

        self._lock = Lock()
        self._pending_frame: Optional[np.ndarray] = None
        # Raw output: lista de arrays (best_ball, robots, raw_count, best_ball_conf)
        # antes de parsear a DTOs. Contenido seguro de leer sin lock (se reemplaza atómicamente).
        self._latest_raw: dict = {
            "ball_bbox": None,  # (x1, y1, x2, y2, conf) o None
            "robot_bboxes": [],  # [(x1, y1, x2, y2, conf), ...]
            "frame_shape": None,  # (h, w) del frame que se procesó
            "ts": 0.0,
        }
        self._debug_snapshot: dict = {
            "detector": "yolo_threaded",
            "raw_detections": 0,
            "best_ball_conf": 0.0,
            "robot_count": 0,
            "inference_ms": 0.0,
        }

        self._running = False
        self._thread: Optional[Thread] = None

    # ── API pública ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Arranca el worker thread. Idempotente."""
        if self._running:
            return
        self._running = True
        self._thread = Thread(target=self._worker_loop, name="vision-yolo", daemon=True)
        self._thread.start()

    def submit(self, frame: np.ndarray) -> None:
        """Deja un frame pendiente para el próximo ciclo del worker.

        NON-BLOCKING. Si ya había un pendiente, se reemplaza — siempre
        procesamos el frame más reciente disponible.
        """
        with self._lock:
            self._pending_frame = frame

    def get_latest_output(self) -> dict:
        """Devuelve el último resultado crudo (copia defensiva)."""
        with self._lock:
            return {
                "ball_bbox": self._latest_raw.get("ball_bbox"),
                "robot_bboxes": list(self._latest_raw.get("robot_bboxes", [])),
                "frame_shape": self._latest_raw.get("frame_shape"),
                "ts": float(self._latest_raw.get("ts", 0.0)),
            }

    def get_debug_snapshot(self) -> dict:
        with self._lock:
            return dict(self._debug_snapshot)

    def close(self) -> None:
        """Detiene el worker."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ── Worker ────────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while self._running:
            # Toma el pendiente (si hay)
            with self._lock:
                frame = self._pending_frame
                self._pending_frame = None
            if frame is None:
                time.sleep(YOLO_THREAD_SLEEP_SEC)
                continue

            t0 = time.time()
            try:
                self._run_once(frame, t0)
            except Exception as exc:  # noqa: BLE001 — el worker no puede morir
                log.warning("YOLO inference error: %s", exc)
                with self._lock:
                    self._debug_snapshot["last_error"] = str(exc)

    def _run_once(self, frame: np.ndarray, t0: float) -> None:
        """Un ciclo de inferencia: blob → session.run → guarda raw output."""
        h, w = frame.shape[:2]

        # Preprocesado a (1, 3, IMGSZ, IMGSZ) con swapRB y normalización a [0,1]
        blob = cv2.dnn.blobFromImage(
            frame, 1.0 / 255.0, (YOLO_IMGSZ, YOLO_IMGSZ), swapRB=True
        ).astype(np.float32)
        outputs = self._session.run(None, {self._input_name: blob})
        predictions = outputs[0][0]

        scale_x = w / YOLO_IMGSZ
        scale_y = h / YOLO_IMGSZ

        ball_bbox = None
        best_ball_conf = 0.0
        robot_bboxes = []
        raw_count = 0

        # YOLO output: cada fila es (x1, y1, x2, y2, conf, cls_id)
        for pred in predictions:
            x1, y1, x2, y2, conf, cls_id = pred
            conf = float(conf)
            if conf < YOLO_CONF_THRESHOLD:
                continue
            cls_id = int(round(cls_id))
            x1 = float(x1) * scale_x
            y1 = float(y1) * scale_y
            x2 = float(x2) * scale_x
            y2 = float(y2) * scale_y
            raw_count += 1
            bbox_entry = (x1, y1, x2, y2, conf, cls_id)

            if cls_id == YOLO_BALL_CLASS_ID:
                if conf > best_ball_conf:
                    best_ball_conf = conf
                    ball_bbox = bbox_entry
            elif cls_id == YOLO_ROBOT_CLASS_ID:
                robot_bboxes.append(bbox_entry)

        robot_bboxes.sort(key=lambda r: r[4], reverse=True)
        inference_ms = (time.time() - t0) * 1000.0

        with self._lock:
            self._latest_raw = {
                "ball_bbox": ball_bbox,
                "robot_bboxes": robot_bboxes,
                "frame_shape": (h, w),
                "ts": time.time(),
            }
            self._debug_snapshot.update(
                {
                    "raw_detections": int(raw_count),
                    "best_ball_conf": float(best_ball_conf),
                    "robot_count": len(robot_bboxes),
                    "inference_ms": float(inference_ms),
                }
            )