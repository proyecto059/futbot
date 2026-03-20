//! AI mode selection and dynamic confidence threshold — extracted from main.rs.

use crate::ai_inference::Detection;
use crate::config::{
    ai_conf_max, ai_conf_min, ai_conf_search_base, ai_conf_track_base, ai_lost_bonus_max,
    ai_lost_bonus_per_frame, ai_lost_frames_start, ai_small_box_area_px, ai_small_box_bonus,
    ai_track_max_missing_frames,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AIMode {
    Search,
    Track,
}

pub fn select_ai_mode(
    ai_cache: Option<&Detection>,
    no_ball_frames: u32,
    hsv_streak: u32,
    hsv_track_streak: u32,
) -> AIMode {
    if (ai_cache.is_some() || hsv_streak >= hsv_track_streak)
        && no_ball_frames <= ai_track_max_missing_frames()
    {
        AIMode::Track
    } else {
        AIMode::Search
    }
}

pub fn effective_ai_conf_threshold(mode: AIMode, no_ball_frames: u32, est_box_area_px: i32) -> f32 {
    let base = match mode {
        AIMode::Search => ai_conf_search_base(),
        AIMode::Track => ai_conf_track_base(),
    };

    let mut thr = base;

    if est_box_area_px > 0 && (est_box_area_px as u32) <= ai_small_box_area_px() {
        thr -= ai_small_box_bonus().max(0.0);
    }

    if no_ball_frames >= ai_lost_frames_start() {
        let extra = no_ball_frames - ai_lost_frames_start();
        let lost_bonus =
            (extra as f32 * ai_lost_bonus_per_frame().max(0.0)).min(ai_lost_bonus_max().max(0.0));
        thr -= lost_bonus;
    }

    thr.clamp(ai_conf_min(), ai_conf_max())
}
