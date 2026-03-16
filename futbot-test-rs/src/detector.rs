//! Ball detection — mirrors detector.py exactly.
//!
//! Detection pipeline (in order of priority):
//!   1. HSV pass with circularity filter
//!   2. Partial contour pass (ellipse fitting for arcs)
//!   3. Seed detector (high-purity tiny balls)
//!
//! All passes use adaptive V floor computed from the current frame.

use anyhow::Result;
use opencv::{
    core::{self, Mat, Point, Point2f, Rect, Scalar, Size, Vector, CV_32F, CV_8U},
    imgproc,
    prelude::*,
};

use crate::config::*;

// ── Owned Mat helper (safe alternative to new_rows_cols_with_data_unsafe) ────

fn mat_f32(rows: i32, cols: i32, data: &[f32]) -> Result<Mat> {
    let mut m = Mat::zeros(rows, cols, CV_32F)?.to_mat()?;
    for r in 0..rows as usize {
        for c in 0..cols as usize {
            *m.at_2d_mut::<f32>(r as i32, c as i32)? = data[r * cols as usize + c];
        }
    }
    Ok(m)
}

// ── Pre-built morphology kernels ──────────────────────────────────────────────

fn kernel_open() -> Mat {
    imgproc::get_structuring_element(
        imgproc::MORPH_ELLIPSE,
        Size::new(MORPH_OPEN_SIZE, MORPH_OPEN_SIZE),
        Point::new(-1, -1),
    )
    .unwrap()
}

fn kernel_dilate() -> Mat {
    imgproc::get_structuring_element(
        imgproc::MORPH_ELLIPSE,
        Size::new(MORPH_DILATE_SIZE, MORPH_DILATE_SIZE),
        Point::new(-1, -1),
    )
    .unwrap()
}

// ── CLAHE ─────────────────────────────────────────────────────────────────────

/// Normalize illumination via CLAHE on L channel of LAB color space.
fn apply_clahe(frame: &Mat) -> Result<Mat> {
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

/// Conditionally apply CLAHE + Gaussian blur, return (processed_bgr, hsv).
fn preprocess_frame(frame: &Mat) -> Result<(Mat, Mat)> {
    let processed = if CLAHE_ENABLED {
        let mean = core::mean_def(frame)?;
        let brightness = mean[0] + mean[1] + mean[2];
        if brightness < CLAHE_BRIGHTNESS_THRESHOLD {
            apply_clahe(frame)?
        } else {
            frame.clone()
        }
    } else {
        frame.clone()
    };

    let mut blurred = Mat::default();
    imgproc::gaussian_blur_def(&processed, &mut blurred, Size::new(11, 11), 0.0)?;

    let mut hsv = Mat::default();
    imgproc::cvt_color_def(&blurred, &mut hsv, imgproc::COLOR_BGR2HSV)?;

    Ok((blurred, hsv))
}

/// Compute adaptive V floor from orange-hue pixels in the current HSV frame.
fn compute_adaptive_v_floor(hsv: &Mat) -> i32 {
    let rows = hsv.rows() as usize;
    let cols = hsv.cols() as usize;
    let mut v_samples: Vec<f32> = Vec::with_capacity(512);

    for r in 0..rows {
        for c in 0..cols {
            let px: core::Vec3b = *hsv.at_2d(r as i32, c as i32).unwrap();
            let h = px[0];
            let s = px[1];
            let v = px[2];
            if h <= HSV_UPPER[0] && s >= HSV_ADAPTIVE_S_SAMPLE {
                v_samples.push(v as f32);
            }
        }
    }

    if v_samples.len() >= 5 {
        v_samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let idx = ((HSV_ADAPTIVE_V_PCTILE / 100.0) * (v_samples.len() - 1) as f32) as usize;
        let v_ref = v_samples[idx.min(v_samples.len() - 1)];
        ((v_ref * HSV_ADAPTIVE_V_RATIO) as i32).max(HSV_ADAPTIVE_V_MIN)
    } else {
        HSV_LOWER[2] as i32
    }
}

#[inline]
fn near_border(cx: f32, cy: f32, w: i32, h: i32) -> bool {
    let b = BORDER_REJECT_PX as f32;
    cx < b || cy < b || cx > (w as f32 - b) || cy > (h as f32 - b)
}

/// Main HSV detection pass with circularity filter.
fn hsv_pass(
    hsv: &Mat,
    lower: [u8; 3],
    upper: [u8; 3],
    min_circ: f64,
) -> Result<Option<(i32, i32, i32)>> {
    let lower_s = Scalar::new(lower[0] as f64, lower[1] as f64, lower[2] as f64, 0.0);
    let upper_s = Scalar::new(upper[0] as f64, upper[1] as f64, upper[2] as f64, 0.0);

    let mut mask = Mat::default();
    core::in_range(hsv, &lower_s, &upper_s, &mut mask)?;

    let kopen = kernel_open();
    let kdilate = kernel_dilate();

    let mut opened = Mat::default();
    imgproc::morphology_ex_def(&mask, &mut opened, imgproc::MORPH_OPEN, &kopen)?;

    let mut dilated = Mat::default();
    imgproc::dilate_def(&opened, &mut dilated, &kdilate)?;

    let mut contours: Vector<Vector<Point>> = Vector::new();
    imgproc::find_contours_def(
        &dilated,
        &mut contours,
        imgproc::RETR_EXTERNAL,
        imgproc::CHAIN_APPROX_SIMPLE,
    )?;

    let w = hsv.cols();
    let h = hsv.rows();
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
        if circularity < min_circ {
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

        if best.map_or(true, |(a, _, _, _)| area > a) {
            best = Some((area, center.x as i32, center.y as i32, radius as i32));
        }
    }

    Ok(best.map(|(_, cx, cy, r)| (cx, cy, r)))
}

/// Partial contour pass — ellipse fitting for arcs/semicircles.
fn partial_contour_pass(hsv: &Mat, lower: [u8; 3]) -> Result<Option<(i32, i32, i32)>> {
    let lower_s = Scalar::new(lower[0] as f64, lower[1] as f64, lower[2] as f64, 0.0);
    let upper_s = Scalar::new(HSV_UPPER[0] as f64, HSV_UPPER[1] as f64, HSV_UPPER[2] as f64, 0.0);

    let mut mask = Mat::default();
    core::in_range(hsv, &lower_s, &upper_s, &mut mask)?;

    let kopen = kernel_open();
    let kdilate = kernel_dilate();

    let mut opened = Mat::default();
    imgproc::morphology_ex_def(&mask, &mut opened, imgproc::MORPH_OPEN, &kopen)?;

    let mut dilated = Mat::default();
    imgproc::dilate_def(&opened, &mut dilated, &kdilate)?;

    let mut contours: Vector<Vector<Point>> = Vector::new();
    imgproc::find_contours_def(
        &dilated,
        &mut contours,
        imgproc::RETR_EXTERNAL,
        imgproc::CHAIN_APPROX_SIMPLE,
    )?;

    let w = hsv.cols();
    let h = hsv.rows();

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

        if circularity < PARTIAL_CIRCULARITY_MIN || circularity >= MIN_CIRCULARITY {
            continue;
        }
        if cnt.len() < 5 {
            continue;
        }

        let ellipse = match imgproc::fit_ellipse(&cnt) {
            Ok(e) => e,
            Err(_) => continue,
        };

        let (ma, mi) = (ellipse.size.width, ellipse.size.height);
        let (major, minor) = if ma >= mi { (ma, mi) } else { (mi, ma) };
        if major < 1e-6 {
            continue;
        }
        let ratio = minor / major;
        if ratio < PARTIAL_ELLIPSE_RATIO {
            continue;
        }

        let radius = major / 2.0;
        if radius < MIN_BALL_RADIUS {
            continue;
        }

        let cx = ellipse.center.x;
        let cy = ellipse.center.y;
        if near_border(cx, cy, w, h) {
            continue;
        }

        return Ok(Some((cx as i32, cy as i32, radius as i32)));
    }

    Ok(None)
}

/// Seed detector for tiny 8-15 px balls (high-purity color).
fn seed_pass(hsv: &Mat, seed_lower: [u8; 3]) -> Result<Option<(i32, i32, i32)>> {
    let lower_s = Scalar::new(
        seed_lower[0] as f64,
        seed_lower[1] as f64,
        seed_lower[2] as f64,
        0.0,
    );
    let upper_s = Scalar::new(
        SEED_UPPER[0] as f64,
        SEED_UPPER[1] as f64,
        SEED_UPPER[2] as f64,
        0.0,
    );

    let mut seed_mask = Mat::default();
    core::in_range(hsv, &lower_s, &upper_s, &mut seed_mask)?;

    let k3 = imgproc::get_structuring_element(
        imgproc::MORPH_ELLIPSE,
        Size::new(3, 3),
        Point::new(-1, -1),
    )?;
    let mut eroded = Mat::default();
    imgproc::erode_def(&seed_mask, &mut eroded, &k3)?;

    let mut contours: Vector<Vector<Point>> = Vector::new();
    imgproc::find_contours_def(
        &eroded,
        &mut contours,
        imgproc::RETR_EXTERNAL,
        imgproc::CHAIN_APPROX_SIMPLE,
    )?;

    let w = hsv.cols();
    let h = hsv.rows();
    let mut best: Option<(f64, i32, i32, i32)> = None;

    for cnt in contours.iter() {
        let area = imgproc::contour_area_def(&cnt)?;
        if area < SEED_MIN_PIXELS || area > SEED_MAX_AREA {
            continue;
        }

        let mut center = Point2f::default();
        let mut radius = 0f32;
        imgproc::min_enclosing_circle(&cnt, &mut center, &mut radius)?;

        if near_border(center.x, center.y, w, h) {
            continue;
        }

        if best.map_or(true, |(a, _, _, _)| area > a) {
            let r = radius.max(MIN_BALL_RADIUS) as i32;
            best = Some((area, center.x as i32, center.y as i32, r));
        }
    }

    Ok(best.map(|(_, cx, cy, r)| (cx, cy, r)))
}

/// Core detection: tries all passes on a given (sub)frame.
fn detect_in_frame(frame: &Mat) -> Result<Option<(i32, i32, i32)>> {
    let (_processed, hsv) = preprocess_frame(frame)?;

    let v_floor = compute_adaptive_v_floor(&hsv);
    let adaptive_lower = [HSV_LOWER[0], HSV_LOWER[1], v_floor as u8];
    let adaptive_seed_lower = [SEED_LOWER[0], SEED_LOWER[1], v_floor as u8];

    if let Some(det) = hsv_pass(&hsv, adaptive_lower, HSV_UPPER, MIN_CIRCULARITY)? {
        return Ok(Some(det));
    }

    if let Some(det) = partial_contour_pass(&hsv, adaptive_lower)? {
        return Ok(Some(det));
    }

    if let Some(det) = seed_pass(&hsv, adaptive_seed_lower)? {
        return Ok(Some(det));
    }

    Ok(None)
}

/// Main public API for ball detection with optional ROI search.
pub fn detect_ball(
    frame: &Mat,
    roi_center: Option<(i32, i32)>,
) -> Result<Option<(i32, i32, i32)>> {
    if let Some((rx, ry)) = roi_center {
        let half = DETECT_ROI_SIZE / 2;
        let x1 = (rx - half).max(0);
        let y1 = (ry - half).max(0);
        let x2 = (rx + half).min(frame.cols());
        let y2 = (ry + half).min(frame.rows());

        if x2 > x1 && y2 > y1 {
            let roi_ref = frame.roi(Rect::new(x1, y1, x2 - x1, y2 - y1))?;
            let roi_mat = roi_ref.clone_pointee();
            if let Some((dx, dy, r)) = detect_in_frame(&roi_mat)? {
                return Ok(Some((dx + x1, dy + y1, r)));
            }
        }
    }

    detect_in_frame(frame)
}

/// Extract ROI around ball center, resized to ROI_SIZE×ROI_SIZE.
pub fn extract_roi(frame: &Mat, cx: i32, cy: i32, radius: i32) -> Result<Mat> {
    let half = radius + ROI_PADDING;
    let x1 = (cx - half).max(0);
    let y1 = (cy - half).max(0);
    let x2 = (cx + half).min(frame.cols());
    let y2 = (cy + half).min(frame.rows());

    let roi_mat = if x2 > x1 && y2 > y1 {
        let roi_ref = frame.roi(Rect::new(x1, y1, x2 - x1, y2 - y1))?;
        roi_ref.clone_pointee()
    } else {
        frame.clone()
    };

    let mut out = Mat::default();
    imgproc::resize_def(&roi_mat, &mut out, Size::new(ROI_SIZE, ROI_SIZE))?;
    Ok(out)
}

// ── BallAccumulator ───────────────────────────────────────────────────────────

pub struct BallAccumulator {
    acc: Mat,
}

impl BallAccumulator {
    pub fn new() -> Self {
        let acc = Mat::zeros(FRAME_HEIGHT, FRAME_WIDTH, CV_32F)
            .unwrap()
            .to_mat()
            .unwrap();
        BallAccumulator { acc }
    }

    pub fn update(&mut self, seed_mask: &Mat) -> Option<(i32, i32, i32)> {
        // Decay: acc = acc * ACCUM_DECAY
        let acc_prev = self.acc.clone();
        core::multiply_def(
            &acc_prev,
            &Scalar::new(ACCUM_DECAY as f64, 0.0, 0.0, 0.0),
            &mut self.acc,
        )
        .ok()?;

        // Add: binarize seed_mask (u8 → float) and add to acc
        let mut mask_f32 = Mat::default();
        seed_mask
            .convert_to(&mut mask_f32, CV_32F, 1.0 / 255.0, 0.0)
            .ok()?;
        let mut bin = Mat::default();
        imgproc::threshold(&mask_f32, &mut bin, 0.0, 1.0, imgproc::THRESH_BINARY).ok()?;

        let acc_prev2 = self.acc.clone();
        core::add_def(&acc_prev2, &bin, &mut self.acc).ok()?;

        // Threshold: hot = acc > ACCUM_THRESHOLD
        let mut hot_f32 = Mat::default();
        imgproc::threshold(
            &self.acc,
            &mut hot_f32,
            ACCUM_THRESHOLD as f64,
            255.0,
            imgproc::THRESH_BINARY,
        )
        .ok()?;
        let mut hot = Mat::default();
        hot_f32.convert_to(&mut hot, CV_8U, 1.0, 0.0).ok()?;

        let mut contours: Vector<Vector<Point>> = Vector::new();
        imgproc::find_contours_def(
            &hot,
            &mut contours,
            imgproc::RETR_EXTERNAL,
            imgproc::CHAIN_APPROX_SIMPLE,
        )
        .ok()?;

        let w = self.acc.cols();
        let h = self.acc.rows();
        let mut best: Option<(f32, i32, i32, i32)> = None;

        for cnt in contours.iter() {
            let area = imgproc::contour_area_def(&cnt).unwrap_or(0.0);
            if area < ACCUM_MIN_AREA {
                continue;
            }

            let mut center = Point2f::default();
            let mut radius = 0f32;
            if imgproc::min_enclosing_circle(&cnt, &mut center, &mut radius).is_err() {
                continue;
            }
            if near_border(center.x, center.y, w, h) {
                continue;
            }

            let cx = center.x as i32;
            let cy = center.y as i32;
            let nx1 = (cx - 3).max(0);
            let ny1 = (cy - 3).max(0);
            let nx2 = (cx + 4).min(w);
            let ny2 = (cy + 4).min(h);

            let score: f32 = if nx2 > nx1 && ny2 > ny1 {
                let patch_ref = self.acc.roi(Rect::new(nx1, ny1, nx2 - nx1, ny2 - ny1)).ok();
                patch_ref
                    .and_then(|p| {
                        let mut max_val = 0f64;
                        core::min_max_loc(
                            &p.clone_pointee(),
                            None,
                            Some(&mut max_val),
                            None,
                            None,
                            &Mat::default(),
                        )
                        .ok()?;
                        Some(max_val as f32)
                    })
                    .unwrap_or(0.0)
            } else {
                0.0
            };

            if best.map_or(true, |(s, _, _, _)| score > s) {
                let r = radius.max(MIN_BALL_RADIUS) as i32;
                best = Some((score, cx, cy, r));
            }
        }

        best.map(|(_, cx, cy, r)| (cx, cy, r))
    }

    pub fn reset(&mut self) {
        let _ = self
            .acc
            .set_to(&Scalar::new(0.0, 0.0, 0.0, 0.0), &Mat::default());
    }
}

impl Default for BallAccumulator {
    fn default() -> Self {
        Self::new()
    }
}

// ── BallKalman ────────────────────────────────────────────────────────────────

/// 2D Kalman filter: state [x, y, vx, vy], measurement [x, y].
pub struct BallKalman {
    kf: opencv::video::KalmanFilter,
    pub initialized: bool,
}

impl BallKalman {
    pub fn new() -> Result<Self> {
        use opencv::video::KalmanFilterTrait;

        let mut kf = opencv::video::KalmanFilter::new(4, 2, 0, CV_32F)?;

        // Measurement matrix: [[1,0,0,0],[0,1,0,0]]
        let mm = mat_f32(2, 4, &[1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0])?;
        kf.set_measurement_matrix(mm);

        // Transition matrix: [[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]]
        let tm = mat_f32(4, 4, &[
            1.0, 0.0, 1.0, 0.0,
            0.0, 1.0, 0.0, 1.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ])?;
        kf.set_transition_matrix(tm);

        // Process noise: I(4) * KALMAN_PROCESS_NOISE
        let pn_data: Vec<f32> = (0..16)
            .map(|i| if i % 5 == 0 { KALMAN_PROCESS_NOISE } else { 0.0 })
            .collect();
        let pn = mat_f32(4, 4, &pn_data)?;
        kf.set_process_noise_cov(pn);

        // Measurement noise: I(2) * KALMAN_MEASUREMENT_NOISE
        let mn = mat_f32(2, 2, &[KALMAN_MEASUREMENT_NOISE, 0.0, 0.0, KALMAN_MEASUREMENT_NOISE])?;
        kf.set_measurement_noise_cov(mn);

        Ok(BallKalman { kf, initialized: false })
    }

    /// Update with measurement, return corrected (x, y).
    pub fn update(&mut self, x: f32, y: f32) -> (f32, f32) {
        use opencv::video::KalmanFilterTrait;

        if !self.initialized {
            let sp = mat_f32(4, 1, &[x, y, 0.0, 0.0]).unwrap();
            self.kf.set_state_post(sp.clone());
            self.kf.set_state_pre(sp);

            // error_cov_post = I(4)
            let ec = mat_f32(4, 4, &[
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]).unwrap();
            self.kf.set_error_cov_post(ec);
            self.initialized = true;
        }

        let _ = self.kf.predict_def();

        let meas = mat_f32(2, 1, &[x, y]).unwrap();
        let corrected = self.kf.correct(&meas).unwrap();

        let cx: f32 = *corrected.at_2d(0, 0).unwrap();
        let cy: f32 = *corrected.at_2d(1, 0).unwrap();
        (cx, cy)
    }

    /// Predict next position without a measurement.
    pub fn predict(&mut self) -> (f32, f32) {
        use opencv::video::KalmanFilterTrait;
        if !self.initialized {
            return (0.0, 0.0);
        }
        let predicted = self.kf.predict_def().unwrap();
        let px: f32 = *predicted.at_2d(0, 0).unwrap();
        let py: f32 = *predicted.at_2d(1, 0).unwrap();
        (px, py)
    }

    pub fn reset(&mut self) {
        self.initialized = false;
    }
}

impl Default for BallKalman {
    fn default() -> Self {
        Self::new().expect("BallKalman::new failed")
    }
}
