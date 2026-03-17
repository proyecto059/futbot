#[path = "../src/config.rs"]
mod config;

#[path = "../src/game_logic.rs"]
mod game_logic;

use game_logic::{decide_action, Action};

#[test]
fn test_no_ball_returns_search() {
    assert_eq!(decide_action(None, None, None), Action::Search);
}

#[test]
fn test_close_ball_returns_stop() {
    assert_eq!(decide_action(Some(160), Some(120), Some(40)), Action::Stop);
    assert_eq!(decide_action(Some(160), Some(120), Some(50)), Action::Stop);
}

#[test]
fn test_ball_right_returns_turn_right() {
    // error_x = 200 - 160 = 40 > DEAD_ZONE_X(20)
    assert_eq!(
        decide_action(Some(200), Some(120), Some(10)),
        Action::TurnRight
    );
}

#[test]
fn test_ball_left_returns_turn_left() {
    // error_x = 100 - 160 = -60 < -DEAD_ZONE_X
    assert_eq!(
        decide_action(Some(100), Some(120), Some(10)),
        Action::TurnLeft
    );
}

#[test]
fn test_ball_center_returns_forward() {
    // error_x = 160 - 160 = 0, within dead zone
    assert_eq!(
        decide_action(Some(160), Some(120), Some(10)),
        Action::Forward
    );
}
