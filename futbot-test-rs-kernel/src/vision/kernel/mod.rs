use anyhow::Result;
use opencv::core::Mat;

pub mod avx_kernel;
pub mod fused_bgr_threshold;
pub mod neon_kernel;
pub mod scalar_kernel;
pub mod validate;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelBackend {
    Scalar,
    Neon,
    Avx2,
}

pub trait HsvThresholdKernel: Send + Sync {
    fn backend(&self) -> KernelBackend;

    fn is_fallback(&self) -> bool {
        false
    }

    fn threshold_hsv_to_mask(
        &self,
        hsv: &Mat,
        lower: [u8; 3],
        upper: [u8; 3],
        out_mask: &mut Mat,
    ) -> Result<()>;
}
