#[path = "../src/vision/kernel/validate.rs"]
mod validate;

use validate::*;
use std::sync::{Mutex, OnceLock};

fn env_lock() -> &'static Mutex<()> {
    static ENV_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    ENV_LOCK.get_or_init(|| Mutex::new(()))
}

#[test]
fn mismatch_ratio_zero_for_identical() {
    assert_eq!(mismatch_ratio(&[0, 255, 1], &[0, 255, 1]), 0.0);
}

#[test]
fn mismatch_ratio_counts_different_bytes() {
    let ratio = mismatch_ratio(&[0, 255, 1, 7], &[0, 0, 1, 8]);
    assert!((ratio - 0.5).abs() < f64::EPSILON);
}

#[test]
fn env_flag_reads_truthy_values() {
    let _guard = env_lock().lock().unwrap();
    unsafe {
        std::env::set_var("VISION_VALIDATE_KERNEL_TEST", "true");
    }
    assert!(env_flag_enabled("VISION_VALIDATE_KERNEL_TEST"));
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL_TEST");
    }
}

#[test]
fn env_flag_reads_false_for_missing_or_falsy() {
    let _guard = env_lock().lock().unwrap();
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL_TEST");
        std::env::set_var("VISION_VALIDATE_KERNEL_TEST", "0");
    }
    assert!(!env_flag_enabled("VISION_VALIDATE_KERNEL_TEST"));
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL_TEST");
    }
}

#[test]
fn env_f64_uses_default_on_invalid() {
    let _guard = env_lock().lock().unwrap();
    unsafe {
        std::env::set_var("VISION_VALIDATE_KERNEL_RATIO_TEST", "nope");
    }
    assert_eq!(env_f64("VISION_VALIDATE_KERNEL_RATIO_TEST", 0.03), 0.03);
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL_RATIO_TEST");
    }
}

#[test]
fn env_f64_reads_valid_value() {
    let _guard = env_lock().lock().unwrap();
    unsafe {
        std::env::set_var("VISION_VALIDATE_KERNEL_RATIO_TEST", "0.125");
    }
    assert!((env_f64("VISION_VALIDATE_KERNEL_RATIO_TEST", 0.03) - 0.125).abs() < f64::EPSILON);
    unsafe {
        std::env::remove_var("VISION_VALIDATE_KERNEL_RATIO_TEST");
    }
}
