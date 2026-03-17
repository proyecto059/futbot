use anyhow::Result;
use opencv::{
    core::{self, Mat, Scalar, Vec3b},
    prelude::*,
};

use crate::config::BgrThresholds;

pub fn threshold_bgr_to_mask_fused(
    frame: &Mat,
    thresholds: BgrThresholds,
    out_mask: &mut Mat,
) -> Result<()> {
    let rows = frame.rows();
    let cols = frame.cols();
    ensure_mask(rows, cols, out_mask)?;

    if frame.typ() == core::CV_8UC3 && frame.is_continuous() && out_mask.is_continuous() {
        let src = frame.data_typed::<Vec3b>()?;
        let dst = out_mask.data_typed_mut::<u8>()?;
        for (px, out) in src.iter().zip(dst.iter_mut()) {
            let b = px[0] as i16;
            let g = px[1] as i16;
            let red = px[2] as i16;
            let keep = red >= thresholds.r_min as i16
                && g >= thresholds.g_min as i16
                && b <= thresholds.b_max as i16
                && (red - g) >= thresholds.rg_delta_min
                && (red - b) >= thresholds.rb_delta_min
                && (g - b) >= thresholds.gb_delta_min;
            *out = if keep { 255 } else { 0 };
        }
        return Ok(());
    }

    for r in 0..rows {
        for c in 0..cols {
            let px = *frame.at_2d::<core::Vec3b>(r, c)?;
            let b = px[0] as i16;
            let g = px[1] as i16;
            let red = px[2] as i16;

            let keep = red >= thresholds.r_min as i16
                && g >= thresholds.g_min as i16
                && b <= thresholds.b_max as i16
                && (red - g) >= thresholds.rg_delta_min
                && (red - b) >= thresholds.rb_delta_min
                && (g - b) >= thresholds.gb_delta_min;

            if keep {
                *out_mask.at_2d_mut::<u8>(r, c)? = 255;
            }
        }
    }

    Ok(())
}

fn ensure_mask(rows: i32, cols: i32, out_mask: &mut Mat) -> Result<()> {
    if out_mask.rows() == rows && out_mask.cols() == cols && out_mask.typ() == core::CV_8UC1 {
        out_mask.set_to(&Scalar::all(0.0), &Mat::default())?;
    } else {
        *out_mask = Mat::new_rows_cols_with_default(rows, cols, core::CV_8UC1, Scalar::all(0.0))?;
    }
    Ok(())
}
