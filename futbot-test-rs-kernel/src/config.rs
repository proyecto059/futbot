//! Configuration — mirrors config.py exactly.
//!
//! Env vars (same as Python):
//!   CAMERA_URL        MJPEG stream URL   (default: http://192.168.4.1:81/stream)
//!   USE_LOCAL_CAM     "true" to use /dev/videoN
//!   LOCAL_CAM_ID      device index       (default: 0)

use std::env;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DetectorBackend {
    Hsv,
    Bgr,
}

impl DetectorBackend {
    pub fn short_label(self) -> &'static str {
        match self {
            Self::Hsv => "HSV",
            Self::Bgr => "BGR",
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct BgrThresholds {
    pub r_min: u8,
    pub g_min: u8,
    pub b_max: u8,
    pub rg_delta_min: i16,
    pub rb_delta_min: i16,
    pub gb_delta_min: i16,
}

fn env_u8(name: &str, default: u8) -> u8 {
    env::var(name)
        .ok()
        .and_then(|v| v.parse::<u8>().ok())
        .unwrap_or(default)
}

fn env_i16(name: &str, default: i16) -> i16 {
    env::var(name)
        .ok()
        .and_then(|v| v.parse::<i16>().ok())
        .unwrap_or(default)
}

fn env_u32(name: &str, default: u32) -> u32 {
    env::var(name)
        .ok()
        .and_then(|v| v.parse::<u32>().ok())
        .unwrap_or(default)
}

fn env_u32_opt(name: &str) -> Option<u32> {
    env::var(name).ok().and_then(|v| v.parse::<u32>().ok())
}

fn env_f32(name: &str, default: f32) -> f32 {
    env::var(name)
        .ok()
        .and_then(|v| v.parse::<f32>().ok())
        .unwrap_or(default)
}

fn env_bool(name: &str, default: bool) -> bool {
    env::var(name)
        .ok()
        .map(|v| {
            let v = v.trim();
            v.eq_ignore_ascii_case("1")
                || v.eq_ignore_ascii_case("true")
                || v.eq_ignore_ascii_case("yes")
                || v.eq_ignore_ascii_case("on")
        })
        .unwrap_or(default)
}

// ── Camera ───────────────────────────────────────────────────────────────────
pub const FRAME_WIDTH: i32 = 320;
pub const FRAME_HEIGHT: i32 = 240;

pub fn camera_url() -> String {
    env::var("CAMERA_URL").unwrap_or_else(|_| "http://192.168.4.1:81/stream".into())
}

pub fn use_local_cam() -> bool {
    env_bool("USE_LOCAL_CAM", false)
}

pub fn local_cam_id() -> i32 {
    env::var("LOCAL_CAM_ID")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(0)
}

pub fn detector_backend() -> DetectorBackend {
    match env::var("DETECTOR_BACKEND") {
        Ok(value) if value.eq_ignore_ascii_case("bgr") => DetectorBackend::Bgr,
        _ => DetectorBackend::Hsv,
    }
}

pub fn bgr_thresholds() -> BgrThresholds {
    BgrThresholds {
        r_min: env_u8("BGR_R_MIN", 120),
        g_min: env_u8("BGR_G_MIN", 55),
        b_max: env_u8("BGR_B_MAX", 140),
        rg_delta_min: env_i16("BGR_RG_DELTA_MIN", 25),
        rb_delta_min: env_i16("BGR_RB_DELTA_MIN", 45),
        gb_delta_min: env_i16("BGR_GB_DELTA_MIN", 5),
    }
}

pub fn vision_fused_enabled() -> bool {
    env_bool("VISION_FUSED", false)
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
pub const AI_SUBMIT_STRIDE_DEFAULT: u32 = 1;

pub fn ai_stride() -> u32 {
    env_u32("AI_STRIDE", AI_SUBMIT_STRIDE_DEFAULT).max(1)
}

pub fn ai_stride_search() -> u32 {
    env_u32_opt("AI_STRIDE_SEARCH")
        .unwrap_or_else(ai_stride)
        .max(1)
}

pub fn ai_stride_track() -> u32 {
    env_u32_opt("AI_STRIDE_TRACK")
        .unwrap_or_else(|| ai_stride().max(2))
        .max(1)
}

pub fn ai_track_fullframe_every() -> u32 {
    env_u32("AI_TRACK_FULLFRAME_EVERY", 6).max(1)
}

pub fn ai_hsv_track_streak() -> u32 {
    env_u32("AI_HSV_TRACK_STREAK", 2).max(1)
}

pub fn ai_track_max_missing_frames() -> u32 {
    env_u32("AI_TRACK_MAX_MISSING_FRAMES", 8)
}

pub fn ai_conf_search_base() -> f32 {
    env_f32("AI_CONF_BASE_SEARCH", 0.24)
}

pub fn ai_conf_track_base() -> f32 {
    env_f32("AI_CONF_BASE_TRACK", 0.34)
}

pub fn ai_conf_min() -> f32 {
    env_f32("AI_CONF_MIN", 0.12)
}

pub fn ai_conf_max() -> f32 {
    env_f32("AI_CONF_MAX", 0.60)
}

pub fn ai_small_box_area_px() -> u32 {
    env_u32("AI_SMALL_BOX_AREA_PX", 1400)
}

pub fn ai_small_box_bonus() -> f32 {
    env_f32("AI_SMALL_BOX_BONUS", 0.06)
}

pub fn ai_lost_frames_start() -> u32 {
    env_u32("AI_LOST_FRAMES_START", 8)
}

pub fn ai_lost_bonus_per_frame() -> f32 {
    env_f32("AI_LOST_BONUS_PER_FRAME", 0.004)
}

pub fn ai_lost_bonus_max() -> f32 {
    env_f32("AI_LOST_BONUS_MAX", 0.10)
}

pub fn ai_parser_conf_floor() -> f32 {
    env_f32("AI_CONF_FLOOR", 0.10)
}

pub fn ai_cache_max_age() -> u32 {
    env_u32("AI_CACHE_MAX_AGE", AI_CACHE_MAX_AGE).max(1)
}

pub fn ai_roi_enabled() -> bool {
    env_bool("AI_USE_ROI", false)
}

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
pub const FRAME_CENTER_X: i32 = FRAME_WIDTH / 2; // 160
pub const FRAME_CENTER_Y: i32 = FRAME_HEIGHT / 2; // 120
pub const DEAD_ZONE_X: i32 = 20;
pub const CLOSE_RADIUS: i32 = 40;
