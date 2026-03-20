//! OpenCV MOSSE/KCF tracker — mirrors tracker.py exactly.
//!
//! Wraps an OpenCV legacy tracker for fast inter-frame updates between
//! AI inference frames. Degrades gracefully if opencv-contrib is absent
//! (build without the `opencv-tracking` cargo feature).

use opencv::core::Mat;

#[cfg(feature = "opencv-tracking")]
use crate::config::{FRAME_HEIGHT, FRAME_WIDTH};

pub struct BallTracker {
    #[cfg(feature = "opencv-tracking")]
    inner: Option<TrackerInner>,
    #[cfg(not(feature = "opencv-tracking"))]
    _phantom: (),
}

#[cfg(feature = "opencv-tracking")]
struct TrackerInner {
    tracker: Box<dyn opencv::tracking::TrackerTrait>,
    active: bool,
}

impl BallTracker {
    pub fn new() -> Self {
        #[cfg(feature = "opencv-tracking")]
        return BallTracker { inner: None };

        #[cfg(not(feature = "opencv-tracking"))]
        {
            log::debug!("[tracker] opencv-tracking feature not enabled — tracker disabled, using Kalman only");
            BallTracker { _phantom: () }
        }
    }

    /// Initialize tracker with ball bounding box. Mirrors `init()` in Python.
    pub fn init(&mut self, frame: &Mat, cx: i32, cy: i32, radius: i32) {
        #[cfg(feature = "opencv-tracking")]
        {
            use crate::config::TRACKER_TYPE;
            use opencv::core::Rect2d;

            let result = if TRACKER_TYPE == "MOSSE" {
                opencv::tracking::legacy::TrackerMOSSE::create()
                    .map(|t| Box::new(t) as Box<dyn opencv::tracking::TrackerTrait>)
            } else {
                opencv::tracking::legacy::TrackerKCF::create()
                    .map(|t| Box::new(t) as Box<dyn opencv::tracking::TrackerTrait>)
            };

            let mut tracker = match result {
                Ok(t) => t,
                Err(e) => {
                    log::warn!("[tracker] create failed: {} — tracker disabled", e);
                    return;
                }
            };

            let r = radius.max(10) as f64;
            let x = (cx as f64 - r).max(0.0);
            let y = (cy as f64 - r).max(0.0);
            let w = (2.0 * r).min(FRAME_WIDTH as f64 - x);
            let h = (2.0 * r).min(FRAME_HEIGHT as f64 - y);

            match tracker.init(frame, Rect2d::new(x, y, w, h)) {
                Ok(_) => {
                    self.inner = Some(TrackerInner {
                        tracker,
                        active: true,
                    });
                }
                Err(e) => {
                    log::warn!("[tracker] init failed: {}", e);
                }
            }
        }

        #[cfg(not(feature = "opencv-tracking"))]
        {
            let _ = (frame, cx, cy, radius);
        }
    }

    /// Update tracker on new frame. Returns center (cx, cy) or None if lost.
    pub fn update(&mut self, frame: &Mat) -> Option<(i32, i32)> {
        #[cfg(feature = "opencv-tracking")]
        {
            use opencv::core::Rect2d;
            let inner = self.inner.as_mut()?;
            if !inner.active {
                return None;
            }
            let mut bbox = Rect2d::default();
            match inner.tracker.update(frame, &mut bbox) {
                Ok(true) => {
                    let cx = (bbox.x + bbox.width / 2.0) as i32;
                    let cy = (bbox.y + bbox.height / 2.0) as i32;
                    Some((cx, cy))
                }
                _ => {
                    inner.active = false;
                    None
                }
            }
        }

        #[cfg(not(feature = "opencv-tracking"))]
        {
            let _ = frame;
            None
        }
    }

    pub fn reset(&mut self) {
        #[cfg(feature = "opencv-tracking")]
        {
            self.inner = None;
        }
    }
}

impl Default for BallTracker {
    fn default() -> Self {
        Self::new()
    }
}
