#[path = "../src/config.rs"]
mod config;

#[path = "../src/ai_inference.rs"]
mod ai_inference;

#[path = "../src/ai_policy.rs"]
mod ai_policy;

use ai_inference::Detection;
use ai_policy::{effective_ai_conf_threshold, select_ai_mode, AIMode};
use config::{ai_lost_frames_start, ai_small_box_area_px, ai_track_max_missing_frames};

#[test]
fn ai_mode_switches_between_search_and_track() {
    assert_eq!(select_ai_mode(None, 0, 0, 2), AIMode::Search);
    assert_eq!(
        select_ai_mode(
            Some(&Detection {
                cx: 0,
                cy: 0,
                w: 10,
                h: 10,
                conf: 0.5,
                class_id: 0,
            }),
            0,
            0,
            2
        ),
        AIMode::Track
    );
    assert_eq!(
        select_ai_mode(
            Some(&Detection {
                cx: 0,
                cy: 0,
                w: 10,
                h: 10,
                conf: 0.5,
                class_id: 0,
            }),
            ai_track_max_missing_frames() + 1,
            0,
            2
        ),
        AIMode::Search
    );
    assert_eq!(select_ai_mode(None, 0, 3, 2), AIMode::Track);
}

#[test]
fn dynamic_threshold_gets_lower_when_lost_or_small() {
    let base = effective_ai_conf_threshold(AIMode::Search, 0, 1000);
    let lost = effective_ai_conf_threshold(AIMode::Search, ai_lost_frames_start() + 20, 1000);
    let small = effective_ai_conf_threshold(AIMode::Search, 0, ai_small_box_area_px() as i32);

    assert!(lost <= base);
    assert!(small <= base);
}
