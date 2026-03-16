//! ONNX Runtime inference thread — mirrors ai_inference.py exactly.
//!
//! Enabled via cargo feature `ai`:
//!   cargo build --release --features ai
//!
//! Input:  full BGR frame (any size — resized internally to AI_INPUT_SIZE).
//! Output: list of Detection structs filtered to BALL_CLASS_ID.
//!
//! Runs at ~15-20 FPS on RPi3. Non-blocking submit/get preserves real-time behavior.

use opencv::core::Mat;

/// A single detection from the AI model (in original frame coordinates).
#[derive(Debug, Clone)]
pub struct Detection {
    pub cx: i32,
    pub cy: i32,
    pub w: i32,
    pub h: i32,
    pub conf: f32,
    pub class_id: i32,
}

#[derive(Debug, Clone, Copy)]
pub struct AIResultMeta {
    pub preprocess_ms: f64,
    pub infer_ms: f64,
    pub parse_ms: f64,
    pub detections: usize,
}

fn should_log_ai_error(count: u64) -> bool {
    count <= 5 || count % 50 == 0
}

#[cfg(test)]
mod api_tests {
    use super::{should_log_ai_error, AIInferenceThread};

    #[test]
    fn ai_thread_reports_no_latest_result_in_stub_mode() {
        let ai = AIInferenceThread::new();
        assert!(ai.get_latest_result().is_none());
    }

    #[test]
    fn ai_error_log_policy_matches_expected_rate_limit() {
        assert!(should_log_ai_error(1));
        assert!(should_log_ai_error(5));
        assert!(!should_log_ai_error(6));
        assert!(should_log_ai_error(50));
        assert!(!should_log_ai_error(51));
    }
}

#[cfg(any(test, feature = "ai"))]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AIOutputFormat {
    Nx6,
    Nx7,
}

#[cfg(any(test, feature = "ai"))]
fn parse_output_layout(shape: &[i64]) -> anyhow::Result<(usize, usize, AIOutputFormat)> {
    let ndims = shape.len();
    let (rows_i64, stride_i64) = if ndims == 3 {
        if shape[0] != 1 {
            return Err(anyhow::anyhow!(
                "unexpected AI output shape {:?}: batch dim must be 1",
                shape
            ));
        }
        (shape[1], shape[2])
    } else if ndims == 2 {
        (shape[0], shape[1])
    } else {
        return Err(anyhow::anyhow!(
            "unexpected AI output rank {} with shape {:?}; expected rank 2 or 3",
            ndims,
            shape
        ));
    };

    if rows_i64 < 0 {
        return Err(anyhow::anyhow!(
            "unexpected AI output shape {:?}: rows must be non-negative",
            shape
        ));
    }

    let format = match stride_i64 {
        6 => AIOutputFormat::Nx6,
        7 => AIOutputFormat::Nx7,
        _ => {
            return Err(anyhow::anyhow!(
                "unexpected AI output shape {:?}: last dim must be 6 or 7",
                shape
            ));
        }
    };

    let rows = rows_i64 as usize;
    let stride = stride_i64 as usize;
    Ok((rows, stride, format))
}

#[cfg(any(test, feature = "ai"))]
fn parse_row_conf_class(flat: &[f32], base: usize, format: AIOutputFormat) -> (f32, f32) {
    match format {
        AIOutputFormat::Nx6 => (flat[base + 4], flat[base + 5]),
        AIOutputFormat::Nx7 => {
            let obj_conf = flat[base + 4];
            let cls_conf = flat[base + 5];
            (obj_conf * cls_conf, flat[base + 6])
        }
    }
}

#[cfg(test)]
mod output_parse_tests {
    use super::{parse_output_layout, parse_row_conf_class, AIOutputFormat};

    #[test]
    fn parse_layout_accepts_nx6_rank3() {
        let (rows, stride, format) =
            parse_output_layout(&[1, 300, 6]).expect("layout should parse");
        assert_eq!(rows, 300);
        assert_eq!(stride, 6);
        assert_eq!(format, AIOutputFormat::Nx6);
    }

    #[test]
    fn parse_layout_accepts_nx7_rank3() {
        let (rows, stride, format) =
            parse_output_layout(&[1, 300, 7]).expect("layout should parse");
        assert_eq!(rows, 300);
        assert_eq!(stride, 7);
        assert_eq!(format, AIOutputFormat::Nx7);
    }

    #[test]
    fn parse_layout_accepts_nx6_rank2() {
        let (rows, stride, format) = parse_output_layout(&[300, 6]).expect("layout should parse");
        assert_eq!(rows, 300);
        assert_eq!(stride, 6);
        assert_eq!(format, AIOutputFormat::Nx6);
    }

    #[test]
    fn parse_layout_accepts_nx7_rank2() {
        let (rows, stride, format) = parse_output_layout(&[300, 7]).expect("layout should parse");
        assert_eq!(rows, 300);
        assert_eq!(stride, 7);
        assert_eq!(format, AIOutputFormat::Nx7);
    }

    #[test]
    fn parse_layout_rejects_unsupported_last_dim() {
        let err = parse_output_layout(&[1, 300, 84]).expect_err("layout should fail");
        assert!(err.to_string().contains("6 or 7"));
    }

    #[test]
    fn parse_row_conf_class_supports_nx6() {
        let row = [10.0, 20.0, 30.0, 40.0, 0.61, 0.0];
        let (conf, class_id) = parse_row_conf_class(&row, 0, AIOutputFormat::Nx6);
        assert!((conf - 0.61).abs() < f32::EPSILON);
        assert!((class_id - 0.0).abs() < f32::EPSILON);
    }

    #[test]
    fn parse_row_conf_class_supports_nx7() {
        let row = [10.0, 20.0, 30.0, 40.0, 0.80, 0.50, 0.0];
        let (conf, class_id) = parse_row_conf_class(&row, 0, AIOutputFormat::Nx7);
        assert!((conf - 0.40).abs() < 1e-6);
        assert!((class_id - 0.0).abs() < f32::EPSILON);
    }
}

// ── Stub when AI feature is disabled ─────────────────────────────────────────

#[cfg(not(feature = "ai"))]
pub struct AIInferenceThread {
    pub available: bool,
}

#[cfg(not(feature = "ai"))]
impl AIInferenceThread {
    pub fn new() -> Self {
        log::info!("[AI] Compiled without `ai` feature — AI inference disabled");
        AIInferenceThread { available: false }
    }
    pub fn stop(&mut self) {}
    pub fn submit_frame(&self, _frame: &Mat) {}
    pub fn submit_frame_with_offset(&self, _frame: &Mat, _offset: Option<(i32, i32)>) {}
    pub fn get_detections(&self) -> Vec<Detection> {
        vec![]
    }
    pub fn get_latest_result(&self) -> Option<AIResultMeta> {
        None
    }

    pub fn get_and_reset_submit_drops(&self) -> u64 {
        0
    }
}

#[cfg(not(feature = "ai"))]
impl Default for AIInferenceThread {
    fn default() -> Self {
        Self::new()
    }
}

// ── Full implementation when `ai` feature is enabled ─────────────────────────

#[cfg(feature = "ai")]
mod inner {
    use std::path::Path;
    use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};
    use std::sync::Mutex;
    use std::thread::{self, JoinHandle};

    use anyhow::Result;
    use crossbeam_channel::{bounded, Receiver, Sender, TryRecvError, TrySendError};
    use ndarray::Array4;
    use opencv::{core::Mat, imgproc, prelude::*};
    use ort::session::Session;
    use ort::value::Tensor;

    use super::{
        parse_output_layout, parse_row_conf_class, AIOutputFormat, AIResultMeta, Detection,
    };
    use crate::config::{
        ai_parser_conf_floor, AI_INPUT_SIZE, AI_THREADS, BALL_CLASS_ID, MODEL_PATH,
    };

    enum Msg {
        Frame {
            frame: Mat,
            offset: Option<(i32, i32)>,
        },
        Stop,
    }

    type AIOutput = (Vec<Detection>, f64, f64, f64);

    pub struct AIInferenceThread {
        input_tx: Option<Sender<Msg>>,
        output_rx: Receiver<AIOutput>,
        latest_result: Mutex<Option<AIResultMeta>>,
        submit_drops: AtomicU64,
        thread: Option<JoinHandle<()>>,
        pub available: bool,
    }

    impl AIInferenceThread {
        pub fn new() -> Self {
            let (input_tx, input_rx) = bounded::<Msg>(2);
            let (output_tx, output_rx) = bounded::<AIOutput>(2);

            let model_exists = Path::new(MODEL_PATH).exists();
            if !model_exists {
                log::warn!(
                    "[AI] model.onnx not found at {} — AI thread disabled",
                    MODEL_PATH
                );
            }

            let available = model_exists;
            let handle = thread::spawn(move || run_inference(input_rx, output_tx));

            AIInferenceThread {
                input_tx: Some(input_tx),
                output_rx,
                latest_result: Mutex::new(None),
                submit_drops: AtomicU64::new(0),
                thread: Some(handle),
                available,
            }
        }

        pub fn stop(&mut self) {
            if let Some(input_tx) = self.input_tx.take() {
                match input_tx.try_send(Msg::Stop) {
                    Ok(_) => {}
                    Err(TrySendError::Full(_)) => {
                        // Queue is full: dropping the last sender cleanly disconnects
                        // the channel so the worker exits after draining queued frames.
                    }
                    Err(TrySendError::Disconnected(_)) => {}
                }
            }
            // Drop the handle (detach) instead of join — model loading can take
            // several seconds and we don't want to block Ctrl+C shutdown.
            drop(self.thread.take());
        }

        /// Non-blocking submit — drops frame if queue is full.
        pub fn submit_frame(&self, frame: &Mat) {
            self.submit_frame_with_offset(frame, None);
        }

        /// Non-blocking submit with optional (x,y) output offset.
        ///
        /// Use offset for ROI crops: detections are mapped back to full-frame
        /// coordinates by adding this offset after model parsing.
        pub fn submit_frame_with_offset(&self, frame: &Mat, offset: Option<(i32, i32)>) {
            let Some(input_tx) = self.input_tx.as_ref() else {
                return;
            };

            match input_tx.try_send(Msg::Frame {
                frame: frame.clone(),
                offset,
            }) {
                Ok(_) => {}
                Err(TrySendError::Full(_)) => {
                    self.submit_drops.fetch_add(1, Ordering::Relaxed);
                }
                Err(e) => log::warn!("[AI] submit_frame_with_offset error: {}", e),
            }
        }

        /// Non-blocking get — returns latest detections or [] if no new result.
        pub fn get_detections(&self) -> Vec<Detection> {
            let mut latest = None;
            loop {
                match self.output_rx.try_recv() {
                    Ok(output) => latest = Some(output),
                    Err(TryRecvError::Empty) | Err(TryRecvError::Disconnected) => break,
                }
            }

            if let Some((dets, preprocess_ms, infer_ms, parse_ms)) = latest {
                if let Ok(mut slot) = self.latest_result.lock() {
                    *slot = Some(AIResultMeta {
                        preprocess_ms,
                        infer_ms,
                        parse_ms,
                        detections: dets.len(),
                    });
                }
                dets
            } else {
                Vec::new()
            }
        }

        pub fn get_latest_result(&self) -> Option<AIResultMeta> {
            self.latest_result.lock().ok().and_then(|slot| *slot)
        }

        pub fn get_and_reset_submit_drops(&self) -> u64 {
            self.submit_drops.swap(0, Ordering::Relaxed)
        }
    }

    impl Default for AIInferenceThread {
        fn default() -> Self {
            Self::new()
        }
    }

    static OUTPUT_LAYOUT_LOGGED: AtomicU8 = AtomicU8::new(0);
    static INFER_ERROR_COUNT: AtomicU64 = AtomicU64::new(0);

    fn log_output_layout_once(format: AIOutputFormat, shape: &[i64], rows: usize, stride: usize) {
        let mask = match format {
            AIOutputFormat::Nx6 => 0b01,
            AIOutputFormat::Nx7 => 0b10,
        };

        let previous = OUTPUT_LAYOUT_LOGGED.fetch_or(mask, Ordering::Relaxed);
        if previous & mask != 0 {
            return;
        }

        match format {
            AIOutputFormat::Nx6 => {
                log::info!(
                    "[AI] output layout Nx6 detected: shape={:?}, rows={}, stride={} (conf direct)",
                    shape,
                    rows,
                    stride
                );
            }
            AIOutputFormat::Nx7 => {
                log::warn!(
                    "[AI] output layout Nx7 detected: shape={:?}, rows={}, stride={} (conf=obj_conf*class_conf)",
                    shape,
                    rows,
                    stride
                );
            }
        }
    }

    fn run_inference(input_rx: Receiver<Msg>, output_tx: Sender<AIOutput>) {
        let mut session = match load_session() {
            Some(s) => s,
            None => {
                for msg in &input_rx {
                    if matches!(msg, Msg::Stop) {
                        break;
                    }
                }
                return;
            }
        };

        for msg in &input_rx {
            match msg {
                Msg::Stop => break,
                Msg::Frame { frame, offset } => {
                    let (mut dets, preprocess_ms, infer_ms, parse_ms) =
                        match infer(&mut session, &frame) {
                            Ok(ok) => ok,
                            Err(err) => {
                                let n = INFER_ERROR_COUNT.fetch_add(1, Ordering::Relaxed) + 1;
                                if super::should_log_ai_error(n) {
                                    log::warn!("[AI] infer failed ({}) -> {}", n, err);
                                }
                                (Vec::new(), 0.0, 0.0, 0.0)
                            }
                        };
                    if let Some((ox, oy)) = offset {
                        for d in &mut dets {
                            d.cx += ox;
                            d.cy += oy;
                        }
                    }
                    let _ = output_tx.try_send((dets, preprocess_ms, infer_ms, parse_ms));
                }
            }
        }
    }

    fn load_session() -> Option<Session> {
        if !Path::new(MODEL_PATH).exists() {
            log::warn!("[AI] model not found at '{}' — AI disabled", MODEL_PATH);
            return None;
        }

        let build: anyhow::Result<Session> = (|| {
            let b = Session::builder().map_err(|e| anyhow::anyhow!("{}", e))?;
            let mut b = b
                .with_intra_threads(AI_THREADS as usize)
                .map_err(|e| anyhow::anyhow!("{}", e))?;
            b.commit_from_file(MODEL_PATH)
                .map_err(|e| anyhow::anyhow!("{:?}", e))
        })();

        match build {
            Ok(s) => {
                log::info!("[AI] YOLO loaded from '{}'", MODEL_PATH);
                Some(s)
            }
            Err(e) => {
                log::warn!("[AI] failed to load model: {} — is ORT_DYLIB_PATH set?", e);
                None
            }
        }
    }

    /// Preprocess BGR Mat → NCHW float32 [0,1]. Mirrors `_preprocess()` in Python.
    fn preprocess(frame: &Mat) -> Result<Array4<f32>> {
        let (h, w) = (AI_INPUT_SIZE.0 as usize, AI_INPUT_SIZE.1 as usize);

        let mut resized = Mat::default();
        imgproc::resize(
            frame,
            &mut resized,
            opencv::core::Size::new(AI_INPUT_SIZE.1, AI_INPUT_SIZE.0),
            0.0,
            0.0,
            imgproc::INTER_LINEAR,
        )?;

        let mut rgb = Mat::default();
        imgproc::cvt_color_def(&resized, &mut rgb, imgproc::COLOR_BGR2RGB)?;

        let mut tensor = Array4::<f32>::zeros((1, 3, h, w));
        fill_tensor_from_rgb(&rgb, &mut tensor)?;
        Ok(tensor)
    }

    fn fill_tensor_from_rgb(rgb: &Mat, tensor: &mut Array4<f32>) -> Result<()> {
        const SCALE: f32 = 1.0 / 255.0;

        let h = tensor.shape()[2];
        let w = tensor.shape()[3];
        let plane = h * w;

        // Fast path: continuous CV_8UC3 lets us scan pixels linearly.
        if rgb.typ() == opencv::core::CV_8UC3 && rgb.is_continuous() {
            let src = rgb.data_typed::<opencv::core::Vec3b>()?;
            let dst = tensor
                .as_slice_mut()
                .ok_or_else(|| anyhow::anyhow!("tensor backing storage is not contiguous"))?;

            let need = plane;
            if src.len() < need || dst.len() < need {
                return Err(anyhow::anyhow!(
                    "preprocess buffer size mismatch: src={} dst={} need={}",
                    src.len(),
                    dst.len(),
                    need
                ));
            }

            for i in 0..plane {
                let px = src[i];
                dst[i] = px[0] as f32 * SCALE;
                dst[plane + i] = px[1] as f32 * SCALE;
                dst[(2 * plane) + i] = px[2] as f32 * SCALE;
            }
            return Ok(());
        }

        // Fallback: safe indexed access for non-contiguous mats.
        for r in 0..h {
            for c in 0..w {
                let px: opencv::core::Vec3b = *rgb.at_2d(r as i32, c as i32)?;
                tensor[[0, 0, r, c]] = px[0] as f32 * SCALE;
                tensor[[0, 1, r, c]] = px[1] as f32 * SCALE;
                tensor[[0, 2, r, c]] = px[2] as f32 * SCALE;
            }
        }
        Ok(())
    }

    /// Run inference. Mirrors `_infer()` + `_parse_output()` in Python.
    fn infer(session: &mut Session, frame: &Mat) -> Result<(Vec<Detection>, f64, f64, f64)> {
        let t_pre = std::time::Instant::now();
        let tensor = preprocess(frame)?;
        let preprocess_ms = t_pre.elapsed().as_secs_f64() * 1000.0;
        // ort 2.x: use (shape, data) tuple — works without ndarray feature flag
        let shape: Vec<i64> = tensor.shape().iter().map(|&s| s as i64).collect();
        let data = tensor.into_raw_vec();
        let input = Tensor::from_array((shape, data))?;
        let t_infer = std::time::Instant::now();
        let outputs = session.run(ort::inputs![input])?;
        let infer_ms = t_infer.elapsed().as_secs_f64() * 1000.0;
        let t_parse = std::time::Instant::now();

        // ort 2.x: try_extract_tensor returns (Shape, &[T]) — flat slice + shape
        // output[0]: (1, N, 6|7) or (N, 6|7)
        //   Nx6: [x1, y1, x2, y2, conf, class_id]
        //   Nx7: [x1, y1, x2, y2, obj_conf, class_conf, class_id]
        let (shape, flat) = outputs[0].try_extract_tensor::<f32>()?;
        let (rows, stride, format) = parse_output_layout(&shape)?;
        log_output_layout_once(format, &shape, rows, stride);

        let expected_len = rows
            .checked_mul(stride)
            .ok_or_else(|| anyhow::anyhow!("AI output row count overflow for shape {:?}", shape))?;
        if flat.len() < expected_len {
            return Err(anyhow::anyhow!(
                "unexpected AI output length {} for shape {:?}; need at least {}",
                flat.len(),
                shape,
                expected_len
            ));
        };

        let frame_w = frame.cols().max(1) as f32;
        let frame_h = frame.rows().max(1) as f32;
        let scale_x = frame_w / AI_INPUT_SIZE.1 as f32;
        let scale_y = frame_h / AI_INPUT_SIZE.0 as f32;

        let mut results = Vec::new();

        // For both (1,N,*) and (N,*) the flat index per row i is i*stride
        // because batch dim 0 contributes 0 * N * stride offset
        for i in 0..rows {
            let base = i * stride;
            let x1 = flat[base];
            let y1 = flat[base + 1];
            let x2 = flat[base + 2];
            let y2 = flat[base + 3];
            let (conf, class_id) = parse_row_conf_class(flat, base, format);

            if conf < ai_parser_conf_floor() {
                continue;
            }
            if class_id as i32 != BALL_CLASS_ID {
                continue;
            }

            let x1s = (x1 * scale_x) as i32;
            let y1s = (y1 * scale_y) as i32;
            let x2s = (x2 * scale_x) as i32;
            let y2s = (y2 * scale_y) as i32;
            let bw = x2s - x1s;
            let bh = y2s - y1s;

            results.push(Detection {
                cx: x1s + bw / 2,
                cy: y1s + bh / 2,
                w: bw,
                h: bh,
                conf,
                class_id: class_id as i32,
            });
        }
        let parse_ms = t_parse.elapsed().as_secs_f64() * 1000.0;
        Ok((results, preprocess_ms, infer_ms, parse_ms))
    }

    #[cfg(test)]
    mod preprocess_tests {
        use anyhow::Result;
        use ndarray::Array4;
        use opencv::{
            core::{self, Mat, Scalar, Vec3b},
            prelude::*,
        };

        use super::fill_tensor_from_rgb;

        fn approx_eq(a: f32, b: f32) -> bool {
            (a - b).abs() < 1e-6
        }

        #[test]
        fn fill_tensor_from_rgb_writes_nchw_channels() -> Result<()> {
            let mut rgb = Mat::new_rows_cols_with_default(2, 2, core::CV_8UC3, Scalar::all(0.0))?;

            *rgb.at_2d_mut::<Vec3b>(0, 0)? = Vec3b::from([10, 20, 30]);
            *rgb.at_2d_mut::<Vec3b>(0, 1)? = Vec3b::from([40, 50, 60]);
            *rgb.at_2d_mut::<Vec3b>(1, 0)? = Vec3b::from([70, 80, 90]);
            *rgb.at_2d_mut::<Vec3b>(1, 1)? = Vec3b::from([100, 110, 120]);

            let mut tensor = Array4::<f32>::zeros((1, 3, 2, 2));
            fill_tensor_from_rgb(&rgb, &mut tensor)?;

            assert!(approx_eq(tensor[[0, 0, 0, 0]], 10.0 / 255.0));
            assert!(approx_eq(tensor[[0, 0, 0, 1]], 40.0 / 255.0));
            assert!(approx_eq(tensor[[0, 0, 1, 0]], 70.0 / 255.0));
            assert!(approx_eq(tensor[[0, 0, 1, 1]], 100.0 / 255.0));

            assert!(approx_eq(tensor[[0, 1, 0, 0]], 20.0 / 255.0));
            assert!(approx_eq(tensor[[0, 1, 0, 1]], 50.0 / 255.0));
            assert!(approx_eq(tensor[[0, 1, 1, 0]], 80.0 / 255.0));
            assert!(approx_eq(tensor[[0, 1, 1, 1]], 110.0 / 255.0));

            assert!(approx_eq(tensor[[0, 2, 0, 0]], 30.0 / 255.0));
            assert!(approx_eq(tensor[[0, 2, 0, 1]], 60.0 / 255.0));
            assert!(approx_eq(tensor[[0, 2, 1, 0]], 90.0 / 255.0));
            assert!(approx_eq(tensor[[0, 2, 1, 1]], 120.0 / 255.0));

            Ok(())
        }
    }
}

#[cfg(feature = "ai")]
pub use inner::AIInferenceThread;
