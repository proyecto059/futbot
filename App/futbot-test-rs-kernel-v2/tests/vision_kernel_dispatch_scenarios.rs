use anyhow::Result;
use opencv::core::{self, Mat, Scalar, Vec3b};
use opencv::prelude::*;

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

use kernel::{HsvThresholdKernel, KernelBackend};
use kernel::scalar_kernel::ScalarKernel;
use kernel_dispatch::KernelDispatch;

struct ZeroKernel;

impl HsvThresholdKernel for ZeroKernel {
    fn backend(&self) -> KernelBackend {
        KernelBackend::Avx2
    }

    fn threshold_hsv_to_mask(
        &self,
        hsv: &Mat,
        _lower: [u8; 3],
        _upper: [u8; 3],
        out_mask: &mut Mat,
    ) -> Result<()> {
        *out_mask = Mat::new_rows_cols_with_default(
            hsv.rows(),
            hsv.cols(),
            core::CV_8UC1,
            Scalar::all(0.0),
        )?;
        Ok(())
    }
}

fn tiny_hsv() -> Result<Mat> {
    let mut hsv = Mat::new_rows_cols_with_default(1, 2, core::CV_8UC3, Scalar::all(0.0))?;
    let px = hsv.data_typed_mut::<Vec3b>()?;
    px[0] = Vec3b::from([10, 100, 100]);
    px[1] = Vec3b::from([150, 100, 100]);
    Ok(hsv)
}

#[test]
fn validation_disabled_keeps_backend_output() -> Result<()> {
    let hsv = tiny_hsv()?;
    let mut out = Mat::default();
    let mut dispatch = KernelDispatch {
        kernel: Box::new(ZeroKernel),
        scalar: ScalarKernel::new(),
        validation_enabled: false,
        mismatch_threshold: 0.0,
        force_scalar_fallback: false,
    };

    dispatch.threshold_hsv_to_mask(&hsv, [5, 50, 50], [20, 255, 255], &mut out)?;
    let bytes = out.data_typed::<u8>()?;
    assert_eq!(bytes, &[0, 0]);
    assert!(!dispatch.force_scalar_fallback);
    Ok(())
}

#[test]
fn validation_enables_scalar_fallback_on_high_mismatch() -> Result<()> {
    let hsv = tiny_hsv()?;
    let mut out = Mat::default();
    let mut dispatch = KernelDispatch {
        kernel: Box::new(ZeroKernel),
        scalar: ScalarKernel::new(),
        validation_enabled: true,
        mismatch_threshold: 0.1,
        force_scalar_fallback: false,
    };

    dispatch.threshold_hsv_to_mask(&hsv, [5, 50, 50], [20, 255, 255], &mut out)?;
    let bytes = out.data_typed::<u8>()?;
    assert_eq!(bytes, &[255, 0]);
    assert!(dispatch.force_scalar_fallback);
    Ok(())
}
