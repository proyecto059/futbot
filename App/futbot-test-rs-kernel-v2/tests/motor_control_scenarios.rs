#[path = "../src/config.rs"]
mod config;

#[path = "../src/motor_control.rs"]
mod motor_control;

use motor_control::PIDController;

#[test]
fn test_pid_update() {
    let mut pid = PIDController::new(1.0, 0.0, 0.0, 100.0);
    let out = pid.update(10.0, 0.1);
    assert!((out - 10.0).abs() < 1e-6, "expected 10.0, got {}", out);
}

#[test]
fn test_pid_clamp() {
    let mut pid = PIDController::new(10.0, 0.0, 0.0, 50.0);
    let out = pid.update(100.0, 1.0);
    assert_eq!(out, 50.0);
}

#[test]
fn test_pid_reset() {
    let mut pid = PIDController::new(0.0, 1.0, 0.0, 1000.0);
    pid.update(10.0, 1.0);
    pid.reset();
    let out = pid.update(0.0, 1.0);
    assert!((out - 0.0).abs() < 1e-6);
}
