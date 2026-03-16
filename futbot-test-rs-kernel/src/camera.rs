//! Camera capture thread — mirrors camera.py exactly.
//!
//! Reads MJPEG frames (or local webcam) in a background thread.
//! The main loop never blocks waiting for OpenCV; it just calls
//! `wait_for_frame` with a timeout and `get_frame` to get a clone.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use opencv::core::Mat;
use opencv::prelude::*;
use opencv::videoio::{self, VideoCapture, VideoCaptureTrait};

use crate::config::{camera_url, local_cam_id, use_local_cam, FRAME_HEIGHT, FRAME_WIDTH};

pub struct CameraThread {
    /// Latest decoded frame (None until first frame arrives)
    frame: Arc<Mutex<Option<Mat>>>,
    /// Condvar used to signal a new frame has arrived
    new_frame: Arc<(Mutex<bool>, Condvar)>,
    running: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

impl CameraThread {
    pub fn new() -> Self {
        CameraThread {
            frame: Arc::new(Mutex::new(None)),
            new_frame: Arc::new((Mutex::new(false), Condvar::new())),
            running: Arc::new(AtomicBool::new(false)),
            thread: None,
        }
    }

    pub fn start(&mut self) {
        self.running.store(true, Ordering::SeqCst);

        let frame = Arc::clone(&self.frame);
        let new_frame = Arc::clone(&self.new_frame);
        let running = Arc::clone(&self.running);

        let source_label = if use_local_cam() {
            format!("local cam {}", local_cam_id())
        } else {
            camera_url()
        };
        log::info!("[camera] source: {}", source_label);

        let handle = thread::spawn(move || {
            run_capture(frame, new_frame, running);
        });

        self.thread = Some(handle);
    }

    pub fn stop(&mut self) {
        self.running.store(false, Ordering::SeqCst);
        // Wake up any blocked wait_for_frame caller
        let (lock, cvar) = &*self.new_frame;
        let mut ready = lock.lock().unwrap();
        *ready = true;
        cvar.notify_all();
        drop(ready);

        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }

    /// Block until a new frame arrives or `timeout` expires.
    /// Returns true if a frame arrived, false on timeout.
    /// Mirrors `wait_for_frame` in Python.
    pub fn wait_for_frame(&self, timeout: Duration) -> bool {
        let (lock, cvar) = &*self.new_frame;
        let guard = lock.lock().unwrap();
        let (mut ready, timeout_result) = cvar.wait_timeout_while(guard, timeout, |r| !*r).unwrap();
        if *ready {
            *ready = false; // clear event (mirrors Python Event.clear())
            true
        } else {
            !timeout_result.timed_out()
        }
    }

    /// Returns a clone of the latest frame, or None if no frame yet.
    pub fn get_frame(&self) -> Option<Mat> {
        let guard = self.frame.lock().unwrap();
        guard.as_ref().map(|m| m.clone())
    }
}

fn run_capture(
    frame_store: Arc<Mutex<Option<Mat>>>,
    new_frame: Arc<(Mutex<bool>, Condvar)>,
    running: Arc<AtomicBool>,
) {
    // CAP_FFMPEG for URL streams avoids GStreamer SIGSEGV on some Linux setups.
    let cap_result = if use_local_cam() {
        VideoCapture::new(local_cam_id(), videoio::CAP_ANY)
    } else {
        VideoCapture::from_file(&camera_url(), videoio::CAP_FFMPEG)
    };
    let mut cap = match cap_result {
        Ok(c) => c,
        Err(e) => {
            log::error!("[camera] failed to open source: {}", e);
            return;
        }
    };
    // 1-second read timeout so the loop can check `running` on Ctrl+C
    let _ = cap.set(videoio::CAP_PROP_READ_TIMEOUT_MSEC, 1000.0);

    let mut buf = Mat::default();

    while running.load(Ordering::SeqCst) {
        match cap.read(&mut buf) {
            Ok(true) if !buf.empty() => {}
            _ => {
                // No frame yet — spin briefly
                thread::sleep(Duration::from_millis(5));
                continue;
            }
        }

        // Resize to (FRAME_WIDTH, FRAME_HEIGHT)
        let mut resized = Mat::default();
        opencv::imgproc::resize_def(
            &buf,
            &mut resized,
            opencv::core::Size::new(FRAME_WIDTH, FRAME_HEIGHT),
        )
        .unwrap_or(());

        // Store frame
        {
            let mut guard = frame_store.lock().unwrap();
            *guard = Some(resized);
        }

        // Signal new frame
        let (lock, cvar) = &*new_frame;
        {
            let mut ready = lock.lock().unwrap();
            *ready = true;
        }
        cvar.notify_all();
    }
}

impl Default for CameraThread {
    fn default() -> Self {
        Self::new()
    }
}
