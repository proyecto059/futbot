# futbot-test/config.py

import os

# Camera
CAMERA_URL: str = os.getenv("CAMERA_URL", "http://192.168.4.1:81/stream")
USE_LOCAL_CAM: bool = os.getenv("USE_LOCAL_CAM", "false").lower() == "true"
LOCAL_CAM_ID: int   = int(os.getenv("LOCAL_CAM_ID", "0"))
FRAME_WIDTH = 320
FRAME_HEIGHT = 240

# HSV orange ball detection (reused from cam.py)
HSV_LOWER = (5, 120, 120)
HSV_UPPER = (20, 255, 255)
MIN_CONTOUR_AREA = 500
MIN_BALL_RADIUS = 10

# Adaptive illumination (LAB+CLAHE) — applied inside detect_ball()
CLAHE_ENABLED = True          # kill switch: set False to disable entirely
CLAHE_CLIP_LIMIT = 2.5        # contrast limit (2.0=soft, 3.0=aggressive, 4.0=max)
CLAHE_TILE_GRID = 8           # used as tileGridSize=(N,N) — do NOT pass scalar directly
CLAHE_BRIGHTNESS_THRESHOLD = 130  # apply CLAHE when np.mean(frame) < this

# Morphology kernels
MORPH_OPEN_SIZE = 5
MORPH_DILATE_SIZE = 7

# Kalman
KALMAN_PROCESS_NOISE = 1e-2
KALMAN_MEASUREMENT_NOISE = 1e-1
KALMAN_RESET_AFTER_N_FRAMES = 30  # reset if no detection for this many frames (~0.6s at 50Hz)

# ROI for AI (usado por HSV detector para recorte visual, no por YOLO26)
ROI_SIZE = 96          # 96x96 pixels
ROI_PADDING = 20       # extra padding around ball bbox

# ONNX model — YOLO26n INT8 exportado con export_model.py
MODEL_PATH = "model.onnx"
AI_THREADS = 4
AI_INPUT_SIZE = (320, 320)   # imgsz usado en export_model.py --imgsz 320
AI_CONF_THRESHOLD = 0.4      # confianza mínima para detección válida
AI_NMS_THRESHOLD = 0.45      # NMS IoU threshold (YOLO26 no tiene NMS interno)
BALL_CLASS_ID = 0            # Custom 2-class model: 0=ball, 1=robot

# Tracker
TRACKER_TYPE = "MOSSE"   # or "KCF"
TRACKER_REINIT_INTERVAL = 15  # re-init tracker every N frames

# GPIO motor pins (BCM numbering) — H-bridge DIR+PWM scheme (L298N or similar)
MOTOR_A_DIR = 2
MOTOR_A_PWM = 5
MOTOR_B_DIR = 4
MOTOR_B_PWM = 6
PWM_FREQ = 100   # Hz

# PID for direction control
PID_KP = 0.8
PID_KI = 0.01
PID_KD = 0.1
MAX_SPEED = 80   # 0-100 PWM duty cycle (matches Arduino constant)

# Game logic
FRAME_CENTER_X = FRAME_WIDTH // 2
FRAME_CENTER_Y = FRAME_HEIGHT // 2
DEAD_ZONE_X = 20    # pixels: no turn correction needed
CLOSE_RADIUS = 40   # pixels: ball is "close enough"
