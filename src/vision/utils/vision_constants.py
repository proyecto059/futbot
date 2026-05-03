"""Constantes del pipeline de visión.

Fuente ÚNICA de verdad para todos los parámetros usados por los operadores:
    - Tamaño de cámara y exposición
    - Rangos HSV (bola naranja, goles, línea blanca)
    - Umbrales de contorno / radio / área para detección de bola
    - Parámetros adaptativos (EMA de hue, reacquire, reset de miss)
    - Configuración YOLO (tamaño de entrada, clases, confianza)

`cam.py` re-exporta las constantes que necesite para hardware desde este módulo.
"""

from pathlib import Path

import numpy as np

# ── Cámara ───────────────────────────────────────────────────────────────────

CAMERA_WIDTH = 320
CAMERA_HEIGHT = 240
CAMERA_EXPOSURE_DEFAULT = 200
CAMERA_BRIGHTNESS = 0

# Rampa de exposición adaptativa (cuando hay muchos miss_streak de la bola)
EXPOSURE_MIN = 150
EXPOSURE_MAX = 450
EXPOSURE_ADJUST_EVERY = 10  # cada N frames

# ── HSV bola naranja ─────────────────────────────────────────────────────────

# Rango primario de naranja (hue cerca del rojo bajo)
HSV_LO = (0, 230, 20)
HSV_HI = (10, 255, 255)
# Rango secundario (hue cerca del rojo alto, el círculo HSV envuelve)
HSV_LO2 = (168, 230, 20)
HSV_HI2 = (179, 255, 255)

# ── Detección adaptativa de bola ─────────────────────────────────────────────

ADAPTIVE_ORANGE_HUE_MIN = 0
ADAPTIVE_ORANGE_HUE_MAX = 15
ADAPTIVE_MIN_CIRCULARITY = 0.20
ADAPTIVE_MAX_RADIUS = 150
ADAPTIVE_STRICT_BASE_MARGIN = 8
ADAPTIVE_HUE_EMA_ALPHA = 0.15
ADAPTIVE_RELAXED_RECENT_SEC = 1.2
ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES = 2
ADAPTIVE_MISS_RESET_FRAMES = 30

ADAPTIVE_SAT_LOW_LIGHT = 80
ADAPTIVE_CIRCULARITY_LOW_LIGHT = 0.40
ADAPTIVE_LOW_LIGHT_MIN_MISS_FRAMES = 3
ADAPTIVE_GAMMA_MAX = 1.5

ADAPTIVE_SAT_TIERS = {
    "very_low": (80, 80),
    "low": (120, 100),
    "medium": (160, 160),
}

BALL_MIN_AREA = 700
BALL_MIN_RADIUS = 15
BALL_CLOSE_RADIUS = 60

# Filtros de falsos positivos: ignora la franja superior ruidosa y bordes
HOT_PIXEL_Y_MAX = 82
BORDER_MARGIN = 25

# ── HSV goles ────────────────────────────────────────────────────────────────

HSV_GOAL_YELLOW_LO = np.array([20, 100, 100], dtype=np.uint8)
HSV_GOAL_YELLOW_HI = np.array([40, 255, 255], dtype=np.uint8)
HSV_GOAL_BLUE_LO = np.array([100, 150, 50], dtype=np.uint8)
HSV_GOAL_BLUE_HI = np.array([130, 255, 255], dtype=np.uint8)
GOAL_MIN_PIXELS = 120

# ── HSV línea blanca (ROI inferior del frame) ────────────────────────────────

HSV_WHITE_LO = np.array([0, 0, 220], dtype=np.uint8)
HSV_WHITE_HI = np.array([180, 30, 255], dtype=np.uint8)
LINE_DETECT_MIN_PIXELS = 4000

# ── YOLO (ONNX) ──────────────────────────────────────────────────────────────

YOLO_IMGSZ = 320
YOLO_BALL_CLASS_ID = 0
YOLO_ROBOT_CLASS_ID = 1
YOLO_CONF_THRESHOLD = 0.35
YOLO_THREAD_SLEEP_SEC = 0.001
YOLO_INTRA_OP_THREADS = 4
YOLO_INTER_OP_THREADS = 1

# ── Fusión de detección de bola ──────────────────────────────────────────────

BALL_FUSION_CACHE_TTL_SEC = 0.5


def resolve_yolo_model_path() -> Path:
    """Busca `model.onnx` en la raíz del proyecto; si no, en `test-robot/`.

    Devuelve un `Path` aunque el archivo no exista: la validación se hace en
    `OnnxSessionFactory.create` para permitir mensajes de error específicos.
    """
    project_root = Path(__file__).resolve().parents[2]
    root_path = project_root / "model.onnx"
    if root_path.exists():
        return root_path
    return project_root / "test-robot" / "model.onnx"