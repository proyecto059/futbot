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
    core::{self, Mat, Point, Point2f, Rect, Scalar, Size, ToInputArray, Vector, CV_32F, CV_8U},
    imgproc,
    prelude::*,
};
use std::sync::OnceLock;
use std::time::Instant;

use crate::config::*;
use crate::vision::bgr_detector::detect_ball_bgr;
use crate::vision::context::VisionContext;

#[derive(Debug, Clone, Copy, Default)]
pub struct DetectorStats {
    pub preprocess_ms: f64,
    pub threshold_main_ms: f64,
    pub threshold_seed_ms: f64,
    pub morphology_ms: f64,
    pub contour_extract_ms: f64,
}

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

fn kernel_open() -> &'static Mat {
    static K: OnceLock<Mat> = OnceLock::new();
    K.get_or_init(|| {
        imgproc::get_structuring_element(
            imgproc::MORPH_ELLIPSE,
            Size::new(MORPH_OPEN_SIZE, MORPH_OPEN_SIZE),
            Point::new(-1, -1),
        )
        .unwrap()
    })
}

fn kernel_dilate() -> &'static Mat {
    static K: OnceLock<Mat> = OnceLock::new();
    K.get_or_init(|| {
        imgproc::get_structuring_element(
            imgproc::MORPH_ELLIPSE,
            Size::new(MORPH_DILATE_SIZE, MORPH_DILATE_SIZE),
            Point::new(-1, -1),
        )
        .unwrap()
    })
}

#[inline]
fn near_border(cx: f32, cy: f32, w: i32, h: i32) -> bool {
    let b = BORDER_REJECT_PX as f32;
    cx < b || cy < b || cx > (w as f32 - b) || cy > (h as f32 - b)
}

/// Main HSV detection pass with circularity filter.
fn hsv_pass(
    hsv: &(impl MatTraitConst + ToInputArray),
    lower: [u8; 3],
    upper: [u8; 3],
    min_circ: f64,
    precomputed_mask: Option<&Mat>,
    stats: &mut DetectorStats,
) -> Result<Option<(i32, i32, i32)>> {
    let mask = if let Some(mask) = precomputed_mask {
        mask.clone()
    } else {
        let lower_s = Scalar::new(lower[0] as f64, lower[1] as f64, lower[2] as f64, 0.0);
        let upper_s = Scalar::new(upper[0] as f64, upper[1] as f64, upper[2] as f64, 0.0);

        let t_threshold = Instant::now();
        let mut mask = Mat::default();
        core::in_range(hsv, &lower_s, &upper_s, &mut mask)?;
        stats.threshold_main_ms += t_threshold.elapsed().as_secs_f64() * 1000.0;
        mask
    };

    let kopen = kernel_open();
    let kdilate = kernel_dilate();

    let t_morph = Instant::now();
    let mut opened = Mat::default();
    imgproc::morphology_ex_def(&mask, &mut opened, imgproc::MORPH_OPEN, kopen)?;

    let mut dilated = Mat::default();
    imgproc::dilate_def(&opened, &mut dilated, kdilate)?;
    stats.morphology_ms += t_morph.elapsed().as_secs_f64() * 1000.0;

    let t_contours = Instant::now();
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

    stats.contour_extract_ms += t_contours.elapsed().as_secs_f64() * 1000.0;

    Ok(best.map(|(_, cx, cy, r)| (cx, cy, r)))
}

/// Partial contour pass — ellipse fitting for arcs/semicircles.
fn partial_contour_pass(
    hsv: &(impl MatTraitConst + ToInputArray),
    lower: [u8; 3],
    stats: &mut DetectorStats,
) -> Result<Option<(i32, i32, i32)>> {
    let lower_s = Scalar::new(lower[0] as f64, lower[1] as f64, lower[2] as f64, 0.0);
    let upper_s = Scalar::new(
        HSV_UPPER[0] as f64,
        HSV_UPPER[1] as f64,
        HSV_UPPER[2] as f64,
        0.0,
    );

    let t_threshold = Instant::now();
    let mut mask = Mat::default();
    core::in_range(hsv, &lower_s, &upper_s, &mut mask)?;
    stats.threshold_main_ms += t_threshold.elapsed().as_secs_f64() * 1000.0;

    let kopen = kernel_open();
    let kdilate = kernel_dilate();

    let t_morph = Instant::now();
    let mut opened = Mat::default();
    imgproc::morphology_ex_def(&mask, &mut opened, imgproc::MORPH_OPEN, kopen)?;

    let mut dilated = Mat::default();
    imgproc::dilate_def(&opened, &mut dilated, kdilate)?;
    stats.morphology_ms += t_morph.elapsed().as_secs_f64() * 1000.0;

    let t_contours = Instant::now();
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

        stats.contour_extract_ms += t_contours.elapsed().as_secs_f64() * 1000.0;

        return Ok(Some((cx as i32, cy as i32, radius as i32)));
    }

    stats.contour_extract_ms += t_contours.elapsed().as_secs_f64() * 1000.0;

    Ok(None)
}

/// Seed detector for tiny 8-15 px balls (high-purity color).
fn seed_pass(
    hsv: &(impl MatTraitConst + ToInputArray),
    seed_lower: [u8; 3],
    precomputed_mask: Option<&Mat>,
    stats: &mut DetectorStats,
) -> Result<Option<(i32, i32, i32)>> {
    let seed_mask = if let Some(mask) = precomputed_mask {
        mask.clone()
    } else {
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

        let t_threshold = Instant::now();
        let mut seed_mask = Mat::default();
        core::in_range(hsv, &lower_s, &upper_s, &mut seed_mask)?;
        stats.threshold_seed_ms += t_threshold.elapsed().as_secs_f64() * 1000.0;
        seed_mask
    };

    let k3 = imgproc::get_structuring_element(
        imgproc::MORPH_ELLIPSE,
        Size::new(3, 3),
        Point::new(-1, -1),
    )?;
    let t_morph = Instant::now();
    let mut eroded = Mat::default();
    imgproc::erode_def(&seed_mask, &mut eroded, &k3)?;
    stats.morphology_ms += t_morph.elapsed().as_secs_f64() * 1000.0;

    let t_contours = Instant::now();
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

    stats.contour_extract_ms += t_contours.elapsed().as_secs_f64() * 1000.0;

    Ok(best.map(|(_, cx, cy, r)| (cx, cy, r)))
}

/// Core detection: tries all passes on a given (sub)frame.
fn detect_in_hsv(
    hsv: &(impl MatTraitConst + ToInputArray),
    adaptive_lower: [u8; 3],
    adaptive_seed_lower: [u8; 3],
    main_mask: Option<&Mat>,
    seed_mask: Option<&Mat>,
    stats: &mut DetectorStats,
) -> Result<Option<(i32, i32, i32)>> {
    if let Some(det) = hsv_pass(
        hsv,
        adaptive_lower,
        HSV_UPPER,
        MIN_CIRCULARITY,
        main_mask,
        stats,
    )? {
        return Ok(Some(det));
    }

    if let Some(det) = partial_contour_pass(hsv, adaptive_lower, stats)? {
        return Ok(Some(det));
    }

    if let Some(det) = seed_pass(hsv, adaptive_seed_lower, seed_mask, stats)? {
        return Ok(Some(det));
    }

    Ok(None)
}

/// Main public API for ball detection with optional ROI search.
pub fn detect_ball(frame: &Mat, roi_center: Option<(i32, i32)>) -> Result<Option<(i32, i32, i32)>> {
    let (det, _stats) = detect_ball_with_stats(frame, roi_center)?;
    Ok(det)
}

pub fn detector_backend_name() -> &'static str {
    detector_backend().short_label()
}

pub fn detect_ball_bgr_with_thresholds(
    frame: &Mat,
    thresholds: BgrThresholds,
) -> Result<Option<(i32, i32, i32)>> {
    detect_ball_bgr(frame, thresholds)
}

pub fn detect_ball_from_context(
    frame: &Mat,
    ctx: &mut VisionContext,
    roi_center: Option<(i32, i32)>,
) -> Result<Option<(i32, i32, i32)>> {
    let (det, _stats) = detect_ball_from_context_with_stats(frame, ctx, roi_center, 0.0)?;
    Ok(det)
}

pub fn detect_ball_from_context_with_stats(
    frame: &Mat,
    ctx: &mut VisionContext,
    roi_center: Option<(i32, i32)>,
    preprocess_ms: f64,
) -> Result<(Option<(i32, i32, i32)>, DetectorStats)> {
    if detector_backend() == DetectorBackend::Bgr {
        let stats = DetectorStats {
            preprocess_ms,
            ..Default::default()
        };
        let det = detect_ball_bgr(frame, bgr_thresholds())?;
        return Ok((det, stats));
    }

    let mut stats = DetectorStats {
        preprocess_ms,
        ..Default::default()
    };

    if let Some((rx, ry)) = roi_center {
        let half = DETECT_ROI_SIZE / 2;
        let x1 = (rx - half).max(0);
        let y1 = (ry - half).max(0);
        let x2 = (rx + half).min(ctx.hsv.cols());
        let y2 = (ry + half).min(ctx.hsv.rows());

        if x2 > x1 && y2 > y1 {
            let roi_rect = Rect::new(x1, y1, x2 - x1, y2 - y1);
            let (roi_adaptive_lower, roi_adaptive_seed_lower) =
                ctx.prepare_roi_hsv_in_place(frame, roi_rect)?;
            if let Some((dx, dy, r)) = detect_in_hsv(
                &ctx.roi_hsv,
                roi_adaptive_lower,
                roi_adaptive_seed_lower,
                None,
                None,
                &mut stats,
            )? {
                return Ok((Some((dx + x1, dy + y1, r)), stats));
            }
        }
    }

    let det = detect_in_hsv(
        &ctx.hsv,
        ctx.adaptive_lower,
        ctx.adaptive_seed_lower,
        Some(&ctx.main_mask),
        Some(&ctx.seed_mask),
        &mut stats,
    )?;
    Ok((det, stats))
}

pub fn detect_ball_with_stats(
    frame: &Mat,
    roi_center: Option<(i32, i32)>,
) -> Result<(Option<(i32, i32, i32)>, DetectorStats)> {
    if detector_backend() == DetectorBackend::Bgr {
        let det = detect_ball_bgr(frame, bgr_thresholds())?;
        return Ok((
            det,
            DetectorStats {
                preprocess_ms: 0.0,
                ..Default::default()
            },
        ));
    }

    let t_preprocess = Instant::now();
    let mut ctx = VisionContext::prepare(frame)?;
    let preprocess_ms = t_preprocess.elapsed().as_secs_f64() * 1000.0;
    let out = detect_ball_from_context_with_stats(frame, &mut ctx, roi_center, preprocess_ms)?;
    Ok(out)
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
        let tm = mat_f32(
            4,
            4,
            &[
                1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
            ],
        )?;
        kf.set_transition_matrix(tm);

        // Process noise: I(4) * KALMAN_PROCESS_NOISE
        let pn_data: Vec<f32> = (0..16)
            .map(|i| {
                if i % 5 == 0 {
                    KALMAN_PROCESS_NOISE
                } else {
                    0.0
                }
            })
            .collect();
        let pn = mat_f32(4, 4, &pn_data)?;
        kf.set_process_noise_cov(pn);

        // Measurement noise: I(2) * KALMAN_MEASUREMENT_NOISE
        let mn = mat_f32(
            2,
            2,
            &[KALMAN_MEASUREMENT_NOISE, 0.0, 0.0, KALMAN_MEASUREMENT_NOISE],
        )?;
        kf.set_measurement_noise_cov(mn);

        Ok(BallKalman {
            kf,
            initialized: false,
        })
    }

    /// Update with measurement, return corrected (x, y).
    pub fn update(&mut self, x: f32, y: f32) -> (f32, f32) {
        use opencv::video::KalmanFilterTrait;

        if !self.initialized {
            let sp = mat_f32(4, 1, &[x, y, 0.0, 0.0]).unwrap();
            self.kf.set_state_post(sp.clone());
            self.kf.set_state_pre(sp);

            // error_cov_post = I(4)
            let ec = mat_f32(
                4,
                4,
                &[
                    1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
                ],
            )
            .unwrap();
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
