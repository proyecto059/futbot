use std::collections::HashMap;

pub fn update_ai_cache<T: Clone>(
    best: Option<T>,
    mut ai_cache: Option<T>,
    mut ai_cache_age: u32,
    max_age: u32,
) -> (Option<T>, u32) {
    if let Some(best) = best {
        ai_cache = Some(best);
        ai_cache_age = 0;
    } else if ai_cache.is_some() && ai_cache_age < max_age {
        ai_cache_age += 1;
    } else {
        ai_cache = None;
        ai_cache_age = 0;
    }

    (ai_cache, ai_cache_age)
}

pub fn apply_static_rejection(
    cx: Option<i32>,
    cy: Option<i32>,
    static_hits: &mut HashMap<(i32, i32), u32>,
    static_grid_size: i32,
    static_reject_frames: u32,
) -> (Option<i32>, Option<i32>) {
    if let (Some(fcx), Some(fcy)) = (cx, cy) {
        let key = (fcx / static_grid_size, fcy / static_grid_size);
        *static_hits.entry(key).or_insert(0) += 1;
        static_hits.retain(|k, v| k == &key || *v < static_reject_frames);
        if *static_hits.get(&key).unwrap_or(&0) > static_reject_frames {
            return (None, None);
        }
    }

    (cx, cy)
}

pub fn update_last_known_pos(
    current_last_known_pos: Option<(i32, i32)>,
    cx: Option<i32>,
    cy: Option<i32>,
    no_ball_frames: u32,
    clear_after_no_ball_frames: u32,
) -> Option<(i32, i32)> {
    if let (Some(fcx), Some(fcy)) = (cx, cy) {
        Some((fcx, fcy))
    } else if no_ball_frames > clear_after_no_ball_frames {
        None
    } else {
        current_last_known_pos
    }
}
