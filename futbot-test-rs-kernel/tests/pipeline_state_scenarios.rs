use std::collections::HashMap;

#[path = "../src/config.rs"]
mod config;

#[path = "../src/game_logic.rs"]
mod game_logic;

#[path = "../src/pipeline_state.rs"]
mod pipeline_state;

use game_logic::{decide_action, Action};

#[test]
fn no_detection_continues_search_behavior() {
    let mut last_known_pos = Some((160, 120));

    for no_ball_frames in 1..=35 {
        let action = decide_action(None, None, Some(15));
        assert_eq!(action, Action::Search);

        last_known_pos =
            pipeline_state::update_last_known_pos(last_known_pos, None, None, no_ball_frames, 30);

        if no_ball_frames <= 30 {
            assert_eq!(last_known_pos, Some((160, 120)));
        }
    }

    assert_eq!(last_known_pos, None);
}

#[test]
fn static_rejection_trips_only_after_threshold() {
    let mut static_hits = HashMap::new();

    let mut filtered = (Some(100), Some(100));
    for _ in 0..config::STATIC_REJECT_FRAMES {
        filtered = pipeline_state::apply_static_rejection(
            filtered.0,
            filtered.1,
            &mut static_hits,
            config::STATIC_GRID_SIZE,
            config::STATIC_REJECT_FRAMES,
        );
        assert_eq!(filtered, (Some(100), Some(100)));
    }

    filtered = pipeline_state::apply_static_rejection(
        filtered.0,
        filtered.1,
        &mut static_hits,
        config::STATIC_GRID_SIZE,
        config::STATIC_REJECT_FRAMES,
    );
    assert_eq!(filtered, (None, None));
}

#[test]
fn ai_cache_ages_and_expires_deterministically() {
    let mut cache = None;
    let mut age = 0;

    (cache, age) =
        pipeline_state::update_ai_cache(Some(7_i32), cache, age, config::AI_CACHE_MAX_AGE);
    assert_eq!(cache, Some(7));
    assert_eq!(age, 0);

    for expected_age in 1..=config::AI_CACHE_MAX_AGE {
        (cache, age) = pipeline_state::update_ai_cache(None, cache, age, config::AI_CACHE_MAX_AGE);
        assert_eq!(cache, Some(7));
        assert_eq!(age, expected_age);
    }

    (cache, age) = pipeline_state::update_ai_cache(None, cache, age, config::AI_CACHE_MAX_AGE);
    assert_eq!(cache, None);
    assert_eq!(age, 0);

    (cache, age) = pipeline_state::update_ai_cache(None, cache, age, config::AI_CACHE_MAX_AGE);
    assert_eq!(cache, None);
    assert_eq!(age, 0);
}
