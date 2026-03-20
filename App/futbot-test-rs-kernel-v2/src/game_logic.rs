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
pub fn decide_action(ball_x: Option<i32>, ball_y: Option<i32>, ball_radius: Option<i32>) -> Action {
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
