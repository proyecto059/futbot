//! Game logic — mirrors game_logic.py exactly.
//!
//! Pure function: maps ball position to robot action. No side effects.

use crate::config::{CLOSE_RADIUS, DEAD_ZONE_X, FRAME_CENTER_X};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Forward,
    TurnLeft,
    TurnRight,
    Stop,
    Search,
}

impl Action {
    pub fn name(&self) -> &'static str {
        match self {
            Action::Forward => "FORWARD",
            Action::TurnLeft => "TURN_LEFT",
            Action::TurnRight => "TURN_RIGHT",
            Action::Stop => "STOP",
            Action::Search => "SEARCH",
        }
    }
}

/// Maps ball position to robot action.
/// Mirrors `decide_action()` in Python.
pub fn decide_action(
    ball_x: Option<i32>,
    ball_y: Option<i32>,
    ball_radius: Option<i32>,
) -> Action {
    let (Some(bx), Some(_by), Some(r)) = (ball_x, ball_y, ball_radius) else {
        return Action::Search;
    };

    if r >= CLOSE_RADIUS {
        return Action::Stop;
    }

    let error_x = bx - FRAME_CENTER_X;
    if error_x > DEAD_ZONE_X {
        return Action::TurnRight;
    }
    if error_x < -DEAD_ZONE_X {
        return Action::TurnLeft;
    }

    Action::Forward
}

#[cfg(test)]
mod tests {
    use super::*;

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
        assert_eq!(decide_action(Some(200), Some(120), Some(10)), Action::TurnRight);
    }

    #[test]
    fn test_ball_left_returns_turn_left() {
        // error_x = 100 - 160 = -60 < -DEAD_ZONE_X
        assert_eq!(decide_action(Some(100), Some(120), Some(10)), Action::TurnLeft);
    }

    #[test]
    fn test_ball_center_returns_forward() {
        // error_x = 160 - 160 = 0, within dead zone
        assert_eq!(decide_action(Some(160), Some(120), Some(10)), Action::Forward);
    }
}
