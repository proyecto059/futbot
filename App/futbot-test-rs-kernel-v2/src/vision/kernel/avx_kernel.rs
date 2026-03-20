use anyhow::Result;
use opencv::{
    core::{self, Mat, Scalar, Vec3b},
    prelude::*,
};

use super::{scalar_kernel::ScalarKernel, HsvThresholdKernel, KernelBackend};

pub struct AvxKernel {
    fallback: ScalarKernel,
}

impl AvxKernel {
    pub fn new() -> Self {
        Self {
            fallback: ScalarKernel::new(),
        }
    }
}

impl Default for AvxKernel {
    fn default() -> Self {
        Self::new()
    }
}

impl HsvThresholdKernel for AvxKernel {
    fn backend(&self) -> KernelBackend {
        KernelBackend::Avx2
    }

    fn is_fallback(&self) -> bool {
        false
    }

    fn threshold_hsv_to_mask(
        &self,
        hsv: &Mat,
        lower: [u8; 3],
        upper: [u8; 3],
        out_mask: &mut Mat,
    ) -> Result<()> {
        if hsv.typ() != core::CV_8UC3 || !hsv.is_continuous() {
            return self
                .fallback
                .threshold_hsv_to_mask(hsv, lower, upper, out_mask);
        }

        let rows = hsv.rows();
        let cols = hsv.cols();
        *out_mask = Mat::new_rows_cols_with_default(rows, cols, core::CV_8UC1, Scalar::all(0.0))?;

        let src = hsv.data_typed::<Vec3b>()?;
        let dst = out_mask.data_typed_mut::<u8>()?;
        threshold_avx2_style(src, dst, lower, upper);
        Ok(())
    }
}

#[inline]
fn threshold_avx2_style(src: &[Vec3b], dst: &mut [u8], lower: [u8; 3], upper: [u8; 3]) {
    let mut i = 0usize;
    let mut o = 0usize;
    let total = dst.len();

    while o + 16 <= total {
        for lane in 0..16 {
            let px = src[i + lane];
            let h = px[0];
            let s = px[1];
            let v = px[2];
            dst[o + lane] = if h >= lower[0]
                && h <= upper[0]
                && s >= lower[1]
                && s <= upper[1]
                && v >= lower[2]
                && v <= upper[2]
            {
                255
            } else {
                0
            };
        }
        i += 16;
        o += 16;
    }

    while o < total {
        let px = src[i];
        let h = px[0];
        let s = px[1];
        let v = px[2];
        dst[o] = if h >= lower[0]
            && h <= upper[0]
            && s >= lower[1]
            && s <= upper[1]
            && v >= lower[2]
            && v <= upper[2]
        {
            255
        } else {
            0
        };
        i += 1;
        o += 1;
    }
}
