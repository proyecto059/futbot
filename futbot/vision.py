"""Pipeline de vision — deteccion hibrida YOLO + HSV.

Clase Vision con metodo detect(frame) -> Detections.
Soporte multi-backend YOLO: ONNX, NCNN, TensorRT.
Fallback HSV para pelota naranja.
Deteccion de porterias por color y linea blanca del campo.

Dataclasses de salida:
    Ball      — pelota detectada (x, y, radius, confidence normalizados)
    Goal      — porteria detectada (color, x, y normalizados)
    WhiteLine — linea blanca del campo (detected, position)
    Detections — resultado unificado (ball + goal + white_line + timestamp)

Flujo de deteccion (en Vision.detect):
    1. YOLO inferencia (si backend disponible)
    2. HSV pelota naranja (siempre como fallback)
    3. HSV porterias (azul/amarillo)
    4. HSV linea blanca (tercio inferior del frame)
    5. Fusion: YOLO > HSV > cache TTL (0.5s)
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
    """Deteccion de pelota con coordenadas normalizadas (0.0 a 1.0).

    Atributos:
        x: Centro x normalizado (0 = borde izquierdo, 1 = borde derecho).
        y: Centro y normalizado (0 = borde superior, 1 = borde inferior).
        radius: Radio normalizado respecto a max(ancho, alto) del frame.
        confidence: Confianza de la deteccion (0.0 a 1.0). YOLO da el valor
            real, HSV asigna 0.7 fijo.
    """
    x: float
    y: float
    radius: float
    confidence: float


@dataclass
class Goal:
    """Deteccion de porteria.

    Atributos:
        color: "blue" para porteria azul, "yellow" para amarilla.
        x: Centro x normalizado de la masa de pixeles de color.
        y: Centro y normalizado de la masa de pixeles de color.
    """
    color: str
    x: float
    y: float


@dataclass
class WhiteLine:
    """Deteccion de linea blanca del campo en el tercio inferior del frame.

    Atributos:
        detected: True si hay suficiente masa de pixeles blancos.
        position: "left" si la linea esta a la izquierda, "right" si a la
            derecha, "center" si esta centrada o no es concluyente.
    """
    detected: bool
    position: str


@dataclass
class Detections:
    """Resultado unificado de deteccion de un frame.

    Agrupa todas las detecciones disponibles. Si un tipo de deteccion no
    esta disponible, su campo es None.

    Atributos:
        ball: Pelota detectada o None.
        goal: Porteria detectada o None.
        white_line: Linea blanca detectada o None.
        ts: Timestamp Unix de cuando se proceso el frame.
    """
    ball: Ball | None = None
    goal: Goal | None = None
    white_line: WhiteLine | None = None
    ts: float = 0.0


# ── Clase Vision ──────────────────────────────────────────────────────────────

class Vision:
    """Pipeline hibrido de deteccion: YOLO + HSV + fusion.

    Inicializa el backend YOLO segun configuracion. Si el backend falla
    (libreria no instalada, modelo no encontrado), opera solo con HSV.

    Mantiene una cache de pelota con TTL de 0.5s para suavizar detecciones
    intermitentes.

    Atributos:
        _cfg: Instancia de Config con todos los parametros.
        _yolo: Backend YOLO activo (o None si fallo).
        _ball_cache: Ultima pelota detectada (para cache TTL).
        _ball_cache_ts: Timestamp de la ultima deteccion cacheada.
        _cache_ttl: Tiempo de vida de la cache en segundos (0.5).
    """

    def __init__(self, config: Config) -> None:
        """Inicializa el pipeline de vision.

        Intenta cargar el backend YOLO especificado en config.yolo_backend.
        Si falla, registra un warning y continua solo con HSV.

        Args:
            config: Instancia de Config con parametros de vision.
        """
        self._cfg = config
        self._yolo = None
        self._ball_cache: Optional[Ball] = None
        self._ball_cache_ts: float = 0.0
        self._cache_ttl: float = 0.5

        self._init_yolo()

    def _init_yolo(self) -> None:
        """Inicializa el backend YOLO segun config.yolo_backend.

        Soporta "onnx", "ncnn" y "tensorrt". Si el backend lanza una
        excepcion (libreria faltante, modelo no encontrado), self._yolo
        queda en None y el sistema opera solo con HSV.
        """
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
        """Ejecuta el pipeline completo de deteccion sobre un frame BGR.

        Orden de ejecucion:
          1. YOLO — inferencia de red neuronal (si backend disponible)
          2. HSV pelota — segmentacion por color naranja (siempre)
          3. HSV porterias — deteccion de azul y amarillo
          4. HSV linea blanca — deteccion en tercio inferior
          5. Fusion — YOLO tiene prioridad, HSV es fallback, cache TTL

        Args:
            frame: Frame BGR como array numpy de shape (H, W, 3).

        Returns:
            Detections con todas las detecciones del frame.
        """
        now = time.time()
        h, w = frame.shape[:2]

        yolo_ball = None
        if self._yolo is not None:
            yolo_raw = self._yolo.infer(frame)
            yolo_ball = self._parse_yolo_ball(yolo_raw, w, h)

        hsv_ball = self._detect_hsv_ball(frame, w, h)
        goal = self._detect_goal(frame, w, h)
        line = self._detect_white_line(frame, w, h)
        ball = self._fuse_ball(yolo_ball, hsv_ball, now)

        return Detections(ball=ball, goal=goal, white_line=line, ts=now)

    # ── YOLO ──────────────────────────────────────────────────────────────

    def _parse_yolo_ball(self, raw, w: int, h: int) -> Optional[Ball]:
        """Parsea la salida cruda de YOLO buscando la pelota.

        Itera sobre las detecciones, filtra por class_id == ball_class_id
        y confianza >= yolo_conf_threshold. Convierte coordenadas de
        bounding box (x1,y1,x2,y2) a centro y radio normalizados.

        Args:
            raw: Array numpy de detecciones (N, 6) con formato
                 [x1, y1, x2, y2, confidence, class_id].
            w: Ancho del frame en pixeles.
            h: Alto del frame en pixeles.

        Returns:
            Ball normalizada o None si no hay deteccion valida.
        """
        if raw is None or len(raw) == 0:
            return None
        for det in raw:
            cls_id = int(det[5]) if len(det) >= 6 else -1
            if cls_id == self._cfg.yolo_ball_class_id:
                x1, y1, x2, y2 = det[:4]
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                rx = (x2 - x1) / 2
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
        """Detecta la pelota naranja por segmentacion de color HSV.

        Pipeline:
          1. Convertir BGR → HSV
          2. Aplicar dos mascaras de rango (cubre wrap-around del hue en rojos)
          3. Ignorar franja superior (hot_pixel_y_max) y bordes (border_margin)
          4. Encontrar contornos externos
          5. Filtrar por area minima, radio minimo y circularidad

        Args:
            frame: Frame BGR.
            w: Ancho del frame.
            h: Alto del frame.

        Returns:
            Ball con confianza fija 0.7, o None.
        """
        lo = np.array(self._cfg.ball_hsv_lower, dtype=np.uint8)
        hi = np.array(self._cfg.ball_hsv_upper, dtype=np.uint8)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lo, hi)

        lo2 = np.array(self._cfg.ball_hsv_lower2, dtype=np.uint8)
        hi2 = np.array(self._cfg.ball_hsv_upper2, dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lo2, hi2)
        mask = cv2.bitwise_or(mask, mask2)

        mask[:self._cfg.hot_pixel_y_max, :] = 0
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
            perimeter = cv2.arcLength(cnt, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter * perimeter)
                if circularity < self._cfg.adaptive_min_circularity:
                    continue
            return Ball(
                x=cx / w,
                y=cy / h,
                radius=radius / max(w, h),
                confidence=0.7,
            )
        return None

    # ── HSV porterias ─────────────────────────────────────────────────────

    def _detect_goal(self, frame: np.ndarray, w: int, h: int) -> Optional[Goal]:
        """Detecta porterias por color (azul y amarillo) en espacio HSV.

        Busca primero azul, luego amarillo. Para cada color, aplica mascara
        y verifica que la cantidad de pixeles supere goal_min_pixels.
        Calcula el centroide via momentos de la mascara.

        Args:
            frame: Frame BGR.
            w: Ancho del frame.
            h: Alto del frame.

        Returns:
            Goal con color y posicion normalizada, o None.
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        lo_b = np.array(self._cfg.goal_blue_hsv_lower, dtype=np.uint8)
        hi_b = np.array(self._cfg.goal_blue_hsv_upper, dtype=np.uint8)
        mask_b = cv2.inRange(hsv, lo_b, hi_b)
        blue_pixels = cv2.countNonZero(mask_b)
        if blue_pixels >= self._cfg.goal_min_pixels:
            moments = cv2.moments(mask_b)
            if moments["m00"] > 0:
                return Goal(color="blue", x=moments["m10"] / moments["m00"] / w,
                            y=moments["m01"] / moments["m00"] / h)

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
        """Detecta la linea blanca del campo en el tercio inferior del frame.

        Solo inspecciona el 33% inferior de la imagen (donde estaria la
        linea de banda). Aplica mascara de blanco (V alto, S bajo) y
        determina la posicion comparando densidad de pixeles entre la
        mitad izquierda y derecha.

        Args:
            frame: Frame BGR.
            w: Ancho del frame.
            h: Alto del frame.

        Returns:
            WhiteLine con detected=True y position si la linea es visible.
        """
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
        """Combina detecciones YOLO y HSV con prioridad y cache TTL.

        Prioridad: YOLO (si confianza suficiente) > HSV > cache TTL.
        Si ninguna fuente tiene deteccion y la cache expiro, devuelve None.

        Args:
            yolo_ball: Deteccion de YOLO (puede ser None).
            hsv_ball: Deteccion de HSV (puede ser None).
            now: Timestamp actual para TTL de cache.

        Returns:
            Ball fusionada o None.
        """
        if yolo_ball is not None and yolo_ball.confidence >= self._cfg.yolo_conf_threshold:
            self._ball_cache = yolo_ball
            self._ball_cache_ts = now
            return yolo_ball
        if hsv_ball is not None:
            self._ball_cache = hsv_ball
            self._ball_cache_ts = now
            return hsv_ball
        if self._ball_cache is not None and (now - self._ball_cache_ts) < self._cache_ttl:
            return self._ball_cache
        return None


# ── Backends YOLO ─────────────────────────────────────────────────────────────

class _YoloOnnxBackend:
    """Backend YOLO via ONNX Runtime.

    Usa onnxruntime.InferenceSession con CPUExecutionProvider.
    Espera un modelo que acepte entrada "images" con shape (1, 3, 320, 320)
    normalizada a [0, 1].

    Atributos:
        _session: InferenceSession de ONNX Runtime.
        _imgsz: Tamano de entrada de la red (cuadrado).
    """

    def __init__(self, config: Config) -> None:
        """Carga el modelo ONNX y crea la sesion de inferencia.

        Args:
            config: Instancia de Config con ruta del modelo y tamano.

        Raises:
            onnxruntime.capi.onnxruntime_pybind11_state.Fail: Si el modelo
                no existe o no es compatible.
        """
        import onnxruntime as ort
        model_path = str(config.resolve_yolo_model_path())
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Ejecuta inferencia YOLO sobre un frame BGR.

        Pipeline: resize → transpose (HWC→CHW) → add batch dim →
        normalize /255 → session.run → filtrar por confianza > 0.1

        Args:
            frame: Frame BGR de cualquier tamano.

        Returns:
            Array numpy (M, 6) con detecciones [x1,y1,x2,y2,conf,cls],
            o array vacio si no hay detecciones, o None si falla.
        """
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        img = img.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        outputs = self._session.run(None, {"images": img})
        return self._process_output(outputs[0])

    def _process_output(self, output) -> Optional[np.ndarray]:
        """Filtra la salida cruda de ONNX Runtime por confianza minima.

        Args:
            output: Tensor de salida de ONNX con shape (1, N, 6) o (N, 6).

        Returns:
            Array con detecciones de confianza > 0.1, o array vacio.
        """
        if output is None:
            return None
        result = output[0] if len(output.shape) == 3 else output
        return result[result[:, 4] > 0.1] if len(result) > 0 else []


class _YoloNcnnBackend:
    """Backend YOLO via NCNN (optimizado para ARM en Raspberry Pi).

    Usa ncnn.Net con aceleracion ARM NEON. Carga el modelo desde
    archivos .param y .bin.

    Atributos:
        _net: Red NCNN cargada.
        _imgsz: Tamano de entrada.
    """

    def __init__(self, config: Config) -> None:
        """Carga el modelo NCNN desde el directorio de modelos.

        Args:
            config: Instancia de Config con ruta del directorio NCNN.

        Raises:
            FileNotFoundError: Si model.ncnn.param o .bin no existen.
        """
        import ncnn
        model_dir = str(config.resolve_ncnn_model_dir())
        self._net = ncnn.Net()
        self._net.load_param(f"{model_dir}/model.ncnn.param")
        self._net.load_model(f"{model_dir}/model.ncnn.bin")
        self._imgsz = config.yolo_imgsz

    def infer(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Ejecuta inferencia YOLO via NCNN.

        Pipeline: resize → Mat.from_pixels (BGR) → normalize →
        extractor.input → extractor.extract → filtrar.

        Args:
            frame: Frame BGR.

        Returns:
            Array con detecciones filtradas, o array vacio.
        """
        import ncnn
        img = cv2.resize(frame, (self._imgsz, self._imgsz))
        mat = ncnn.Mat.from_pixels(img, ncnn.Mat.PixelType.PIXEL_BGR, self._imgsz, self._imgsz)
        mat.substract_mean_normalize([0, 0, 0], [1 / 255.0] * 3)
        ex = self._net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return self._process_output(out)

    def _process_output(self, out) -> Optional[np.ndarray]:
        """Filtra la salida cruda de NCNN por confianza minima.

        Args:
            out: Mat de salida de NCNN.

        Returns:
            Array numpy con detecciones de confianza > 0.1.
        """
        if out is None:
            return None
        data = np.array(out)
        return data[data[:, 4] > 0.1] if len(data) > 0 else []


class _YoloTensorrtBackend:
    """Backend YOLO via TensorRT (placeholder).

    No implementado. Reservado para futura aceleracion por GPU/NPU.
    """

    def __init__(self, config: Config) -> None:
        """Lanza NotImplementedError — backend no disponible.

        Args:
            config: Instancia de Config (ignorada).
        """
        raise NotImplementedError("TensorRT backend no implementado en esta version")

    def infer(self, frame: np.ndarray):
        """Stub de inferencia — siempre devuelve None.

        Args:
            frame: Frame BGR (ignorado).

        Returns:
            None.
        """
        return None
