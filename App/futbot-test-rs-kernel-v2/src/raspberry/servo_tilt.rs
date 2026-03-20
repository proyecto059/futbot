use crate::config::{
    servo_dead_zone_y, servo_hold_no_ball_frames, servo_home_angle, servo_invert, servo_max_angle,
    servo_min_angle, servo_pwm_bcm, servo_return_home, servo_step_deg, servo_tilt_enabled,
    FRAME_CENTER_Y,
};

#[cfg(target_os = "linux")]
use rppal::gpio::{Gpio, OutputPin};

#[derive(Debug, Clone)]
pub struct ServoTiltConfig {
    pub enabled: bool,
    pub pin_bcm: u8,
    pub min_angle: f64,
    pub max_angle: f64,
    pub home_angle: f64,
    pub step_deg: f64,
    pub dead_zone_y: i32,
    pub invert: bool,
    pub hold_no_ball_frames: u32,
    pub return_home: bool,
}

impl ServoTiltConfig {
    pub fn from_env() -> Self {
        let min_angle = servo_min_angle();
        let max_angle = servo_max_angle();
        let home_angle = servo_home_angle().clamp(min_angle, max_angle);
        Self {
            enabled: servo_tilt_enabled(),
            pin_bcm: servo_pwm_bcm(),
            min_angle,
            max_angle,
            home_angle,
            step_deg: servo_step_deg().max(0.1),
            dead_zone_y: servo_dead_zone_y().max(0),
            invert: servo_invert(),
            hold_no_ball_frames: servo_hold_no_ball_frames(),
            return_home: servo_return_home(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ServoTiltState {
    pub angle_deg: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ServoDecision {
    Hold,
    Up,
    Down,
    Home,
}

fn clamp_angle(angle: f64, cfg: &ServoTiltConfig) -> f64 {
    angle.clamp(cfg.min_angle, cfg.max_angle)
}

fn angle_to_duty(angle_deg: f64) -> f64 {
    2.5 + (10.0 * angle_deg / 180.0)
}

fn next_servo_angle(
    cy: Option<i32>,
    no_ball_frames: u32,
    state: &ServoTiltState,
    cfg: &ServoTiltConfig,
    frame_center_y: i32,
) -> (f64, ServoDecision) {
    if !cfg.enabled {
        return (state.angle_deg, ServoDecision::Hold);
    }

    let current = clamp_angle(state.angle_deg, cfg);

    if no_ball_frames > 0 {
        if no_ball_frames > cfg.hold_no_ball_frames && cfg.return_home {
            let delta = cfg.home_angle - current;
            if delta.abs() <= cfg.step_deg {
                return (clamp_angle(cfg.home_angle, cfg), ServoDecision::Home);
            }
            let dir = if delta > 0.0 { 1.0 } else { -1.0 };
            return (
                clamp_angle(current + dir * cfg.step_deg, cfg),
                ServoDecision::Home,
            );
        }
        return (current, ServoDecision::Hold);
    }

    let Some(cy) = cy else {
        return (current, ServoDecision::Hold);
    };

    let err_y = cy - frame_center_y;
    if err_y.abs() <= cfg.dead_zone_y {
        return (current, ServoDecision::Hold);
    }

    let mut direction = if err_y < 0 { 1.0 } else { -1.0 };
    if cfg.invert {
        direction *= -1.0;
    }

    let next = clamp_angle(current + direction * cfg.step_deg, cfg);
    let decision = if direction > 0.0 {
        ServoDecision::Up
    } else {
        ServoDecision::Down
    };
    (next, decision)
}

pub struct ServoTiltController {
    cfg: ServoTiltConfig,
    state: ServoTiltState,
    #[cfg(target_os = "linux")]
    soft_pwm_pin: Option<OutputPin>,
}

impl ServoTiltController {
    pub fn new() -> Self {
        let cfg = ServoTiltConfig::from_env();
        let state = ServoTiltState {
            angle_deg: cfg.home_angle,
        };
        Self {
            cfg,
            state,
            #[cfg(target_os = "linux")]
            soft_pwm_pin: None,
        }
    }

    pub fn setup(&mut self) {
        if !self.cfg.enabled {
            log::info!("[servo] disabled via SERVO_TILT_ENABLED");
            return;
        }

        #[cfg(target_os = "linux")]
        {
            let duty = angle_to_duty(self.state.angle_deg) / 100.0;
            match Gpio::new()
                .and_then(|gpio| gpio.get(self.cfg.pin_bcm).map(|pin| pin.into_output()))
            {
                Ok(mut pin) => {
                    if let Err(e) = pin.set_pwm_frequency(50.0, duty) {
                        log::warn!("[servo] failed to initialize software PWM: {}", e);
                        return;
                    }
                    self.soft_pwm_pin = Some(pin);
                    log::info!(
                        "[servo] initialized (software PWM BCM={} duty={:.3} angle={:.1} min={:.1} max={:.1} invert={})",
                        self.cfg.pin_bcm,
                        duty,
                        self.state.angle_deg,
                        self.cfg.min_angle,
                        self.cfg.max_angle,
                        self.cfg.invert
                    );
                }
                Err(e) => {
                    log::warn!("[servo] failed to initialize GPIO software PWM: {}", e);
                }
            }
        }

        #[cfg(not(target_os = "linux"))]
        {
            log::warn!("[servo] non-Linux platform — running without servo control");
        }
    }

    pub fn update(&mut self, cy: Option<i32>, no_ball_frames: u32) {
        if !self.cfg.enabled {
            return;
        }

        let (next_angle, decision) =
            next_servo_angle(cy, no_ball_frames, &self.state, &self.cfg, FRAME_CENTER_Y);

        if (next_angle - self.state.angle_deg).abs() < f64::EPSILON {
            return;
        }

        self.state.angle_deg = next_angle;

        #[cfg(target_os = "linux")]
        if let Some(pin) = self.soft_pwm_pin.as_mut() {
            let duty = angle_to_duty(self.state.angle_deg) / 100.0;
            if let Err(e) = pin.set_pwm_frequency(50.0, duty) {
                log::warn!("[servo] failed to set software PWM duty cycle: {}", e);
            } else {
                log::debug!(
                    "[servo] {:?} cy={:?} no_ball_frames={} angle={:.1} duty={:.3}",
                    decision,
                    cy,
                    no_ball_frames,
                    self.state.angle_deg,
                    duty
                );
            }
        }

        #[cfg(not(target_os = "linux"))]
        let _ = decision;
    }

    pub fn cleanup(&mut self) {
        #[cfg(target_os = "linux")]
        {
            if let Some(mut pin) = self.soft_pwm_pin.take() {
                let _ = pin.clear_pwm();
                pin.set_low();
            }
        }
    }
}

impl Default for ServoTiltController {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg() -> ServoTiltConfig {
        ServoTiltConfig {
            enabled: true,
            pin_bcm: 18,
            min_angle: 20.0,
            max_angle: 160.0,
            home_angle: 90.0,
            step_deg: 2.0,
            dead_zone_y: 15,
            invert: false,
            hold_no_ball_frames: 10,
            return_home: true,
        }
    }

    #[test]
    fn clamp_angle_limits_bounds() {
        let c = cfg();
        assert_eq!(clamp_angle(0.0, &c), 20.0);
        assert_eq!(clamp_angle(90.0, &c), 90.0);
        assert_eq!(clamp_angle(180.0, &c), 160.0);
    }

    #[test]
    fn angle_to_duty_maps_endpoints() {
        assert!((angle_to_duty(0.0) - 2.5).abs() < 1e-9);
        assert!((angle_to_duty(180.0) - 12.5).abs() < 1e-9);
        assert!((angle_to_duty(90.0) - 7.5).abs() < 1e-9);
    }

    #[test]
    fn no_move_inside_deadzone() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 90.0 };
        let (next, d) = next_servo_angle(Some(120), 0, &s, &c, 120);
        assert_eq!(next, 90.0);
        assert_eq!(d, ServoDecision::Hold);
    }

    #[test]
    fn moves_up_when_ball_above_center() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 90.0 };
        let (next, d) = next_servo_angle(Some(90), 0, &s, &c, 120);
        assert_eq!(next, 92.0);
        assert_eq!(d, ServoDecision::Up);
    }

    #[test]
    fn moves_down_when_ball_below_center() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 90.0 };
        let (next, d) = next_servo_angle(Some(150), 0, &s, &c, 120);
        assert_eq!(next, 88.0);
        assert_eq!(d, ServoDecision::Down);
    }

    #[test]
    fn invert_flips_direction() {
        let mut c = cfg();
        c.invert = true;
        let s = ServoTiltState { angle_deg: 90.0 };
        let (next, d) = next_servo_angle(Some(90), 0, &s, &c, 120);
        assert_eq!(next, 88.0);
        assert_eq!(d, ServoDecision::Down);
    }

    #[test]
    fn holds_before_threshold_when_ball_missing() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 110.0 };
        let (next, d) = next_servo_angle(None, 10, &s, &c, 120);
        assert_eq!(next, 110.0);
        assert_eq!(d, ServoDecision::Hold);
    }

    #[test]
    fn returns_home_after_threshold_when_ball_missing() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 110.0 };
        let (next, d) = next_servo_angle(None, 11, &s, &c, 120);
        assert_eq!(next, 108.0);
        assert_eq!(d, ServoDecision::Home);
    }

    #[test]
    fn clamps_to_limits_when_stepping() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 159.5 };
        let (next, d) = next_servo_angle(Some(80), 0, &s, &c, 120);
        assert_eq!(next, 160.0);
        assert_eq!(d, ServoDecision::Up);
    }

    #[test]
    fn no_ball_frames_ignores_predicted_cy() {
        let c = cfg();
        let s = ServoTiltState { angle_deg: 100.0 };
        let (next, d) = next_servo_angle(Some(10), 1, &s, &c, 120);
        assert_eq!(next, 100.0);
        assert_eq!(d, ServoDecision::Hold);
    }
}
