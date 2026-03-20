use anyhow::Result;
use opencv::core::{self, Mat, Scalar};

use super::{HsvThresholdKernel, KernelBackend};

pub struct ScalarKernel;

impl ScalarKernel {
    pub fn new() -> Self {
        Self
    }
}

impl Default for ScalarKernel {
    fn default() -> Self {
        Self::new()
    }
}

impl HsvThresholdKernel for ScalarKernel {
    fn backend(&self) -> KernelBackend {
        KernelBackend::Scalar
    }

    fn threshold_hsv_to_mask(
        &self,
        hsv: &Mat,
        lower: [u8; 3],
        upper: [u8; 3],
        out_mask: &mut Mat,
    ) -> Result<()> {
        let lower_s = Scalar::new(lower[0] as f64, lower[1] as f64, lower[2] as f64, 0.0);
        let upper_s = Scalar::new(upper[0] as f64, upper[1] as f64, upper[2] as f64, 0.0);
        core::in_range(hsv, &lower_s, &upper_s, out_mask)?;
        Ok(())
    }
}
