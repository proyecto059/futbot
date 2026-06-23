"""Configuración global del robot — fuente única de verdad.

Todas las constantes que usa el proyecto están aquí. Sin imports de otros
módulos del proyecto. Sin dependencias de hardware.

La clase `Config` es un dataclass que agrupa parámetros de cámara, visión,
pipeline FSM, motores y servos. Se instancia una sola vez en `main.py` y se
pasa a todos los módulos por constructor (inyección manual, sin framework).

Además expone `CRC8_TABLE` y `crc8()` para checksums del protocolo UART de
motores.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

# ── CRC8 ────────────────────────────────────────────────────────────────────────

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
"""Tabla de lookup para CRC8 (polinomio 0x07).

Pre-calculada para checksums de paquetes UART sin costo en runtime.
Usada por `crc8()` y por `motors.py` para validar tramas binarias."""


def crc8(data: bytes) -> int:
    """Calcula el CRC8 de *data* usando la tabla de lookup pre-calculada.

    Polinomio: 0x07. El CRC8 se usa como byte final en cada trama del
    protocolo UART de motores (trama de servos cmd 0x04 y trama de motores
    cmd 0x03). Se calcula sobre los bytes desde `cmd` hasta el final del
    payload.

    Args:
        data: Secuencia de bytes sobre la cual calcular el checksum.

    Returns:
        Entero entre 0 y 255 representando el CRC8.
    """
    c = 0
    for b in data:
        c = CRC8_TABLE[c ^ b]
    return c


# ── Config dataclass ────────────────────────────────────────────────────────────

@dataclass
class Config:
    """Todas las constantes configurables del robot.

    Los valores por defecto están calibrados para:
    - Raspberry Pi 5 con cámara CSI IMX219
    - Driver de motores en /dev/ttyAMA0 a 1 MBaud
    - Pelota naranja sobre campo verde
    - Servos con rango 0-180° (PWM 500-2500µs)

    Se puede instanciar con overrides parciales:
        cfg = Config(chase_speed_base=100.0, yolo_backend="ncnn")
    """

    # ── Cámara ──────────────────────────────────────────────────────────────────

    camera_width: int = 320
    """Ancho de captura en píxeles."""

    camera_height: int = 240
    """Alto de captura en píxeles."""

    camera_fps: int = 30
    """Frames por segundo objetivo (depende del backend)."""

    camera_backend: str = "libcamera"
    """Backend preferido: "libcamera", "gstreamer" o "opencv"."""

    camera_exposure_default: int = 200
    """Exposición por defecto en unidades del backend."""

    camera_flip_horizontal: bool = False
    """Si es True, voltea el frame horizontalmente (espejo)."""

    # ── Visión — HSV pelota naranja ──────────────────────────────────────────────

    ball_hsv_lower: Tuple[int, int, int] = (0, 80, 80)
    """Límite inferior HSV para pelota naranja (H, S, V)."""

    ball_hsv_upper: Tuple[int, int, int] = (65, 255, 255)
    """Límite superior HSV para pelota naranja (H, S, V)."""

    ball_hsv_lower2: Tuple[int, int, int] = (168, 80, 80)
    """Segundo rango inferior HSV para rojos (hue wrap-around 168-179)."""

    ball_hsv_upper2: Tuple[int, int, int] = (179, 255, 255)
    """Segundo rango superior HSV para rojos."""

    ball_min_area: int = 30
    """Área mínima en píxeles² para considerar un contorno como pelota."""

    ball_min_radius: int = 4
    """Radio mínimo en píxeles del círculo envolvente de la pelota."""

    ball_close_radius: int = 60
    """Radio a partir del cual se considera que la pelota está muy cerca."""

    adaptive_min_circularity: float = 0.20
    """Circularidad mínima (0-1) para filtrar falsos positivos no redondos."""

    adaptive_max_radius: int = 150
    """Radio máximo permitido para un contorno de pelota."""

    hot_pixel_y_max: int = 60
    """Franja superior del frame a ignorar (píxeles), reduce ruido de techo/luz."""

    border_margin: int = 25
    """Margen en píxeles a ignorar en los 4 bordes del frame."""

    adaptive_hue_ema_alpha: float = 0.15
    """Factor alpha del filtro EMA para el tono (hue) adaptativo."""

    adaptive_reacquire_min_miss: int = 2
    """Frames consecutivos sin detección antes de re-adquirir."""

    adaptive_miss_reset_frames: int = 30
    """Frames sin detección tras los cuales se resetea el tracking adaptativo."""

    # ── Visión — HSV porterías ───────────────────────────────────────────────────

    goal_yellow_hsv_lower: Tuple[int, int, int] = (18, 130, 130)
    """Límite inferior HSV para portería amarilla."""

    goal_yellow_hsv_upper: Tuple[int, int, int] = (50, 255, 255)
    """Límite superior HSV para portería amarilla."""

    goal_blue_hsv_lower: Tuple[int, int, int] = (95, 180, 60)
    """Límite inferior HSV para portería azul."""

    goal_blue_hsv_upper: Tuple[int, int, int] = (140, 255, 255)
    """Límite superior HSV para portería azul."""

    goal_min_pixels: int = 120
    """Mínimo de píxeles para considerar que hay una portería visible."""

    goal_min_component_area: int = 500
    """Área mínima de componente conexo para validar una portería."""

    # ── Visión — Línea blanca ────────────────────────────────────────────────────

    line_white_hsv_lower: Tuple[int, int, int] = (0, 0, 190)
    """Límite inferior HSV para línea blanca (alta saturación de valor)."""

    line_white_hsv_upper: Tuple[int, int, int] = (180, 60, 255)
    """Límite superior HSV para línea blanca."""

    line_detect_min_pixels: int = 3000
    """Mínimo de píxeles blancos en el ROI para detectar línea."""

    line_detect_min_ratio: float = 0.035
    """Ratio mínimo de píxeles blancos / total en el ROI."""

    # ── Visión — YOLO ────────────────────────────────────────────────────────────

    yolo_imgsz: int = 320
    """Tamaño de entrada de la red YOLO (cuadrado, píxeles)."""

    yolo_conf_threshold: float = 0.40
    """Umbral de confianza mínimo para aceptar una detección YOLO."""

    yolo_ball_class_id: int = 0
    """ID de clase YOLO para la pelota."""

    yolo_robot_class_id: int = 4
    """ID de clase YOLO para otros robots."""

    yolo_model_path: str = "models/yoloe26n_v2/onnx/yoloe26n_v2.onnx"
    """Ruta relativa al modelo ONNX."""

    yolo_ncnn_model_dir: str = "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
    """Directorio del modelo NCNN (contiene .param y .bin)."""

    yolo_backend: str = "onnx"
    """Backend YOLO activo: "onnx", "ncnn" o "tensorrt"."""

    yolo_thread_sleep_sec: float = 0.001
    """Sleep entre iteraciones del hilo de inferencia YOLO."""

    # ── Pipeline — Persecución (CHASE) ──────────────────────────────────────────

    chase_speed_base: float = 80.0
    """Velocidad base de avance durante la persecución (0-255)."""

    chase_rot_gain: float = 0.8
    """Ganancia proporcional para el giro durante el servo visual."""

    chase_deadband_px: float = 16.0
    """Zona muerta en píxeles: error menor a esto no produce giro."""

    kick_radius_px: float = 50.0
    """Radio de pelota a partir del cual se activa patada directa (avance recto)."""

    chase_miss_secs: float = 0.8
    """Segundos sin ver la pelota antes de declarar pérdida y pasar a RECOVERY."""

    chase_blind_speed: float = 60.0
    """Velocidad de avance durante el escaneo ciego (pelota perdida recientemente)."""

    chase_blind_ms: int = 100
    """Duración de cada paso de escaneo ciego en milisegundos."""

    chase_blind_scan_secs: float = 0.2
    """Intervalo entre giros de escaneo ciego."""

    # ── Pipeline — Búsqueda (SEARCH) ────────────────────────────────────────────

    search_turn_speed: float = 255.0
    """Velocidad de giro durante la búsqueda rotacional (0-255)."""

    search_turn_ms: int = 250
    """Duración de cada paso de giro en búsqueda (milisegundos)."""

    search_scan_secs: float = 0.3
    """Intervalo entre giros de búsqueda (segundos)."""

    max_search_duration_ms: int = 5000
    """Duración máxima en búsqueda antes de cambiar de estrategia."""

    # ── Pipeline — Recuperación (RECOVERY) ──────────────────────────────────────

    recovery_reverse_speed: float = 110.0
    """Velocidad de retroceso durante la recuperación."""

    recovery_reverse_ms: int = 220
    """Duración del paso de retroceso en recuperación (ms)."""

    recovery_turn_speed: float = 115.0
    """Velocidad de giro durante la recuperación."""

    recovery_turn_ms: int = 180
    """Duración del paso de giro en recuperación (ms)."""

    recovery_max_steps: int = 5
    """Número máximo de pasos del plan de recuperación antes de volver a SEARCH."""

    # ── Motores — UART ───────────────────────────────────────────────────────────

    uart_port: str = "/dev/ttyAMA0"
    """Puerto serial UART del driver de motores en la Raspberry Pi 5."""

    uart_baud: int = 1000000
    """Velocidad de baudios del UART (1 MBaud)."""

    diff_cap: float = 250.0
    """Velocidad máxima absoluta por rueda (0-255). Satura el mapeo diferencial."""

    # ── Motores — Servos ─────────────────────────────────────────────────────────

    servo_pan_id: int = 2
    """ID del servo de paneo (horizontal) en el bus del driver."""

    servo_tilt_id: int = 1
    """ID del servo de inclinación (vertical) en el bus del driver."""

    servo_min_angle: float = 0.0
    """Ángulo mínimo permitido para cualquier servo (grados)."""

    servo_max_angle: float = 180.0
    """Ángulo máximo permitido para cualquier servo (grados)."""

    pan_center: float = 70.0
    """Ángulo neutro del servo de paneo (grados). Posición de reposo."""

    tilt_center: float = 45.0
    """Ángulo neutro del servo de inclinación (grados). Posición de reposo."""

    # ── Rutas ────────────────────────────────────────────────────────────────────

    models_dir: str = "models"
    """Directorio raíz de modelos de red neuronal."""

    def resolve_yolo_model_path(self) -> Path:
        """Devuelve la ruta absoluta al archivo .onnx del modelo YOLO.

        Usa `Path(yolo_model_path)` para resolver la ruta relativa al
        directorio de trabajo actual.

        Returns:
            Objeto Path apuntando al archivo .onnx.
        """
        return Path(self.yolo_model_path)

    def resolve_ncnn_model_dir(self) -> Path:
        """Devuelve la ruta absoluta al directorio del modelo NCNN.

        El directorio debe contener `model.ncnn.param` y `model.ncnn.bin`.

        Returns:
            Objeto Path apuntando al directorio del modelo NCNN.
        """
        return Path(self.yolo_ncnn_model_dir)
