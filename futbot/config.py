"""Configuración global del robot — fuente única de verdad.

Todas las constantes que usa el proyecto están aquí. Sin imports de otros
módulos del proyecto. Sin dependencias de hardware.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

# ── CRC8 ────────────────────────────────────────────────────────────────────────
# Tabla de lookup para CRC8 (polinomio 0x07). Pre-calculada para checksums
# de paquetes UART sin costo en runtime.
CRC8_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]


def crc8(data: bytes) -> int:
    """Calcula el CRC8 de *data* usando la tabla de lookup pre-calculada."""
    c = 0
    for b in data:
        c = CRC8_TABLE[c ^ b]
    return c


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Todas las constantes configurables del robot."""

    # Cámara
    camera_width: int = 320
    camera_height: int = 240
    camera_fps: int = 30
    camera_backend: str = "libcamera"  # libcamera | gstreamer | opencv
    camera_exposure_default: int = 200
    camera_flip_horizontal: bool = False

    # Visión — HSV pelota naranja
    ball_hsv_lower: Tuple[int, int, int] = (0, 80, 80)
    ball_hsv_upper: Tuple[int, int, int] = (65, 255, 255)
    ball_hsv_lower2: Tuple[int, int, int] = (168, 80, 80)
    ball_hsv_upper2: Tuple[int, int, int] = (179, 255, 255)
    ball_min_area: int = 30
    ball_min_radius: int = 4
    ball_close_radius: int = 60
    adaptive_min_circularity: float = 0.20
    adaptive_max_radius: int = 150
    hot_pixel_y_max: int = 60
    border_margin: int = 25
    adaptive_hue_ema_alpha: float = 0.15
    adaptive_reacquire_min_miss: int = 2
    adaptive_miss_reset_frames: int = 30

    # Visión — HSV goles
    goal_yellow_hsv_lower: Tuple[int, int, int] = (18, 130, 130)
    goal_yellow_hsv_upper: Tuple[int, int, int] = (50, 255, 255)
    goal_blue_hsv_lower: Tuple[int, int, int] = (95, 180, 60)
    goal_blue_hsv_upper: Tuple[int, int, int] = (140, 255, 255)
    goal_min_pixels: int = 120
    goal_min_component_area: int = 500

    # Visión — Línea blanca
    line_white_hsv_lower: Tuple[int, int, int] = (0, 0, 190)
    line_white_hsv_upper: Tuple[int, int, int] = (180, 60, 255)
    line_detect_min_pixels: int = 3000
    line_detect_min_ratio: float = 0.035

    # Visión — YOLO
    yolo_imgsz: int = 320
    yolo_conf_threshold: float = 0.40
    yolo_ball_class_id: int = 0
    yolo_robot_class_id: int = 4
    yolo_model_path: str = "models/yoloe26n_v2/onnx/yoloe26n_v2.onnx"
    yolo_ncnn_model_dir: str = "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
    yolo_backend: str = "onnx"  # onnx | ncnn | tensorrt
    yolo_thread_sleep_sec: float = 0.001

    # Pipeline — Persecución (CHASE)
    chase_speed_base: float = 80.0
    chase_rot_gain: float = 0.8
    chase_deadband_px: float = 16.0
    kick_radius_px: float = 50.0
    chase_miss_secs: float = 0.8
    chase_blind_speed: float = 60.0
    chase_blind_ms: int = 100
    chase_blind_scan_secs: float = 0.2

    # Pipeline — Búsqueda (SEARCH)
    search_turn_speed: float = 255.0
    search_turn_ms: int = 250
    search_scan_secs: float = 0.3
    max_search_duration_ms: int = 5000

    # Pipeline — Recuperación (RECOVERY)
    recovery_reverse_speed: float = 110.0
    recovery_reverse_ms: int = 220
    recovery_turn_speed: float = 115.0
    recovery_turn_ms: int = 180
    recovery_max_steps: int = 5

    # Motores — UART
    uart_port: str = "/dev/ttyAMA0"
    uart_baud: int = 1000000
    diff_cap: float = 250.0

    # Motores — Servos
    servo_pan_id: int = 2
    servo_tilt_id: int = 1
    servo_min_angle: float = 0.0
    servo_max_angle: float = 180.0
    pan_center: float = 70.0
    tilt_center: float = 45.0

    # Rutas
    models_dir: str = "models"

    def resolve_yolo_model_path(self) -> Path:
        return Path(self.yolo_model_path)

    def resolve_ncnn_model_dir(self) -> Path:
        return Path(self.yolo_ncnn_model_dir)
