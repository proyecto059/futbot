use anyhow::{anyhow, Result};
use opencv::{
    core::{self, Mat, Point, Point2f, Scalar, Size, Vector},
    imgproc,
    prelude::*,
};
use std::sync::OnceLock;

use crate::config::{
    BgrThresholds, BORDER_REJECT_PX, MIN_BALL_RADIUS, MIN_CONTOUR_AREA, MORPH_DILATE_SIZE,
    MORPH_OPEN_SIZE, PARTIAL_CIRCULARITY_MIN,
};
use crate::vision::kernel::fused_bgr_threshold::threshold_bgr_to_mask_fused;

struct BgrMorphKernels {
    open: Mat,
    dilate: Mat,
}

static BGR_MORPH_KERNELS: OnceLock<Result<BgrMorphKernels, String>> = OnceLock::new();

fn morphology_kernels() -> Result<(Mat, Mat)> {
    let cached = BGR_MORPH_KERNELS.get_or_init(|| {
        let open = imgproc::get_structuring_element(
            imgproc::MORPH_ELLIPSE,
            Size::new(MORPH_OPEN_SIZE, MORPH_OPEN_SIZE),
            Point::new(-1, -1),
        )
        .map_err(|e| e.to_string())?;
        let dilate = imgproc::get_structuring_element(
            imgproc::MORPH_ELLIPSE,
            Size::new(MORPH_DILATE_SIZE, MORPH_DILATE_SIZE),
            Point::new(-1, -1),
        )
        .map_err(|e| e.to_string())?;
        Ok(BgrMorphKernels { open, dilate })
    });

    match cached {
        Ok(k) => Ok((k.open.clone(), k.dilate.clone())),
        Err(msg) => Err(anyhow!(
            "failed to initialize BGR morphology kernels: {msg}"
        )),
    }
}

#[inline]
fn near_border(cx: f32, cy: f32, w: i32, h: i32) -> bool {
    let b = BORDER_REJECT_PX as f32;
    cx < b || cy < b || cx > (w as f32 - b) || cy > (h as f32 - b)
}

pub fn detect_ball_bgr(frame: &Mat, thresholds: BgrThresholds) -> Result<Option<(i32, i32, i32)>> {
    let mut mask = Mat::default();
    build_bgr_mask(
        frame,
        thresholds,
        &mut mask,
        crate::config::vision_fused_enabled(),
    )?;
    detect_from_mask(&mask)
}

fn build_bgr_mask(
    frame: &Mat,
    thresholds: BgrThresholds,
    out_mask: &mut Mat,
    use_fused: bool,
) -> Result<()> {
    if use_fused {
        return threshold_bgr_to_mask_fused(frame, thresholds, out_mask);
    }

    let rows = frame.rows();
    let cols = frame.cols();
    ensure_mask(rows, cols, out_mask)?;

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

fn detect_from_mask(mask: &Mat) -> Result<Option<(i32, i32, i32)>> {
    let (kopen, kdilate) = morphology_kernels()?;

    let mut opened = Mat::default();
    imgproc::morphology_ex_def(mask, &mut opened, imgproc::MORPH_OPEN, &kopen)?;

    let mut dilated = Mat::default();
    imgproc::dilate_def(&opened, &mut dilated, &kdilate)?;

    let mut contours: Vector<Vector<Point>> = Vector::new();
    imgproc::find_contours_def(
        &dilated,
        &mut contours,
        imgproc::RETR_EXTERNAL,
        imgproc::CHAIN_APPROX_SIMPLE,
    )?;

    let w = mask.cols();
    let h = mask.rows();
    let mut best: Option<(f64, i32, i32, i32)> = None;

    for cnt in contours.iter() {
        let area = imgproc::contour_area_def(&cnt)?;
        if area < MIN_CONTOUR_AREA {
            continue;
        }

        let perim = imgproc::arc_length(&cnt, true)?;
        if perim < 1e-6 {
            continue;
        }

        let circularity = 4.0 * std::f64::consts::PI * area / (perim * perim);
        if circularity < PARTIAL_CIRCULARITY_MIN {
            continue;
        }

        let mut center = Point2f::default();
        let mut radius = 0f32;
        imgproc::min_enclosing_circle(&cnt, &mut center, &mut radius)?;

        if radius < MIN_BALL_RADIUS {
            continue;
        }
        if near_border(center.x, center.y, w, h) {
            continue;
        }

        if best.map_or(true, |(best_area, _, _, _)| area > best_area) {
            best = Some((area, center.x as i32, center.y as i32, radius as i32));
        }
    }

    Ok(best.map(|(_, cx, cy, r)| (cx, cy, r)))
}
