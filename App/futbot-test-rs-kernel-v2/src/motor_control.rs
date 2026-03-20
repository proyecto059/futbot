//! Motor control — mirrors motor_control.py exactly.
//!
//! Dual DC motors via RPi GPIO PWM (BCM pins).
//! H-bridge DIR+PWM scheme (e.g. L298N).
//! Uses software PWM for GPIO 5 and 6 since those are not hardware PWM pins on RPi3.
//! On non-Linux or without GPIO access, degrades gracefully (no-op).

use crate::config::{
    MAX_SPEED, MOTOR_A_DIR, MOTOR_A_PWM, MOTOR_B_DIR, MOTOR_B_PWM, PID_KD, PID_KI, PID_KP,
};

// ── PID Controller ────────────────────────────────────────────────────────────

/// Pure-math PID controller — no GPIO dependency, fully testable.
/// Mirrors `PIDController` in Python.
pub struct PIDController {
    pub kp: f64,
    pub ki: f64,
    pub kd: f64,
    pub max_output: f64,
    integral: f64,
    prev_error: f64,
}

impl PIDController {
    pub fn new(kp: f64, ki: f64, kd: f64, max_output: f64) -> Self {
        PIDController {
            kp,
            ki,
            kd,
            max_output,
            integral: 0.0,
            prev_error: 0.0,
        }
    }

    pub fn update(&mut self, error: f64, dt: f64) -> f64 {
        self.integral += error * dt;
        let derivative = if dt > 0.0 {
            (error - self.prev_error) / dt
        } else {
            0.0
        };
        self.prev_error = error;
        let output = self.kp * error + self.ki * self.integral + self.kd * derivative;
        output.clamp(-self.max_output, self.max_output)
    }

    pub fn reset(&mut self) {
        self.integral = 0.0;
        self.prev_error = 0.0;
    }
}

impl Default for PIDController {
    fn default() -> Self {
        Self::new(PID_KP, PID_KI, PID_KD, MAX_SPEED)
    }
}

// ── Motor Controller ──────────────────────────────────────────────────────────

/// Controls dual DC motors. Uses rppal on Linux/RPi; no-op elsewhere.
/// Mirrors `MotorController` in Python.
pub struct MotorController {
    #[cfg(target_os = "linux")]
    inner: Option<GpioMotors>,
    #[cfg(not(target_os = "linux"))]
    _phantom: (),
}

#[cfg(target_os = "linux")]
struct GpioMotors {
    gpio: rppal::gpio::Gpio,
    dir_a: rppal::gpio::OutputPin,
    dir_b: rppal::gpio::OutputPin,
    pwm_a: rppal::gpio::OutputPin,
    pwm_b: rppal::gpio::OutputPin,
}

impl MotorController {
    pub fn new() -> Self {
        #[cfg(target_os = "linux")]
        return MotorController { inner: None };
        #[cfg(not(target_os = "linux"))]
        MotorController { _phantom: () }
    }

    /// Initialize GPIO. Gracefully skips if not on RPi.
    pub fn setup(&mut self) {
        #[cfg(target_os = "linux")]
        match Self::try_setup() {
            Ok(motors) => {
                self.inner = Some(motors);
                log::info!(
                    "[motors] GPIO initialized (BCM: A_DIR={} A_PWM={} B_DIR={} B_PWM={})",
                    MOTOR_A_DIR,
                    MOTOR_A_PWM,
                    MOTOR_B_DIR,
                    MOTOR_B_PWM
                );
            }
            Err(e) => {
                log::warn!(
                    "[motors] GPIO not available ({}) — running without motor control",
                    e
                );
            }
        }
        #[cfg(not(target_os = "linux"))]
        log::warn!("[motors] Non-Linux platform — running without motor control");
    }

    #[cfg(target_os = "linux")]
    fn try_setup() -> anyhow::Result<GpioMotors> {
        let gpio = rppal::gpio::Gpio::new()?;
        let dir_a = gpio.get(MOTOR_A_DIR)?.into_output();
        let dir_b = gpio.get(MOTOR_B_DIR)?.into_output();
        let pwm_a = gpio.get(MOTOR_A_PWM)?.into_output();
        let pwm_b = gpio.get(MOTOR_B_PWM)?.into_output();
        Ok(GpioMotors {
            gpio,
            dir_a,
            dir_b,
            pwm_a,
            pwm_b,
        })
    }

    /// Set motor speeds. speed range: -MAX_SPEED to +MAX_SPEED.
    /// Positive = forward, negative = backward.
    /// Note: software PWM is approximated as full on/off (duty cycle via OS scheduler).
    pub fn apply(&mut self, left_speed: f64, right_speed: f64) {
        #[cfg(target_os = "linux")]
        if let Some(ref mut m) = self.inner {
            Self::set_motor_direction(&mut m.dir_a, &mut m.pwm_a, left_speed);
            Self::set_motor_direction(&mut m.dir_b, &mut m.pwm_b, right_speed);
        }
        #[cfg(not(target_os = "linux"))]
        let _ = (left_speed, right_speed);
    }

    #[cfg(target_os = "linux")]
    fn set_motor_direction(
        dir: &mut rppal::gpio::OutputPin,
        pwm: &mut rppal::gpio::OutputPin,
        speed: f64,
    ) {
        // Direction
        if speed >= 0.0 {
            dir.set_high();
        } else {
            dir.set_low();
        }
        // PWM: full on when speed > 0, off when speed == 0
        // For proper soft-PWM, use rppal::gpio::OutputPin::set_pwm or pigpio daemon
        if speed.abs() > 1.0 {
            pwm.set_high();
        } else {
            pwm.set_low();
        }
    }

    pub fn forward(&mut self) {
        self.apply(MAX_SPEED, MAX_SPEED);
    }

    pub fn turn_right(&mut self, speed: f64) {
        self.apply(speed, -speed);
    }

    pub fn turn_left(&mut self, speed: f64) {
        self.apply(-speed, speed);
    }

    pub fn stop(&mut self) {
        self.apply(0.0, 0.0);
    }

    pub fn cleanup(&mut self) {
        self.stop();
        #[cfg(target_os = "linux")]
        {
            self.inner = None;
        }
    }
}

impl Default for MotorController {
    fn default() -> Self {
        Self::new()
    }
}
