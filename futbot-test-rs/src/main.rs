//! FutBotMX — main pipeline entry point.
//!
//! Mirrors main.py exactly, including all state variables and fusion logic.
//!
//! Thread layout:
//!   CameraThread      → shared frame (~25 FPS)
//!   Main loop         → HSV detect + Kalman + Tracker + Game Logic (~50 Hz)
//!   AIInferenceThread → YOLO INT8 on full frame (~15-20 FPS async)
//!   MotorController   → applied on each game logic decision
//!
//! Run:
//!   CAMERA_URL="http://192.168.1.105:8080/video" ./futbot
//!   CAMERA_URL="..." ./futbot --ui
//!   USE_LOCAL_CAM=true ./futbot

mod ai_inference;
mod camera;
mod config;
mod detector;
mod game_logic;
mod motor_control;
mod tracker;

use std::collections::HashMap;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::Parser;
use opencv::{
    core::{self, Mat, Point, Scalar, Size},
    highgui,
    imgproc,
};

use ai_inference::{AIInferenceThread, Detection};
use camera::CameraThread;
use config::*;
use detector::{detect_ball, BallAccumulator, BallKalman};
use game_logic::{decide_action, Action};
use motor_control::MotorController;
use tracker::BallTracker;

#[derive(Parser, Debug)]
#[command(name = "futbot", about = "FutBotMX Vision Pipeline")]
struct Args {
    /// Open debug window (requires display)
    #[arg(long)]
    ui: bool,
}

fn main() -> Result<()> {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    let args = Args::parse();

    // ── Initialize components ──────────────────────────────────────────────────
    let mut cam = CameraThread::new();
    let mut kalman = BallKalman::new()?;
    let mut ball_tracker = BallTracker::new();
    let mut ai = AIInferenceThread::new();
    let mut motors = MotorController::new();

    motors.setup();
    cam.start();

    log_startup(&ai);

    // ── Shutdown flag for Ctrl+C ───────────────────────────────────────────────
    let running = Arc::new(AtomicBool::new(true));
    {
        let running = Arc::clone(&running);
        ctrlc::set_handler(move || {
            running.store(false, Ordering::SeqCst);
        })
        .expect("Error setting Ctrl-C handler");
    }

    // ── State variables (mirrors Python main()) ────────────────────────────────
    let mut frame_count: u64 = 0;
    let mut tracker_frame_counter: u32 = 0;
    let mut no_ball_frames: u32 = 0;
    let mut last_radius: i32 = 15; // default avoids radius=None → SEARCH
    let mut prev_hsv_detected = false;
    let mut hsv_streak: u32 = 0;
    let mut ai_cache: Option<Detection> = None;
    let mut ai_cache_age: u32 = 0;
    let mut accumulator = BallAccumulator::new();
    let mut static_hits: HashMap<(i32, i32), u32> = HashMap::new();
    let mut last_known_pos: Option<(i32, i32)> = None;

    let t_start = Instant::now();
    let mut t_prev = Instant::now();

    // Rolling windows for FPS and loop-time stats
    let mut loop_times: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut hsv_times: VecDeque<f64> = VecDeque::with_capacity(100);

    log::info!("[main] Pipeline started. Press Ctrl+C to stop.\n");
    let mut cam_timeouts: u32 = 0;

    // ── Main loop ──────────────────────────────────────────────────────────────
    while running.load(Ordering::SeqCst) {
        if !cam.wait_for_frame(Duration::from_secs(1)) {
            cam_timeouts += 1;
            if cam_timeouts % 5 == 1 {
                log::warn!("[camera] no frame for {}s — check source", cam_timeouts);
            }
            continue;
        }
        cam_timeouts = 0;

        let frame = match cam.get_frame() {
            Some(f) => f,
            None => continue,
        };

        let t_now = Instant::now();
        let dt = t_now.duration_since(t_prev).as_secs_f64();
        t_prev = t_now;
        if loop_times.len() == 100 {
            loop_times.pop_front();
        }
        loop_times.push_back(dt);

        let mut tracked: Option<(i32, i32)> = None;
        let mut cx: Option<i32> = None;
        let mut cy: Option<i32> = None;

        // 1. Fast HSV detection (timed)
        let t_hsv = Instant::now();
        let detection = detect_ball(&frame, last_known_pos).unwrap_or(None);
        let hsv_elapsed = t_hsv.elapsed().as_secs_f64();
        if hsv_times.len() == 100 {
            hsv_times.pop_front();
        }
        hsv_times.push_back(hsv_elapsed);

        // Accumulator pass — if HSV/partial/seed all failed
        let mut detection = detection;
        if detection.is_none() {
            let mut blurred = Mat::default();
            imgproc::gaussian_blur_def(&frame, &mut blurred, Size::new(11, 11), 0.0)
                .unwrap_or(());

            let mut hsv_frame = Mat::default();
            imgproc::cvt_color_def(&blurred, &mut hsv_frame, imgproc::COLOR_BGR2HSV)
                .unwrap_or(());

            let lower_s = Scalar::new(
                SEED_LOWER[0] as f64,
                SEED_LOWER[1] as f64,
                SEED_LOWER[2] as f64,
                0.0,
            );
            let upper_s = Scalar::new(
                SEED_UPPER[0] as f64,
                SEED_UPPER[1] as f64,
                SEED_UPPER[2] as f64,
                0.0,
            );
            let mut seed_mask = Mat::default();
            if core::in_range(&hsv_frame, &lower_s, &upper_s, &mut seed_mask).is_ok() {
                if let Some(det) = accumulator.update(&seed_mask) {
                    log::debug!("[accum] ball @ ({},{}) r={}", det.0, det.1, det.2);
                    detection = Some(det);
                }
            }
        }

        // 2. Update state based on detection result
        if let Some((dcx, dcy, dradius)) = detection {
            no_ball_frames = 0;
            last_radius = dradius;
            hsv_streak += 1;

            if hsv_streak >= HSV_CONFIRM_FRAMES {
                if !prev_hsv_detected {
                    log::info!("[hsv] ball found @ ({},{}) r={}", dcx, dcy, dradius);
                }
                prev_hsv_detected = true;
                // Kalman update on confirmed detection
                let (kcx, kcy) = kalman.update(dcx as f32, dcy as f32);
                cx = Some(kcx as i32);
                cy = Some(kcy as i32);
            } else {
                // Tentative — don't update Kalman yet
                cx = Some(dcx);
                cy = Some(dcy);
            }

            // Re-init tracker periodically
            if tracker_frame_counter % TRACKER_REINIT_INTERVAL == 0 {
                ball_tracker.init(&frame, dcx, dcy, dradius);
            }
            tracker_frame_counter += 1;
        } else {
            hsv_streak = 0;
            if prev_hsv_detected {
                log::info!("[hsv] ball lost");
            }
            prev_hsv_detected = false;
            no_ball_frames += 1;

            // Fall back to tracker
            tracked = ball_tracker.update(&frame);
            if let Some((tcx, tcy)) = tracked {
                cx = Some(tcx);
                cy = Some(tcy);
            } else {
                cx = None;
                cy = None;
            }

            // Kalman prediction only (no measurement)
            if cx.is_none() && kalman.initialized {
                let (px, py) = kalman.predict();
                cx = Some(px as i32);
                cy = Some(py as i32);
            }
        }

        // 3. Fuse YOLO result if available (overrides HSV when AI has detection)
        ai.submit_frame(&frame);
        let raw_ai_dets = ai.get_detections();

        if !raw_ai_dets.is_empty() {
            let best = raw_ai_dets
                .iter()
                .max_by(|a, b| a.conf.partial_cmp(&b.conf).unwrap())
                .unwrap()
                .clone();
            ai_cache = Some(best);
            ai_cache_age = 0;
        } else if ai_cache.is_some() && ai_cache_age < AI_CACHE_MAX_AGE {
            ai_cache_age += 1;
        } else {
            ai_cache = None;
            ai_cache_age += 1;
        }

        if let Some(ref best) = ai_cache.clone() {
            log::debug!(
                "[ai]  ball @ ({},{}) w={} h={} conf={:.2}",
                best.cx,
                best.cy,
                best.w,
                best.h,
                best.conf
            );
            let (kcx, kcy) = kalman.update(best.cx as f32, best.cy as f32);
            cx = Some(kcx as i32);
            cy = Some(kcy as i32);
            last_radius = best.w.max(best.h) / 2;
            no_ball_frames = 0;
        }

        // 4. Update last known position for ROI tracking
        if let Some((dcx, dcy, _)) = detection {
            last_known_pos = Some((dcx, dcy));
        } else if ai_cache.is_some() && cx.is_some() {
            last_known_pos = cx.zip(cy);
        }
        if no_ball_frames > 30 {
            last_known_pos = None;
        }

        // 5. Motion consistency: reject static candidates for >= STATIC_REJECT_FRAMES
        if let (Some(fcx), Some(fcy)) = (cx, cy) {
            let key = (fcx / STATIC_GRID_SIZE, fcy / STATIC_GRID_SIZE);
            *static_hits.entry(key).or_insert(0) += 1;
            static_hits.retain(|k, v| k == &key || *v < STATIC_REJECT_FRAMES);
            if *static_hits.get(&key).unwrap_or(&0) > STATIC_REJECT_FRAMES {
                cx = None;
                cy = None;
            }
        }

        // 6. Reset Kalman + accumulator if no detection from ANY source for too long
        if no_ball_frames >= KALMAN_RESET_AFTER_N_FRAMES {
            kalman.reset();
            accumulator.reset();
            static_hits.clear();
        }

        // 7. Game logic
        let action = decide_action(cx, cy, Some(last_radius));

        // 8. Motor output
        match action {
            Action::Forward => motors.forward(),
            Action::TurnRight => motors.turn_right(MAX_SPEED * 0.6),
            Action::TurnLeft => motors.turn_left(MAX_SPEED * 0.6),
            Action::Stop => motors.stop(),
            Action::Search => motors.turn_right(30.0),
        }

        frame_count += 1;

        // 9. Debug UI
        if args.ui {
            let mut vis = frame.clone();

            // HSV detection: green circle (raw, before Kalman)
            if let Some((hx, hy, hr)) = detection {
                imgproc::circle(
                    &mut vis,
                    Point::new(hx, hy),
                    hr,
                    Scalar::new(0.0, 255.0, 0.0, 0.0),
                    2,
                    imgproc::LINE_8,
                    0,
                )
                .unwrap_or(());
                imgproc::put_text(
                    &mut vis,
                    "HSV",
                    Point::new(hx - hr, (hy - hr - 4).max(10)),
                    imgproc::FONT_HERSHEY_SIMPLEX,
                    0.35,
                    Scalar::new(0.0, 255.0, 0.0, 0.0),
                    1,
                    imgproc::LINE_8,
                    false,
                )
                .unwrap_or(());
            }

            // AI detections: yellow bounding boxes
            if let Some(ref det) = ai_cache {
                let x1 = det.cx - det.w / 2;
                let y1 = det.cy - det.h / 2;
                let x2 = det.cx + det.w / 2;
                let y2 = det.cy + det.h / 2;
                imgproc::rectangle(
                    &mut vis,
                    opencv::core::Rect::new(x1, y1, (x2 - x1).max(1), (y2 - y1).max(1)),
                    Scalar::new(0.0, 255.0, 255.0, 0.0),
                    2,
                    imgproc::LINE_8,
                    0,
                )
                .unwrap_or(());
                let label = format!("AI {:.2}", det.conf);
                imgproc::put_text(
                    &mut vis,
                    &label,
                    Point::new(x1, y1.max(14) - 4),
                    imgproc::FONT_HERSHEY_SIMPLEX,
                    0.35,
                    Scalar::new(0.0, 255.0, 255.0, 0.0),
                    1,
                    imgproc::LINE_8,
                    false,
                )
                .unwrap_or(());
            }

            // Final estimated ball position: white crosshair
            if let (Some(fcx), Some(fcy)) = (cx, cy) {
                imgproc::draw_marker(
                    &mut vis,
                    Point::new(fcx, fcy),
                    Scalar::new(255.0, 255.0, 255.0, 0.0),
                    imgproc::MARKER_CROSS,
                    14,
                    1,
                    imgproc::LINE_8,
                )
                .unwrap_or(());
            }

            // Status overlay
            let src_lbl = if ai_cache.is_some() {
                "AI"
            } else if detection.is_some() {
                "HSV"
            } else if tracked.is_some() {
                "TRK"
            } else {
                "KLM"
            };
            let status = format!(
                "{} | {} | ({},{})",
                src_lbl,
                action.name(),
                cx.map_or(-1, |v| v),
                cy.map_or(-1, |v| v)
            );
            imgproc::put_text(
                &mut vis,
                &status,
                Point::new(4, 14),
                imgproc::FONT_HERSHEY_SIMPLEX,
                0.4,
                Scalar::new(200.0, 200.0, 200.0, 0.0),
                1,
                imgproc::LINE_8,
                false,
            )
            .unwrap_or(());

            highgui::imshow("FutBotMX", &vis).unwrap_or(());

            // HSV mask window
            let mut hsv_frame2 = Mat::default();
            imgproc::cvt_color_def(&frame, &mut hsv_frame2, imgproc::COLOR_BGR2HSV)
                .unwrap_or(());
            let lower_s = Scalar::new(
                HSV_LOWER[0] as f64,
                HSV_LOWER[1] as f64,
                HSV_LOWER[2] as f64,
                0.0,
            );
            let upper_s = Scalar::new(
                HSV_UPPER[0] as f64,
                HSV_UPPER[1] as f64,
                HSV_UPPER[2] as f64,
                0.0,
            );
            let mut hsv_mask = Mat::default();
            core::in_range(&hsv_frame2, &lower_s, &upper_s, &mut hsv_mask).unwrap_or(());
            highgui::imshow("HSV mask", &hsv_mask).unwrap_or(());

            if highgui::wait_key(1).unwrap_or(0) & 0xFF == b'q' as i32 {
                break;
            }
        }

        // 10. Stats log every 100 frames
        if frame_count % 100 == 0 {
            let avg_loop_ms = if loop_times.is_empty() {
                0.0
            } else {
                loop_times.iter().sum::<f64>() / loop_times.len() as f64 * 1000.0
            };
            let fps = if avg_loop_ms > 0.0 {
                1000.0 / avg_loop_ms
            } else {
                0.0
            };
            let hsv_ms = if hsv_times.is_empty() {
                0.0
            } else {
                hsv_times.iter().sum::<f64>() / hsv_times.len() as f64 * 1000.0
            };
            let elapsed = t_start.elapsed().as_secs_f64();
            let source = if ai_cache.is_some() {
                "AI"
            } else if detection.is_some() {
                "HSV"
            } else if tracked.is_some() {
                "TRACKER"
            } else {
                "KALMAN"
            };
            log::info!(
                "[main] {:6} frames | {:6.1}s | loop {:5.1}ms ({:5.1} FPS) | HSV {:.1}ms | src={} | action={} | ball=({},{})",
                frame_count,
                elapsed,
                avg_loop_ms,
                fps,
                hsv_ms,
                source,
                action.name(),
                cx.map_or(-1, |v| v),
                cy.map_or(-1, |v| v),
            );
        }
    }

    // ── Shutdown ───────────────────────────────────────────────────────────────
    let elapsed = t_start.elapsed().as_secs_f64();
    let avg_fps = if elapsed > 0.0 {
        frame_count as f64 / elapsed
    } else {
        0.0
    };
    log::info!(
        "\n[main] Shutdown — {} frames in {:.1}s ({:.1} FPS avg)",
        frame_count,
        elapsed,
        avg_fps
    );

    motors.stop();
    motors.cleanup();
    cam.stop();
    ai.stop();

    if args.ui {
        highgui::destroy_all_windows().unwrap_or(());
    }

    Ok(())
}

fn log_startup(ai: &AIInferenceThread) {
    println!("{}", "=".repeat(52));
    println!("[main] FutBotMX Vision Pipeline (Rust)");
    println!(
        "  Platform  : {} {}",
        std::env::consts::OS,
        std::env::consts::ARCH
    );
    println!(
        "  AI model  : {}  ({})",
        MODEL_PATH,
        if ai.available {
            "file found — loading…"
        } else {
            "NOT FOUND — disabled"
        }
    );
    println!("  AI input  : {}x{}", AI_INPUT_SIZE.1, AI_INPUT_SIZE.0);
    println!("{}", "=".repeat(52));
}
