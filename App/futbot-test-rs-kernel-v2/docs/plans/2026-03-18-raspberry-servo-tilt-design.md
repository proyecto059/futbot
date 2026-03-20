# Raspberry Servo Tilt Tracking Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add vertical camera-servo tracking so the robot tilts the camera up/down to keep the ball centered on the Y axis while preserving existing drive behavior.

**Architecture:** Integrate a new Raspberry-focused servo controller module into the existing Rust main loop and drive it from the final fused ball center (`cy`) already produced by HSV/AI/Kalman/tracker logic. Keep servo control independent from DC motor decisions by using a dedicated control law (deadzone + incremental angle updates + clamp + optional return-home). Place servo-specific code under a new `src/raspberry/` module tree.

**Tech Stack:** Rust (`rppal`), existing FutBot pipeline, Raspberry Pi GPIO/PWM.

---

## Design Overview

### 1) Module layout

Create a new module folder under `src/`:

- `src/raspberry/mod.rs`
- `src/raspberry/servo_tilt.rs`

Rationale:
- Keeps hardware-specific logic grouped and separate from motion, camera, detector, and AI modules.
- Aligns with your requirement that this lives in a `raspberry/` folder.

### 2) Runtime control point in pipeline

Use `cy` from `src/main.rs` after all fusion/filter stages, right before/near motor action output. This gives the cleanest and most stable tracking signal because it already includes:

- HSV detection
- optional tracker fallback
- AI fusion (if enabled)
- Kalman smoothing
- static rejection filter

Servo update should run every main-loop iteration.

### 3) Servo control behavior (vertical)

Control law:

- Error: `err_y = cy - FRAME_CENTER_Y`
- Deadzone: if `abs(err_y) <= SERVO_DEAD_ZONE_Y`, keep angle
- Outside deadzone: move angle by `SERVO_STEP_DEG` per update
- Clamp angle to `[SERVO_MIN_ANGLE, SERVO_MAX_ANGLE]`
- Optional invert via `SERVO_INVERT` to match your mechanical orientation

Missing ball behavior:

- Hold current angle for `SERVO_HOLD_NO_BALL_FRAMES`
- If configured (`SERVO_RETURN_HOME=true`) and missing persists, move toward `SERVO_HOME_ANGLE` gradually

Safety:

- Always clamp output angle
- Gracefully degrade if PWM setup fails (log warning, no panic)
- Cleanup on shutdown

### 4) PWM and pin mapping

Use 50 Hz PWM for SG90-class servo.

Duty conversion mirrors your Python:

- `duty = 2.5 + (10.0 * angle / 180.0)`

Pin selection via BCM and config/env.

### 5) Config additions (`src/config.rs`)

Add environment-backed helpers and defaults for:

- `servo_tilt_enabled()` -> env `SERVO_TILT_ENABLED` (default true)
- `servo_pwm_bcm()` -> env `SERVO_PWM_BCM` (default 18)
- `servo_min_angle()` / `servo_max_angle()` / `servo_home_angle()`
- `servo_step_deg()`
- `servo_dead_zone_y()`
- `servo_invert()`
- `servo_hold_no_ball_frames()`
- `servo_return_home()`

These keep tuning easy on-device without recompiling.

### 6) Logging and observability

Log once at startup:

- servo enabled state
- BCM pin
- angle limits and home
- invert flag

Periodic debug info (at debug level):

- `cy`, `err_y`, command direction, resulting angle

This helps tune deadzone/step quickly.

### 7) Testing strategy

Unit-test pure logic in `src/raspberry/servo_tilt.rs` (no real GPIO required):

- angle clamp
- deadzone no-move behavior
- invert direction behavior
- missing-ball hold vs return-home
- angle->duty conversion bounds

Hardware interaction remains runtime-tested on Pi.

---

## File-Level Change Plan

### Create: `src/raspberry/mod.rs`

Exports:

- `pub mod servo_tilt;`
- `pub use servo_tilt::ServoTiltController;`

### Create: `src/raspberry/servo_tilt.rs`

Implement:

- `ServoTiltController`
  - setup/init (`rppal` on Linux)
  - update(cy: Option<i32>, no_ball_frames: u32)
  - cleanup()
- internal config snapshot struct for fast reads
- pure helper functions for clamp and duty conversion

### Modify: `src/main.rs`

- Add `mod raspberry;`
- `use raspberry::ServoTiltController;`
- instantiate and setup controller near motor setup
- call update each loop using fused `cy` and `no_ball_frames`
- cleanup during shutdown

### Modify: `src/config.rs`

Add servo-related constants/helpers listed above.

---

## Operational Notes

- Servo tracking is independent of drive action selection in `game_logic.rs`.
- Vertical axis is intentionally tied to Y center only.
- Keeps existing AI/HSV behavior untouched.
- Uses same style as current motor control: hardware-optional with graceful fallback.

---

## Risk & Mitigation

- **Wrong servo direction** due to mounting orientation
  - Mitigation: `SERVO_INVERT=true/false` toggle
- **Servo chatter** near center
  - Mitigation: deadzone + incremental stepping
- **Mechanical stress** at extremes
  - Mitigation: min/max clamp defaults conservative
- **No GPIO access**
  - Mitigation: warn and run without servo control

---

## Validation Checklist (after implementation)

1. Build on host and cross target succeeds.
2. On Pi startup, servo module logs configured pin and limits.
3. Moving ball up/down causes corresponding tilt movement.
4. No-ball behavior matches configured hold/return-home policy.
5. Shutdown releases PWM cleanly.
6. Existing drive motor actions still work unchanged.
