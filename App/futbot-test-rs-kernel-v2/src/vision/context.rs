use anyhow::Result;
use opencv::{
    core::{self, Mat, Size, ToInputArray, Vector},
    imgproc,
    prelude::*,
};

use crate::config::*;
use crate::vision::kernel_dispatch::KernelDispatch;

pub struct VisionContext {
    kernel_dispatch: KernelDispatch,
    pub blurred: Mat,
    pub hsv: Mat,
    pub roi_blurred: Mat,
    pub roi_hsv: Mat,
    pub main_mask: Mat,
    pub seed_mask: Mat,
    pub adaptive_lower: [u8; 3],
    pub adaptive_seed_lower: [u8; 3],
}

impl VisionContext {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn prepare_in_place(&mut self, frame: &Mat) -> Result<()> {
        let processed: Mat;
        let preprocess_src: &Mat = if CLAHE_ENABLED {
            let mean = core::mean_def(frame)?;
            let brightness = (mean[0] + mean[1] + mean[2]) / 3.0;
            if brightness < CLAHE_BRIGHTNESS_THRESHOLD {
                processed = apply_clahe(frame)?;
                &processed
            } else {
                frame
            }
        } else {
            frame
        };

        imgproc::gaussian_blur_def(preprocess_src, &mut self.blurred, Size::new(11, 11), 0.0)?;
        imgproc::cvt_color_def(&self.blurred, &mut self.hsv, imgproc::COLOR_BGR2HSV)?;

        let (adaptive_lower, adaptive_seed_lower) = adaptive_lowers_from_hsv(&self.hsv);
        self.adaptive_lower = adaptive_lower;
        self.adaptive_seed_lower = adaptive_seed_lower;

        self.kernel_dispatch.threshold_hsv_to_mask(
            &self.hsv,
            self.adaptive_lower,
            HSV_UPPER,
            &mut self.main_mask,
        )?;

        self.kernel_dispatch.threshold_hsv_to_mask(
            &self.hsv,
            self.adaptive_seed_lower,
            SEED_UPPER,
            &mut self.seed_mask,
        )?;

        Ok(())
    }

    pub fn prepare_roi_hsv_in_place(
        &mut self,
        frame: &Mat,
        roi: core::Rect,
    ) -> Result<([u8; 3], [u8; 3])> {
        let roi_ref = frame.roi(roi)?;

        if CLAHE_ENABLED {
            let mean = core::mean_def(&roi_ref)?;
            let brightness = mean[0] + mean[1] + mean[2];
            if brightness < CLAHE_BRIGHTNESS_THRESHOLD {
                let processed = apply_clahe(&roi_ref)?;
                imgproc::gaussian_blur_def(
                    &processed,
                    &mut self.roi_blurred,
                    Size::new(11, 11),
                    0.0,
                )?;
            } else {
                imgproc::gaussian_blur_def(
                    &roi_ref,
                    &mut self.roi_blurred,
                    Size::new(11, 11),
                    0.0,
                )?;
            }
        } else {
            imgproc::gaussian_blur_def(&roi_ref, &mut self.roi_blurred, Size::new(11, 11), 0.0)?;
        }
        imgproc::cvt_color_def(&self.roi_blurred, &mut self.roi_hsv, imgproc::COLOR_BGR2HSV)?;
        Ok(adaptive_lowers_from_hsv(&self.roi_hsv))
    }

    pub fn prepare(frame: &Mat) -> Result<Self> {
        let mut ctx = Self::new();
        ctx.prepare_in_place(frame)?;
        Ok(ctx)
    }
}

impl Default for VisionContext {
    fn default() -> Self {
        Self {
            kernel_dispatch: KernelDispatch::new(),
            blurred: Mat::default(),
            hsv: Mat::default(),
            roi_blurred: Mat::default(),
            roi_hsv: Mat::default(),
            main_mask: Mat::default(),
            seed_mask: Mat::default(),
            adaptive_lower: HSV_LOWER,
            adaptive_seed_lower: SEED_LOWER,
        }
    }
}

pub fn selected_kernel_info() -> crate::vision::kernel_dispatch::KernelInfo {
    KernelDispatch::new().info()
}

pub fn adaptive_lowers_from_hsv<T>(hsv: &T) -> ([u8; 3], [u8; 3])
where
    T: MatTraitConst,
{
    let v_floor = compute_adaptive_v_floor(hsv);
    (
        [HSV_LOWER[0], HSV_LOWER[1], v_floor as u8],
        [SEED_LOWER[0], SEED_LOWER[1], v_floor as u8],
    )
}

/// Normalize illumination via CLAHE on L channel of LAB color space.
fn apply_clahe<T>(frame: &T) -> Result<Mat>
where
    T: ToInputArray,
{
    let mut lab = Mat::default();
    imgproc::cvt_color_def(frame, &mut lab, imgproc::COLOR_BGR2Lab)?;

    let mut channels: Vector<Mat> = Vector::new();
    core::split(&lab, &mut channels)?;

    let mut clahe = imgproc::create_clahe(
        CLAHE_CLIP_LIMIT,
        Size::new(CLAHE_TILE_GRID, CLAHE_TILE_GRID),
    )?;
    let mut l_eq = Mat::default();
    clahe.apply(&channels.get(0)?, &mut l_eq)?;
    channels.set(0, l_eq)?;

    let mut merged = Mat::default();
    core::merge(&channels, &mut merged)?;

    let mut bgr = Mat::default();
    imgproc::cvt_color_def(&merged, &mut bgr, imgproc::COLOR_Lab2BGR)?;
    Ok(bgr)
}

/// Compute adaptive V floor from orange-hue pixels in the current HSV frame.
fn compute_adaptive_v_floor<T>(hsv: &T) -> i32
where
    T: MatTraitConst,
{
    if hsv.typ() != core::CV_8UC3 {
        return HSV_LOWER[2] as i32;
    }

    let rows = hsv.rows() as usize;
    let cols = hsv.cols() as usize;
    let mut v_hist = [0u32; 256];
    let mut sample_count: usize = 0;

    for r in 0..rows {
        for c in 0..cols {
            let px = match hsv.at_2d::<core::Vec3b>(r as i32, c as i32) {
                Ok(px_ref) => *px_ref,
                Err(_) => return HSV_LOWER[2] as i32,
            };

            let h = px[0];
            let s = px[1];
            let v = px[2];
            if h <= HSV_UPPER[0] && s >= HSV_ADAPTIVE_S_SAMPLE {
                v_hist[v as usize] += 1;
                sample_count += 1;
            }
        }
    }

    if sample_count >= 5 {
        let target =
            ((HSV_ADAPTIVE_V_PCTILE / 100.0) * (sample_count.saturating_sub(1) as f32)) as usize;
        let mut cumulative: usize = 0;
        let mut v_ref: u8 = HSV_LOWER[2];

        for (v, count) in v_hist.iter().enumerate() {
            cumulative += *count as usize;
            if cumulative > target {
                v_ref = v as u8;
                break;
            }
        }

        ((v_ref as f32 * HSV_ADAPTIVE_V_RATIO) as i32).max(HSV_ADAPTIVE_V_MIN)
    } else {
        HSV_LOWER[2] as i32
    }
}
