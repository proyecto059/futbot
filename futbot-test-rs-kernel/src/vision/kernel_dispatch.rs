use anyhow::Result;
use opencv::{core::Mat, prelude::*};

use crate::vision::kernel::{
    avx_kernel::AvxKernel,
    scalar_kernel::ScalarKernel,
    validate::{env_f64, env_flag_enabled, mismatch_ratio},
    HsvThresholdKernel, KernelBackend,
};

#[cfg(target_arch = "aarch64")]
use crate::vision::kernel::neon_kernel::NeonKernel;

pub struct KernelDispatch {
    kernel: Box<dyn HsvThresholdKernel>,
    scalar: ScalarKernel,
    validation_enabled: bool,
    mismatch_threshold: f64,
    force_scalar_fallback: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct KernelInfo {
    pub backend: KernelBackend,
    pub fallback: bool,
    pub validation_enabled: bool,
    pub mismatch_threshold: f64,
    pub forced_scalar_fallback: bool,
    pub fused_bgr_enabled: bool,
}

impl KernelDispatch {
    pub fn new() -> Self {
        let validation_enabled = env_flag_enabled("VISION_VALIDATE_KERNEL");
        let mismatch_threshold = env_f64("VISION_VALIDATE_MISMATCH_THRESHOLD", 0.03);
        Self {
            kernel: select_kernel(),
            scalar: ScalarKernel::new(),
            validation_enabled,
            mismatch_threshold,
            force_scalar_fallback: false,
        }
    }

    pub fn backend(&self) -> KernelBackend {
        self.kernel.backend()
    }

    pub fn info(&self) -> KernelInfo {
        KernelInfo {
            backend: self.kernel.backend(),
            fallback: self.kernel.is_fallback(),
            validation_enabled: self.validation_enabled,
            mismatch_threshold: self.mismatch_threshold,
            forced_scalar_fallback: self.force_scalar_fallback,
            fused_bgr_enabled: crate::config::vision_fused_enabled(),
        }
    }

    pub fn threshold_hsv_to_mask(
        &mut self,
        hsv: &Mat,
        lower: [u8; 3],
        upper: [u8; 3],
        out_mask: &mut Mat,
    ) -> Result<()> {
        if self.force_scalar_fallback || self.kernel.backend() == KernelBackend::Scalar {
            return self
                .scalar
                .threshold_hsv_to_mask(hsv, lower, upper, out_mask);
        }

        self.kernel
            .threshold_hsv_to_mask(hsv, lower, upper, out_mask)?;

        if !self.validation_enabled {
            return Ok(());
        }

        let mut scalar_mask = Mat::default();
        self.scalar
            .threshold_hsv_to_mask(hsv, lower, upper, &mut scalar_mask)?;

        let mismatch = mask_mismatch_ratio(out_mask, &scalar_mask)?;
        if mismatch > self.mismatch_threshold {
            log::warn!(
                "[vision] kernel mismatch ratio {:.4} exceeds {:.4}; forcing scalar fallback",
                mismatch,
                self.mismatch_threshold,
            );
            self.force_scalar_fallback = true;
            *out_mask = scalar_mask;
        }

        Ok(())
    }
}

impl Default for KernelDispatch {
    fn default() -> Self {
        Self::new()
    }
}

fn select_kernel() -> Box<dyn HsvThresholdKernel> {
    #[cfg(target_arch = "aarch64")]
    {
        if std::arch::is_aarch64_feature_detected!("neon") {
            return Box::new(NeonKernel::new());
        }
    }

    #[cfg(any(target_arch = "x86", target_arch = "x86_64"))]
    {
        if std::arch::is_x86_feature_detected!("avx2") {
            return Box::new(AvxKernel::new());
        }
    }

    Box::new(ScalarKernel::new())
}

fn mask_mismatch_ratio(mask_a: &Mat, mask_b: &Mat) -> Result<f64> {
    if mask_a.rows() != mask_b.rows() || mask_a.cols() != mask_b.cols() {
        return Ok(1.0);
    }

    if mask_a.is_continuous() && mask_b.is_continuous() {
        let a = mask_a.data_typed::<u8>()?;
        let b = mask_b.data_typed::<u8>()?;
        return Ok(mismatch_ratio(a, b));
    }

    let rows = mask_a.rows();
    let cols = mask_a.cols();
    let mut mismatch = 0usize;
    let mut total = 0usize;
    for r in 0..rows {
        for c in 0..cols {
            let a = *mask_a.at_2d::<u8>(r, c)?;
            let b = *mask_b.at_2d::<u8>(r, c)?;
            if a != b {
                mismatch += 1;
            }
            total += 1;
        }
    }

    if total == 0 {
        return Ok(0.0);
    }
    Ok(mismatch as f64 / total as f64)
}

#[cfg(test)]
mod tests {
    use super::*;
    use opencv::core::{self, Scalar, Vec3b};

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
}
