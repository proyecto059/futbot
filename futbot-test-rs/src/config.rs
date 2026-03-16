//! Configuration — mirrors config.py exactly.
//!
//! Env vars (same as Python):
//!   CAMERA_URL        MJPEG stream URL   (default: http://192.168.4.1:81/stream)
//!   USE_LOCAL_CAM     "true" to use /dev/videoN
//!   LOCAL_CAM_ID      device index       (default: 0)

use std::env;

// ── Camera ───────────────────────────────────────────────────────────────────
pub const FRAME_WIDTH: i32 = 320;
pub const FRAME_HEIGHT: i32 = 240;

pub fn camera_url() -> String {
    env::var("CAMERA_URL").unwrap_or_else(|_| "http://192.168.4.1:81/stream".into())
}

pub fn use_local_cam() -> bool {
    env::var("USE_LOCAL_CAM")
        .map(|v| v.to_lowercase() == "true")
        .unwrap_or(false)
}

pub fn local_cam_id() -> i32 {
    env::var("LOCAL_CAM_ID")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0)
}

// ── HSV orange ball detection ─────────────────────────────────────────────────
pub const HSV_LOWER: [u8; 3] = [0, 60, 80];
pub const HSV_UPPER: [u8; 3] = [25, 255, 255];
pub const MIN_CONTOUR_AREA: f64 = 30.0;
pub const MIN_BALL_RADIUS: f32 = 5.0;
pub const MIN_CIRCULARITY: f64 = 0.70;

// ── CLAHE (adaptive illumination) ─────────────────────────────────────────────
pub const CLAHE_ENABLED: bool = true;
pub const CLAHE_CLIP_LIMIT: f64 = 2.5;
pub const CLAHE_TILE_GRID: i32 = 8;
pub const CLAHE_BRIGHTNESS_THRESHOLD: f64 = 300.0;

// ── Border rejection ──────────────────────────────────────────────────────────
pub const BORDER_REJECT_PX: i32 = 15;

// ── Morphology kernels ────────────────────────────────────────────────────────
pub const MORPH_OPEN_SIZE: i32 = 5;
pub const MORPH_DILATE_SIZE: i32 = 7;

// ── Kalman filter ─────────────────────────────────────────────────────────────
pub const KALMAN_PROCESS_NOISE: f32 = 1e-2;
pub const KALMAN_MEASUREMENT_NOISE: f32 = 1e-1;
pub const KALMAN_RESET_AFTER_N_FRAMES: u32 = 150;

// ── ROI ───────────────────────────────────────────────────────────────────────
pub const ROI_SIZE: i32 = 96;
pub const ROI_PADDING: i32 = 20;
pub const DETECT_ROI_SIZE: i32 = 120;

// ── AI cache ──────────────────────────────────────────────────────────────────
pub const AI_CACHE_MAX_AGE: u32 = 10;

// ── Partial contour detection ─────────────────────────────────────────────────
pub const PARTIAL_CIRCULARITY_MIN: f64 = 0.35;
pub const PARTIAL_ELLIPSE_RATIO: f32 = 0.75;

// ── Adaptive V floor ──────────────────────────────────────────────────────────
pub const HSV_ADAPTIVE_V_RATIO: f32 = 0.5;
pub const HSV_ADAPTIVE_V_PCTILE: f32 = 90.0;
pub const HSV_ADAPTIVE_V_MIN: i32 = 20;
pub const HSV_ADAPTIVE_S_SAMPLE: u8 = 80;

// ── Seed detector (tiny 8-15 px balls) ───────────────────────────────────────
pub const SEED_LOWER: [u8; 3] = [5, 150, 120];
pub const SEED_UPPER: [u8; 3] = [20, 255, 255];
pub const SEED_MIN_PIXELS: f64 = 3.0;
pub const SEED_MAX_AREA: f64 = 700.0;

// ── Temporal accumulator ──────────────────────────────────────────────────────
pub const ACCUM_DECAY: f32 = 0.85;
pub const ACCUM_THRESHOLD: f32 = 3.0;
pub const ACCUM_MIN_AREA: f64 = 2.0;

// ── Motion consistency filter ─────────────────────────────────────────────────
pub const STATIC_REJECT_FRAMES: u32 = 30;
pub const STATIC_GRID_SIZE: i32 = 5;
pub const HSV_CONFIRM_FRAMES: u32 = 3;

// ── ONNX / YOLO model ─────────────────────────────────────────────────────────
pub const MODEL_PATH: &str = "model.onnx";
pub const AI_THREADS: i32 = 4;
pub const AI_INPUT_SIZE: (i32, i32) = (320, 320); // (height, width)
pub const AI_CONF_THRESHOLD: f32 = 0.25;
pub const AI_NMS_THRESHOLD: f32 = 0.45;
pub const BALL_CLASS_ID: i32 = 0;

// ── OpenCV tracker ────────────────────────────────────────────────────────────
pub const TRACKER_TYPE: &str = "MOSSE";
pub const TRACKER_REINIT_INTERVAL: u32 = 15;

// ── GPIO motor control (BCM pin numbers) ──────────────────────────────────────
pub const MOTOR_A_DIR: u8 = 2;
pub const MOTOR_A_PWM: u8 = 5;
pub const MOTOR_B_DIR: u8 = 4;
pub const MOTOR_B_PWM: u8 = 6;
pub const PWM_FREQ: f64 = 100.0; // Hz

// ── PID ───────────────────────────────────────────────────────────────────────
pub const PID_KP: f64 = 0.8;
pub const PID_KI: f64 = 0.01;
pub const PID_KD: f64 = 0.1;
pub const MAX_SPEED: f64 = 80.0; // 0–100 PWM duty cycle

// ── Game logic ────────────────────────────────────────────────────────────────
pub const FRAME_CENTER_X: i32 = FRAME_WIDTH / 2;  // 160
pub const FRAME_CENTER_Y: i32 = FRAME_HEIGHT / 2; // 120
pub const DEAD_ZONE_X: i32 = 20;
pub const CLOSE_RADIUS: i32 = 40;
