use std::sync::{Mutex, OnceLock};

#[path = "../src/config.rs"]
mod config;

#[path = "../src/vision/kernel/mod.rs"]
pub mod kernel;

#[path = "../src/vision/kernel_dispatch.rs"]
pub mod kernel_dispatch;

pub mod vision {
    pub use super::kernel;
    pub use super::kernel_dispatch;
}

use config::DetectorBackend;

fn env_lock() -> &'static Mutex<()> {
    static ENV_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    ENV_LOCK.get_or_init(|| Mutex::new(()))
}

struct EnvRestore {
    saved: Vec<(&'static str, Option<String>)>,
}

impl EnvRestore {
    fn capture(names: &[&'static str]) -> Self {
        let mut saved = Vec::with_capacity(names.len());
        for name in names {
            saved.push((*name, std::env::var(name).ok()));
        }
        Self { saved }
    }
}

impl Drop for EnvRestore {
    fn drop(&mut self) {
        for (name, value) in &self.saved {
            unsafe {
                match value {
                    Some(v) => std::env::set_var(name, v),
                    None => std::env::remove_var(name),
                }
            }
        }
    }
}

#[test]
fn detector_backend_defaults_to_hsv() {
    let _guard = env_lock().lock().expect("env lock poisoned");
    let _restore = EnvRestore::capture(&["DETECTOR_BACKEND"]);
    unsafe {
        std::env::remove_var("DETECTOR_BACKEND");
    }
    assert_eq!(config::detector_backend(), DetectorBackend::Hsv);

    unsafe {
        std::env::set_var("DETECTOR_BACKEND", "unknown-value");
    }
    assert_eq!(config::detector_backend(), DetectorBackend::Hsv);
}

#[test]
fn fused_and_ai_roi_defaults_remain_disabled() {
    let _guard = env_lock().lock().expect("env lock poisoned");
    let _restore = EnvRestore::capture(&["VISION_FUSED", "AI_USE_ROI"]);
    unsafe {
        std::env::remove_var("VISION_FUSED");
        std::env::remove_var("AI_USE_ROI");
    }

    assert!(!config::vision_fused_enabled());
    assert!(!config::ai_roi_enabled());
}

#[test]
fn ai_stride_default_remains_one() {
    let _guard = env_lock().lock().expect("env lock poisoned");
    let _restore = EnvRestore::capture(&["AI_STRIDE"]);
    unsafe {
        std::env::remove_var("AI_STRIDE");
    }
    assert_eq!(config::ai_stride(), 1);

    unsafe {
        std::env::set_var("AI_STRIDE", "0");
    }
    assert_eq!(config::ai_stride(), 1);
}

#[test]
fn kernel_dispatch_default_regression_contract() {
    let _guard = env_lock().lock().expect("env lock poisoned");
    let _restore = EnvRestore::capture(&[
        "VISION_VALIDATE_KERNEL",
        "VISION_VALIDATE_MISMATCH_THRESHOLD",
        "VISION_FUSED",
    ]);
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL");
        std::env::remove_var("VISION_VALIDATE_MISMATCH_THRESHOLD");
        std::env::remove_var("VISION_FUSED");
    }

    let info = vision::kernel_dispatch::KernelDispatch::new().info();
    assert!(!info.validation_enabled);
    assert!((info.mismatch_threshold - 0.03).abs() < f64::EPSILON);
    assert!(!info.forced_scalar_fallback);
    assert!(!info.fused_bgr_enabled);

    assert!(matches!(
        info.backend,
        vision::kernel::KernelBackend::Scalar
            | vision::kernel::KernelBackend::Avx2
            | vision::kernel::KernelBackend::Neon
    ));
}
