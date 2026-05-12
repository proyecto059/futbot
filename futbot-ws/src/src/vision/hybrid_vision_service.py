"""Fachada del pipeline de visión (punto de entrada único).

Este módulo NO contiene lógica de OpenCV ni de YOLO — solo orquesta operadores.
Se lee de arriba hacia abajo como una receta: "capturo frame → YOLO async →
HSV sync → fusión → JSON".

Dos hilos en segundo plano:
    HILO OPENCV → `FrameCaptureOperator`   (captura continua de frames)
    HILO YOLO   → `YoloInferenceOperator`  (inferencia ONNX)

El caller (FSM en `main.py`) invoca `tick()` en su loop y recibe un dict
JSON-serializable con ball / robots / goals / line / ts / debug.

Ejemplo:
    vision = HybridVisionService()
    try:
        while running:
            snap = vision.tick()
            # snap['ball'], snap['goals']['blue_cx'], snap['line']['detected'], ...
    finally:
        vision.close()
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from vision.commands.detect_vision_command import DetectVisionCommand
from vision.commands.vision_config_command import VisionConfigCommand
from vision.operators.ball_fusion_operator import BallFusionOperator
from vision.operators.frame_capture_operator import FrameCaptureOperator
from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from vision.operators.json_export_operator import JsonExportOperator
from vision.operators.white_line_detection_operator import WhiteLineDetectionOperator
from vision.operators.yolo_inference_operator import YoloInferenceOperator
from vision.operators.yolo_parser_operator import YoloParserOperator
from vision.utils.onnx_session_factory import OnnxSessionFactory


class HybridVisionService:
    """Pipeline híbrido de visión con dos hilos en segundo plano."""

    def __init__(self, config: Optional[VisionConfigCommand] = None) -> None:
        cfg = config or VisionConfigCommand.default()
        self._cfg = cfg

        # ── HILO 1: captura OpenCV (daemon thread) ──────────────────────
        self._capture = FrameCaptureOperator(
            width=cfg.camera_width,
            height=cfg.camera_height,
        )

        # ── HILO 2: inferencia YOLO (worker thread) ─────────────────────
        session = OnnxSessionFactory.create(cfg.yolo_model_path)
        self._yolo = YoloInferenceOperator(session)

        # ── Operadores puros (corren en el hilo del caller de `tick`) ───
        self._hsv_ball = HsvBallDetectionOperator()
        self._goals = GoalColorDetectionOperator()
        self._line = WhiteLineDetectionOperator()
        self._parser = YoloParserOperator()
        self._fusion = BallFusionOperator(cache_ttl=cfg.cache_ttl_sec)
        self._exporter = JsonExportOperator()

        # Inyecta el VideoCapture real al detector HSV para rampa de exposición
        self._hsv_ball.set_exposure_cap(self._capture.raw_cap)

        # Arranca los dos hilos
        self._capture.start()
        self._yolo.start()

    # ── Propiedades de conveniencia para el FSM ──────────────────────────

    @property
    def frame_width(self) -> int:
        """Ancho real del frame (tras resolver el backend de cámara)."""
        return self._capture.frame_width

    def last_frame(self) -> Optional[np.ndarray]:
        """Devuelve el último frame BGR capturado (o None si aún no hay).

        Útil para dump de debug a disco desde el caller sin exponer el operador.
        """
        frame_dto = self._capture.read_latest()
        return frame_dto.image if frame_dto is not None else None

    # ── Ciclo principal ──────────────────────────────────────────────────

    def tick(
        self,
        command: Optional[DetectVisionCommand] = None,
    ) -> dict:
        """Ejecuta un paso del pipeline y devuelve el snapshot JSON.

        El método es el núcleo del pipeline. Orden:
            1. Lee el último frame del hilo OpenCV (no bloqueante).
            2. Lo envía al hilo YOLO para que empiece a procesarlo.
            3. Corre HSV ball + goals + line en este mismo hilo (CPU liviano).
            4. Lee el ÚLTIMO resultado YOLO disponible (puede ser de un frame
               anterior — eso está bien, HSV tiene prioridad).
            5. Fusiona HSV > YOLO > caché.
            6. Ensambla y devuelve el dict final.
        """
        req = command or DetectVisionCommand()
        now_ts = req.now_ts if req.now_ts is not None else time.time()

        # 1. Último frame del hilo OpenCV
        frame_dto = self._capture.read_latest()
        if frame_dto is None:
            # Todavía no hay frame: devolvemos shape vacío para que el FSM no falle
            return self._exporter.empty(now_ts)
        frame = frame_dto.image

        # 2. Alimenta el hilo YOLO (non-blocking; reemplaza el pendiente anterior)
        self._yolo.submit(frame)

        # 3. Operadores HSV en este hilo
        hsv_ball = self._hsv_ball.detect(frame, now_ts)
        goals = self._goals.detect(frame)
        line = self._line.detect(frame)

        # 4. Último output del hilo YOLO (last-known-good, puede ser de hace ~30ms)
        yolo_raw = self._yolo.get_latest_output()
        yolo_ball, robots = self._parser.parse(yolo_raw)

        # 5. Fusión (HSV > YOLO > caché TTL)
        ball = self._fusion.merge(hsv_ball, yolo_ball, now_ts)

        # 6. Debug opcional
        debug = {}
        if req.include_debug and self._cfg.enable_debug:
            debug = {
                "frames_in": self._capture.frames_captured(),
                "yolo": self._yolo.get_debug_snapshot(),
                "hsv": self._hsv_ball.get_debug_snapshot(),
            }

        return self._exporter.build(
            ball=ball,
            robots=robots,
            goals=goals,
            line=line,
            ts=now_ts,
            debug=debug,
        )

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def close(self) -> None:
        """Detiene ambos hilos y libera la cámara. Idempotente."""
        self._yolo.close()
        self._capture.close()