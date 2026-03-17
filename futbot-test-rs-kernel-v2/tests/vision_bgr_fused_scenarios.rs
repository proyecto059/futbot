use anyhow::Result;
use opencv::core::{self, Mat, Scalar, Vec3b};
use opencv::prelude::*;

#[path = "../src/config.rs"]
mod config;

#[path = "../src/vision/kernel/fused_bgr_threshold.rs"]
mod fused;

use config::BgrThresholds;
use fused::threshold_bgr_to_mask_fused;

#[test]
fn fused_threshold_accepts_cv8uc3_and_outputs_cv8uc1() -> Result<()> {
    let mut frame = Mat::new_rows_cols_with_default(1, 2, core::CV_8UC3, Scalar::all(0.0))?;
    *frame.at_2d_mut::<Vec3b>(0, 0)? = Vec3b::from([20, 120, 200]);
    *frame.at_2d_mut::<Vec3b>(0, 1)? = Vec3b::from([200, 10, 10]);

    let thresholds = BgrThresholds {
        r_min: 120,
        g_min: 55,
        b_max: 140,
        rg_delta_min: 25,
        rb_delta_min: 45,
        gb_delta_min: 5,
    };

    let mut mask = Mat::default();
    threshold_bgr_to_mask_fused(&frame, thresholds, &mut mask)?;

    assert_eq!(mask.typ(), core::CV_8UC1);
    let px = mask.data_typed::<u8>()?;
    assert_eq!(px, &[255, 0]);
    Ok(())
}
