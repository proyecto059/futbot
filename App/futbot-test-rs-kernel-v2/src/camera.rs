//! Camera capture thread — mirrors camera.py exactly.
//!
//! Reads MJPEG frames (or local webcam) in a background thread.
//! The main loop never blocks waiting for OpenCV; it just calls
//! `wait_for_frame` with a timeout and `get_frame` to get a clone.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use opencv::core::{Mat, Vector};
use opencv::imgcodecs;
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

/// Returns (host_port, path) from "http://host:port/path"
fn parse_url(url: &str) -> Option<(String, String)> {
    let after = url.find("://").map(|i| &url[i + 3..]).unwrap_or(url);
    let slash = after.find('/');
    let host_port = slash.map(|i| &after[..i]).unwrap_or(after).to_string();
    let path = slash.map(|i| after[i..].to_string()).unwrap_or_else(|| "/".to_string());
    Some((host_port, path))
}

/// Connect to MJPEG HTTP stream, extract JPEG frames via \xff\xd8..\xff\xd9 markers.
/// Returns true = connection lost, caller should retry.
/// Returns false = running flag cleared, caller should stop.
fn run_mjpeg_stream(
    url: &str,
    frame_store: Arc<Mutex<Option<Mat>>>,
    new_frame: Arc<(Mutex<bool>, Condvar)>,
    running: Arc<AtomicBool>,
) -> bool {
    let (host_port, path) = match parse_url(url) {
        Some(v) => v,
        None => { log::warn!("[camera] bad URL: {}", url); return true; }
    };

    // TCP connect
    let addr = match host_port.parse() {
        Ok(a) => a,
        Err(_) => { log::warn!("[camera] bad host:port '{}'", host_port); return true; }
    };
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(3000)) {
        Ok(s) => s,
        Err(e) => { log::warn!("[camera] TCP connect failed: {}", e); return true; }
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));

    // HTTP GET
    let req = format!("GET {} HTTP/1.0\r\nHost: {}\r\n\r\n", path, host_port);
    if stream.write_all(req.as_bytes()).is_err() {
        return true;
    }

    // Skip HTTP response headers (read until \r\n\r\n)
    let mut header_buf: Vec<u8> = Vec::new();
    let mut tmp = [0u8; 1];
    loop {
        match stream.read(&mut tmp) {
            Ok(1) => {
                header_buf.push(tmp[0]);
                if header_buf.ends_with(b"\r\n\r\n") { break; }
                if header_buf.len() > 8192 { return true; }
            }
            _ => return true,
        }
    }
    log::info!("[camera] HTTP stream connected, reading frames...");

    // Stream body — accumulate bytes, extract JPEGs
    let mut buf: Vec<u8> = Vec::new();
    let mut chunk = [0u8; 4096];

    while running.load(Ordering::SeqCst) {
        match stream.read(&mut chunk) {
            Ok(0) => { log::warn!("[camera] stream closed by server"); return true; }
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(e) => { log::warn!("[camera] read error: {}", e); return true; }
        }

        // Extract all complete JPEGs from buffer
        loop {
            let start = buf.windows(2).position(|w| w == [0xff, 0xd8]);
            let end   = buf.windows(2).position(|w| w == [0xff, 0xd9]);
            match (start, end) {
                (Some(a), Some(b)) if b > a => {
                    // Complete JPEG found
                    let jpg_bytes = buf[a..b + 2].to_vec();
                    buf.drain(..b + 2);

                    let vec: Vector<u8> = Vector::from_slice(&jpg_bytes);
                    if let Ok(frame) = imgcodecs::imdecode(&vec, imgcodecs::IMREAD_COLOR) {
                        if !frame.empty() {
                            let mut resized = Mat::default();
                            opencv::imgproc::resize_def(
                                &frame,
                                &mut resized,
                                opencv::core::Size::new(FRAME_WIDTH, FRAME_HEIGHT),
                            ).unwrap_or(());

                            *frame_store.lock().unwrap() = Some(resized);
                            let (lock, cvar) = &*new_frame;
                            *lock.lock().unwrap() = true;
                            cvar.notify_all();
                        }
                    }
                }
                (_, Some(b)) if start.map(|a| b < a).unwrap_or(true) => {
                    // Stale end marker before any start — discard it
                    buf.drain(..b + 2);
                }
                _ => break, // Need more data
            }
        }

        // Safety: prevent runaway buffer growth
        if buf.len() > 512 * 1024 {
            log::warn!("[camera] buffer overflow, resetting");
            buf.clear();
        }
    }
    false
}

fn run_capture(
    frame_store: Arc<Mutex<Option<Mat>>>,
    new_frame: Arc<(Mutex<bool>, Condvar)>,
    running: Arc<AtomicBool>,
) {
    if use_local_cam() {
        run_capture_local(frame_store, new_frame, running);
        return;
    }

    let url = camera_url();
    while running.load(Ordering::SeqCst) {
        let should_retry = run_mjpeg_stream(&url, Arc::clone(&frame_store), Arc::clone(&new_frame), Arc::clone(&running));
        if !should_retry { break; }
        log::warn!("[camera] reconnecting in 3s...");
        thread::sleep(Duration::from_secs(3));
    }
}

fn run_capture_local(
    frame_store: Arc<Mutex<Option<Mat>>>,
    new_frame: Arc<(Mutex<bool>, Condvar)>,
    running: Arc<AtomicBool>,
) {
    let mut buf = Mat::default();
    while running.load(Ordering::SeqCst) {
        let mut cap = match VideoCapture::new(local_cam_id(), videoio::CAP_ANY)
            .ok()
            .filter(|c| c.is_opened().unwrap_or(false))
        {
            Some(c) => { log::info!("[camera] local cam opened"); c }
            None => {
                log::warn!("[camera] could not open local cam, retrying in 3s...");
                thread::sleep(Duration::from_secs(3));
                continue;
            }
        };

        let mut fail_count: u32 = 0;
        while running.load(Ordering::SeqCst) {
            match cap.read(&mut buf) {
                Ok(true) if !buf.empty() => { fail_count = 0; }
                _ => {
                    fail_count += 1;
                    if fail_count > 10 { log::warn!("[camera] local cam lost, reconnecting..."); break; }
                    thread::sleep(Duration::from_millis(5));
                    continue;
                }
            }
            let mut resized = Mat::default();
            opencv::imgproc::resize_def(&buf, &mut resized, opencv::core::Size::new(FRAME_WIDTH, FRAME_HEIGHT)).unwrap_or(());
            *frame_store.lock().unwrap() = Some(resized);
            let (lock, cvar) = &*new_frame;
            *lock.lock().unwrap() = true;
            cvar.notify_all();
        }
    }
}

impl Default for CameraThread {
    fn default() -> Self {
        Self::new()
    }
}
