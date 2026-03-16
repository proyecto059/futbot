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
    pub fn get_detections(&self) -> Vec<Detection> { vec![] }
}

#[cfg(not(feature = "ai"))]
impl Default for AIInferenceThread {
    fn default() -> Self { Self::new() }
}

// ── Full implementation when `ai` feature is enabled ─────────────────────────

#[cfg(feature = "ai")]
mod inner {
    use std::path::Path;
    use std::thread::{self, JoinHandle};

    use anyhow::Result;
    use crossbeam_channel::{bounded, Receiver, Sender, TrySendError};
    use ndarray::Array4;
    use opencv::{core::Mat, imgproc, prelude::*};
    use ort::session::Session;
    use ort::value::Tensor;

    use crate::config::{
        AI_CONF_THRESHOLD, AI_INPUT_SIZE, AI_THREADS, BALL_CLASS_ID, FRAME_HEIGHT, FRAME_WIDTH,
        MODEL_PATH,
    };
    use super::Detection;

    enum Msg {
        Frame(Mat),
        Stop,
    }

    pub struct AIInferenceThread {
        input_tx: Sender<Msg>,
        output_rx: Receiver<Vec<Detection>>,
        thread: Option<JoinHandle<()>>,
        pub available: bool,
    }

    impl AIInferenceThread {
        pub fn new() -> Self {
            let (input_tx, input_rx) = bounded::<Msg>(2);
            let (output_tx, output_rx) = bounded::<Vec<Detection>>(2);

            let model_exists = Path::new(MODEL_PATH).exists();
            if !model_exists {
                log::warn!("[AI] model.onnx not found at {} — AI thread disabled", MODEL_PATH);
            }

            let available = model_exists;
            let handle = thread::spawn(move || run_inference(input_rx, output_tx));

            AIInferenceThread {
                input_tx,
                output_rx,
                thread: Some(handle),
                available,
            }
        }

        pub fn stop(&mut self) {
            let _ = self.input_tx.send(Msg::Stop);
            // Drop the handle (detach) instead of join — model loading can take
            // several seconds and we don't want to block Ctrl+C shutdown.
            drop(self.thread.take());
        }

        /// Non-blocking submit — drops frame if queue is full.
        pub fn submit_frame(&self, frame: &Mat) {
            match self.input_tx.try_send(Msg::Frame(frame.clone())) {
                Ok(_) | Err(TrySendError::Full(_)) => {}
                Err(e) => log::warn!("[AI] submit_frame error: {}", e),
            }
        }

        /// Non-blocking get — returns latest detections or [] if no new result.
        pub fn get_detections(&self) -> Vec<Detection> {
            self.output_rx.try_recv().unwrap_or_default()
        }
    }

    impl Default for AIInferenceThread {
        fn default() -> Self { Self::new() }
    }

    fn run_inference(input_rx: Receiver<Msg>, output_tx: Sender<Vec<Detection>>) {
        let mut session = match load_session() {
            Some(s) => s,
            None => {
                for msg in &input_rx {
                    if matches!(msg, Msg::Stop) { break; }
                }
                return;
            }
        };

        for msg in &input_rx {
            match msg {
                Msg::Stop => break,
                Msg::Frame(frame) => {
                    let dets = infer(&mut session, &frame).unwrap_or_default();
                    let _ = output_tx.try_send(dets);
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
            let mut b = b.with_intra_threads(AI_THREADS as usize).map_err(|e| anyhow::anyhow!("{}", e))?;
            b.commit_from_file(MODEL_PATH).map_err(|e| anyhow::anyhow!("{:?}", e))
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
            0.0, 0.0,
            imgproc::INTER_LINEAR,
        )?;

        let mut rgb = Mat::default();
        imgproc::cvt_color_def(&resized, &mut rgb, imgproc::COLOR_BGR2RGB)?;

        let mut tensor = Array4::<f32>::zeros((1, 3, h, w));
        for r in 0..h {
            for c in 0..w {
                let px: opencv::core::Vec3b = *rgb.at_2d(r as i32, c as i32)?;
                tensor[[0, 0, r, c]] = px[0] as f32 / 255.0;
                tensor[[0, 1, r, c]] = px[1] as f32 / 255.0;
                tensor[[0, 2, r, c]] = px[2] as f32 / 255.0;
            }
        }
        Ok(tensor)
    }

    /// Run inference. Mirrors `_infer()` + `_parse_output()` in Python.
    fn infer(session: &mut Session, frame: &Mat) -> Result<Vec<Detection>> {
        let tensor = preprocess(frame)?;
        // ort 2.x: use (shape, data) tuple — works without ndarray feature flag
        let shape: Vec<i64> = tensor.shape().iter().map(|&s| s as i64).collect();
        let data = tensor.into_raw_vec();
        let input = Tensor::from_array((shape, data))?;
        let outputs = session.run(ort::inputs![input])?;

        // ort 2.x: try_extract_tensor returns (Shape, &[T]) — flat slice + shape
        // output[0]: (1, N, 6) or (N, 6) — [x1, y1, x2, y2, conf, class_id]
        let (shape, flat) = outputs[0].try_extract_tensor::<f32>()?;
        let ndims = shape.len();
        // shape elements are i64 in ort 2.x
        let rows = if ndims == 3 { shape[1] as usize } else { shape[0] as usize };

        let scale_x = FRAME_WIDTH as f32 / AI_INPUT_SIZE.1 as f32;
        let scale_y = FRAME_HEIGHT as f32 / AI_INPUT_SIZE.0 as f32;

        let mut results = Vec::new();

        // For both (1,N,6) and (N,6) the flat index per row i is i*6
        // because batch dim 0 contributes 0 * N * 6 offset
        for i in 0..rows {
            let base = i * 6;
            let x1      = flat[base];
            let y1      = flat[base + 1];
            let x2      = flat[base + 2];
            let y2      = flat[base + 3];
            let conf    = flat[base + 4];
            let class_id = flat[base + 5];

            if conf < AI_CONF_THRESHOLD { continue; }
            if class_id as i32 != BALL_CLASS_ID { continue; }

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
        Ok(results)
    }
}

#[cfg(feature = "ai")]
pub use inner::AIInferenceThread;
