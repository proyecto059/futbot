use anyhow::Result;
use opencv::{
    core::{self, Mat, Scalar, Vec3b},
    prelude::*,
};

#[path = "../src/config.rs"]
pub mod config;

#[path = "../src/vision/kernel/mod.rs"]
pub mod kernel;

#[path = "../src/vision/kernel_dispatch.rs"]
pub mod kernel_dispatch;

pub mod vision {
    pub use super::kernel;
    pub use super::kernel_dispatch;
}

use vision::kernel::{
    avx_kernel::AvxKernel, neon_kernel::NeonKernel, scalar_kernel::ScalarKernel,
    validate::mismatch_ratio, HsvThresholdKernel, KernelBackend,
};

const LOWER: [u8; 3] = [5, 60, 60];
const UPPER: [u8; 3] = [25, 255, 255];
const STRICT_MISMATCH_THRESHOLD: f64 = 0.0;

fn synthetic_hsv(rows: i32, cols: i32) -> Result<Mat> {
    let mut hsv = Mat::new_rows_cols_with_default(rows, cols, core::CV_8UC3, Scalar::all(0.0))?;
    let px = hsv.data_typed_mut::<Vec3b>()?;

    for r in 0..rows as usize {
        for c in 0..cols as usize {
            let idx = r * cols as usize + c;
            let h = ((r * 17 + c * 13 + (idx % 11)) % 180) as u8;
            let s = ((r * 29 + c * 7 + 40) % 256) as u8;
            let v = ((r * 11 + c * 23 + 90) % 256) as u8;
            px[idx] = Vec3b::from([h, s, v]);
        }
    }

    Ok(hsv)
}

fn backend_kernel(backend: KernelBackend) -> Box<dyn HsvThresholdKernel> {
    match backend {
        KernelBackend::Scalar => Box::new(ScalarKernel::new()),
        KernelBackend::Avx2 => Box::new(AvxKernel::new()),
        KernelBackend::Neon => Box::new(NeonKernel::new()),
    }
}

fn assert_backend_matches_scalar(backend: KernelBackend, hsv: &Mat) -> Result<()> {
    let mut scalar_mask = Mat::default();
    ScalarKernel::new().threshold_hsv_to_mask(hsv, LOWER, UPPER, &mut scalar_mask)?;

    let mut backend_mask = Mat::default();
    backend_kernel(backend).threshold_hsv_to_mask(hsv, LOWER, UPPER, &mut backend_mask)?;

    let scalar_bytes = scalar_mask.data_typed::<u8>()?;
    let backend_bytes = backend_mask.data_typed::<u8>()?;
    let mismatch = mismatch_ratio(scalar_bytes, backend_bytes);

    assert!(
        mismatch <= STRICT_MISMATCH_THRESHOLD,
        "backend {:?} mismatch ratio {mismatch:.6} exceeds {:.6}",
        backend,
        STRICT_MISMATCH_THRESHOLD
    );

    Ok(())
}

#[test]
fn selected_backend_matches_scalar_on_deterministic_input() -> Result<()> {
    let hsv = synthetic_hsv(37, 53)?;
    let selected = vision::kernel_dispatch::KernelDispatch::new().backend();

    assert_backend_matches_scalar(selected, &hsv)
}

#[test]
fn dispatch_output_matches_scalar_on_deterministic_input() -> Result<()> {
    let hsv = synthetic_hsv(19, 41)?;
    let mut dispatch = vision::kernel_dispatch::KernelDispatch::new();

    let mut dispatch_mask = Mat::default();
    dispatch.threshold_hsv_to_mask(&hsv, LOWER, UPPER, &mut dispatch_mask)?;

    let mut scalar_mask = Mat::default();
    ScalarKernel::new().threshold_hsv_to_mask(&hsv, LOWER, UPPER, &mut scalar_mask)?;

    let dispatch_bytes = dispatch_mask.data_typed::<u8>()?;
    let scalar_bytes = scalar_mask.data_typed::<u8>()?;
    let mismatch = mismatch_ratio(dispatch_bytes, scalar_bytes);

    assert!(
        mismatch <= STRICT_MISMATCH_THRESHOLD,
        "dispatch mismatch ratio {mismatch:.6} exceeds {:.6}",
        STRICT_MISMATCH_THRESHOLD
    );

    Ok(())
}

#[test]
fn scalar_backend_matches_scalar_baseline() -> Result<()> {
    let hsv = synthetic_hsv(23, 35)?;
    assert_backend_matches_scalar(KernelBackend::Scalar, &hsv)
}

#[test]
fn avx2_backend_matches_scalar_baseline() -> Result<()> {
    let hsv = synthetic_hsv(29, 31)?;
    assert_backend_matches_scalar(KernelBackend::Avx2, &hsv)
}

#[test]
fn neon_backend_matches_scalar_baseline() -> Result<()> {
    let hsv = synthetic_hsv(17, 47)?;
    assert_backend_matches_scalar(KernelBackend::Neon, &hsv)
}
