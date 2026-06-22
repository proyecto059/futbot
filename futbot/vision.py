"""Pipeline de vision — deteccion hibrida YOLO + HSV.

Clase Vision con metodo detect(frame) -> Detections.
Soporte multi-backend YOLO: ONNX, NCNN, TensorRT.
Fallback HSV para pelota naranja.
Deteccion de porterias por color y linea blanca del campo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from config import Config

log = logging.getLogger("futbot.vision")


# ── Dataclasses de deteccion ──────────────────────────────────────────────────

@dataclass
class Ball:
    """Deteccion de pelota con coordenadas normalizadas (0.0 a 1.0)."""
    x: float          # centro x normalizado
    y: float          # centro y normalizado
    radius: float     # radio normalizado
    confidence: float


@dataclass
class Goal:
    """Deteccion de porteria."""
    color: str        # "blue" | "yellow"
    x: float
    y: float


@dataclass
class WhiteLine:
    """Deteccion de linea blanca del campo."""
    detected: bool
    position: str     # "left" | "right" | "center"


@dataclass
class Detections:
    """Resultado unificado de deteccion."""
    ball: Ball | None = None
    goal: Goal | None = None
    white_line: WhiteLine | None = None
    ts: float = 0.0


# ── Clase Vision ──────────────────────────────────────────────────────────────

class Vision:
    """Pipeline hibrido de deteccion: YOLO + HSV + fusion."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._yolo = None
        self._last_yolo_output = None
        self._ball_cache: Optional[Ball] = None
        self._ball_cache_ts: float = 0.0
        self._cache_ttl: float = 0.5  # segundos

        # Intentar cargar backend YOLO
        self._init_yolo()

    def _init_yolo(self) -> None:
        """Inicializa el backend YOLO segun configuracion."""
        backend = self._cfg.yolo_backend
        try:
            if backend == "onnx":
                self._yolo = _YoloOnnxBackend(self._cfg)
            elif backend == "ncnn":
                self._yolo = _YoloNcnnBackend(self._cfg)
            elif backend == "tensorrt":
                self._yolo = _YoloTensorrtBackend(self._cfg)
            log.info("YOLO backend %s inicializado", backend)
        except Exception as e:
            log.warning("YOLO backend %s no disponible: %s. Solo HSV activo.", backend, e)
            self._yolo = None

    def detect(self, frame: np.ndarray) -> Detections:
        """Ejecuta el pipeline completo de deteccion sobre un frame.

        Orden:
          1. YOLO (si esta disponible) en este hilo
          2. HSV pelota (siempre, como fallback/refuerzo)
          3. HSV porterias
          4. HSV linea blanca
          5. Fusion de detecciones
        """
        now = time.time()
        h, w = frame.shape[:2]

        # 1. YOLO
        yolo_ball = None
        if self._yolo is not None:
            yolo_raw = self._yolo.infer(frame)
            yolo_ball = self._parse_yolo_ball(yolo_raw, w, h)

        # 2. HSV pelota
        hsv_ball = self._detect_hsv_ball(frame, w, h)

        # 3. HSV porterias
        goal = self._detect_goal(frame, w, h)

        # 4. HSV linea blanca
        line = self._detect_white_line(frame, w, h)

        # 5. Fusion (YOLO > HSV > cache)
        ball = self._fuse_ball(yolo_ball, hsv_ball, now)

        return Detections(ball=ball, goal=goal, white_line=line, ts=now)

    # ── YOLO ──────────────────────────────────────────────────────────────

    def _parse_yolo_ball(self, raw, w: int, h: int) -> Optional[Ball]:
        if raw is None or len(raw) == 0:
            return None
        for det in raw:
            cls_id = int(det[5]) if len(det) >= 6 else -1
            if cls_id == self._cfg.yolo_ball_class_id:
                x1, y1, x2, y2 = det[:4]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                rx = (x2 - x1) / 2  # radio en pixeles
                conf = float(det[4]) if len(det) >= 5 else 1.0
                if conf >= self._cfg.yolo_conf_threshold:
                    return Ball(
                        x=cx / w,
                        y=cy / h,
                        radius=rx / max(w, h),
                        confidence=conf,
                    )
        return None

    # ── HSV pelota naranja ────────────────────────────────────────────────

    def _detect_hsv_ball(self, frame: np.ndarray, w: int, h: int) -> Optional[Ball]:
        lo = np.array(self._cfg.ball_hsv_lower, dtype=np.uint8)
        hi = np.array(self._cfg.ball_hsv_upper, dtype=np.uint8)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lo, hi)
        # Segundo rango para rojos (hue wrap-around)
        lo2 = np.array(self._cfg.ball_hsv_lower2, dtype=np.uint8)
        hi2 = np.array(self._cfg.ball_hsv_upper2, dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lo2, hi2)
        mask = cv2.bitwise_or(mask, mask2)
        # Ignorar franja superior ruidosa
        mask[:self._cfg.hot_pixel_y_max, :] = 0
        # Ignorar bordes
        bm = self._cfg.border_margin
        mask[:bm, :] = 0
        mask[-bm:, :] = 0
        mask[:, :bm] = 0
        mask[:, -bm:] = 0
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self._cfg.ball_min_area:
                continue
            (cx, cy), radius = cv2.minEnclosingCircle(cnt)
            if radius < self._cfg.ball_min_radius:
                continue
            # Filtro de circularidad
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < self._cfg.adaptive_min_circularity:
                    continue
            return Ball(
                x=cx / w,
                y=cy / h,
                radius=radius / max(w, h),
                confidence=0.7,  # HSV tiene confianza fija
            )
        return None

    # ── HSV porterias ─────────────────────────────────────────────────────

    def _detect_goal(self, frame: np.ndarray, w: int, h: int) -> Optional[Goal]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # Buscar azul
        lo_b = np.array(self._cfg.goal_blue_hsv_lower, dtype=np.uint8)
        hi_b = np.array(self._cfg.goal_blue_hsv_upper, dtype=np.uint8)
        mask_b = cv2.inRange(hsv, lo_b, hi_b)
        blue_pixels = cv2.countNonZero(mask_b)
        if blue_pixels >= self._cfg.goal_min_pixels:
            moments = cv2.moments(mask_b)
            if moments["m00"] > 0:
                return Goal(color="blue", x=moments["m10"] / moments["m00"] / w,
                            y=moments["m01"] / moments["m00"] / h)
        # Buscar amarillo
        lo_y = np.array(self._cfg.goal_yellow_hsv_lower, dtype=np.uint8)
        hi_y = np.array(self._cfg.goal_yellow_hsv_upper, dtype=np.uint8)
        mask_y = cv2.inRange(hsv, lo_y, hi_y)
        yellow_pixels = cv2.countNonZero(mask_y)
        if yellow_pixels >= self._cfg.goal_min_pixels:
            moments = cv2.moments(mask_y)
            if moments["m00"] > 0:
                return Goal(color="yellow", x=moments["m10"] / moments["m00"] / w,
                            y=moments["m01"] / moments["m00"] / h)
        return None

    # ── HSV linea blanca ──────────────────────────────────────────────────

    def _detect_white_line(self, frame: np.ndarray, w: int, h: int) -> WhiteLine:
        # Solo inspeccionar el tercio inferior del frame
        roi = frame[int(h * 0.66):, :]
        roi_h, roi_w = roi.shape[:2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lo = np.array(self._cfg.line_white_hsv_lower, dtype=np.uint8)
        hi = np.array(self._cfg.line_white_hsv_upper, dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        white_pixels = cv2.countNonZero(mask)
        total = roi_w * roi_h
        ratio = white_pixels / total if total > 0 else 0
        if white_pixels < self._cfg.line_detect_min_pixels or ratio < self._cfg.line_detect_min_ratio:
            return WhiteLine(detected=False, position="center")
        # Determinar posicion: izquierda, centro o derecha
        left_half = mask[:, :roi_w // 2]
        right_half = mask[:, roi_w // 2:]
        left_count = cv2.countNonZero(left_half)
        right_count = cv2.countNonZero(right_half)
        if left_count > right_count * 1.5:
            position = "left"
        elif right_count > left_count * 1.5:
            position = "right"
        else:
            position = "center"
        return WhiteLine(detected=True, position=position)

    # ── Fusion de pelota ──────────────────────────────────────────────────

    def _fuse_ball(
        self, yolo_ball: Optional[Ball], hsv_ball: Optional[Ball], now: float
    ) -> Optional[Ball]:
        # YOLO tiene prioridad si esta disponible con confianza suficiente
        if yolo_ball is not None and yolo_ball.confidence >= self._cfg.yolo_conf_threshold:
            self._ball_cache = yolo_ball
            self._ball_cache_ts = now
            return yolo_ball
        # HSV como fallback
        if hsv_ball is not None:
            self._ball_cache = hsv_ball
            self._ball_cache_ts = now
            return hsv_ball
        # Usar cache si no expiro
        if self._ball_cache is not None and (now - self._ball_cache_ts) < self._cache_ttl:
            return self._ball_cache
        return None


# ── Backends YOLO ─────────────────────────────────────────────────────────────

class _YoloOnnxBackend:
    """Backend YOLO via ONNX Runtime."""

    def __init__(self, config: Config) -> None:
        import onnxruntime as ort
        model_path = str(config.resolve_yolo_model_path())
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray):
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        img = img.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        outputs = self._session.run(None, {"images": img})
        return self._process_output(outputs[0])

    def _process_output(self, output):
        if output is None:
            return None
        result = output[0] if len(output.shape) == 3 else output
        return result[result[:, 4] > 0.1] if len(result) > 0 else []


class _YoloNcnnBackend:
    """Backend YOLO via NCNN (optimizado para ARM en RPi)."""

    def __init__(self, config: Config) -> None:
        import ncnn
        model_dir = str(config.resolve_ncnn_model_dir())
        self._net = ncnn.Net()
        self._net.load_param(f"{model_dir}/model.ncnn.param")
        self._net.load_model(f"{model_dir}/model.ncnn.bin")
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray):
        import ncnn
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        mat = ncnn.Mat.from_pixels(img, ncnn.Mat.PixelType.PIXEL_BGR, self._imgsz, self._imgsz)
        mat.substract_mean_normalize([0, 0, 0], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return self._process_output(out)

    def _process_output(self, out):
        if out is None:
            return None
        data = np.array(out)
        return data[data[:, 4] > 0.1] if len(data) > 0 else []


class _YoloTensorrtBackend:
    """Backend YOLO via TensorRT."""

    def __init__(self, config: Config) -> None:
        raise NotImplementedError("TensorRT backend no implementado en esta version")

    def infer(self, frame: np.ndarray):
        return None
