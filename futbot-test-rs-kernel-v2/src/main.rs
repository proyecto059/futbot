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
mod ai_policy;
mod camera;
mod config;
mod detector;
mod game_logic;
mod motor_control;
mod pipeline_state;
mod tracker;
mod vision;

use std::collections::HashMap;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::Parser;
use opencv::{
    core::{Mat, Point, Rect, Scalar},
    highgui, imgproc,
    prelude::MatTraitConst,
};

use ai_inference::{AIInferenceThread, Detection};
use ai_policy::{effective_ai_conf_threshold, select_ai_mode, AIMode};
use camera::CameraThread;
use config::*;
use detector::{
    detect_ball_bgr_with_thresholds, detect_ball_from_context_with_stats, detect_ball_with_stats,
    detector_backend_name, BallAccumulator, BallKalman,
};
use game_logic::{decide_action, Action};
use motor_control::MotorController;
use pipeline_state::{apply_static_rejection, update_ai_cache, update_last_known_pos};
use tracker::BallTracker;
use vision::context::{selected_kernel_info, VisionContext};

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
    let active_detector_backend = detector_backend_name();
    let active_detector_tag = active_detector_backend.to_ascii_lowercase();
    let using_hsv_backend = detector_backend() == DetectorBackend::Hsv;
    let bgr_cfg = bgr_thresholds();
    let ai_submit_stride = ai_stride();
    let ai_stride_search_cfg = ai_stride_search();
    let ai_stride_track_cfg = ai_stride_track();
    let ai_track_fullframe_every_cfg = ai_track_fullframe_every();
    let ai_hsv_track_streak_cfg = ai_hsv_track_streak();
    let ai_cache_max_age_cfg = ai_cache_max_age();
    let ai_use_roi = ai_roi_enabled();
    log::info!(
        "[main] Detector backend active: {}",
        active_detector_backend
    );

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
    let mut vision_ctx = VisionContext::new();
    let mut last_logged_ai_det: Option<Detection> = None;
    let mut ai_mode: AIMode = AIMode::Search;
    let mut ai_submit_stride_eff: u32 = ai_submit_stride;
    let mut ai_conf_eff: f32 = ai_conf_search_base();
    let mut ai_track_submit_count: u64 = 0;
    let mut ai_submit_drops_period: u64 = 0;

    let t_start = Instant::now();
    let mut t_prev = Instant::now();

    // Rolling windows for FPS and loop-time stats
    let mut loop_times: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut hsv_times: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut det_preprocess_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut det_threshold_main_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut det_threshold_seed_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut det_morphology_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut det_contour_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut accum_update_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut tracker_update_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut ai_preprocess_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut ai_infer_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut ai_parse_ms: VecDeque<f64> = VecDeque::with_capacity(100);
    let mut ai_fusion_ms: VecDeque<f64> = VecDeque::with_capacity(100);

    log::info!("[main] Pipeline started. Press Ctrl+C to stop.\n");
    let mut cam_timeouts: u32 = 0;
    let mut detector_errs: u32 = 0;

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

        let (vision_ctx_ready, vision_prepare_ms) = if using_hsv_backend {
            let t_prepare = Instant::now();
            let prepared_ctx = vision_ctx.prepare_in_place(&frame);
            let prepare_ms = t_prepare.elapsed().as_secs_f64() * 1000.0;
            match prepared_ctx {
                Ok(()) => (true, prepare_ms),
                Err(err) => {
                    detector_errs += 1;
                    if detector_errs % 50 == 1 {
                        log::warn!(
                            "[hsv] VisionContext::prepare_in_place failed ({} total): {}",
                            detector_errs,
                            err
                        );
                    }
                    (false, 0.0)
                }
            }
        } else {
            (true, 0.0)
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
        let mut frame_accum_path_ms = 0.0;
        let mut frame_tracker_ms = 0.0;
        let mut frame_ai_fusion_ms = 0.0;

        // 1. Fast HSV detection (timed)
        let t_hsv = Instant::now();
        let mut detection: Option<(i32, i32, i32)> = None;
        let mut detector_stats_ok = false;
        let mut detector_stats = Default::default();
        if using_hsv_backend {
            if vision_ctx_ready {
                match detect_ball_from_context_with_stats(
                    &frame,
                    &mut vision_ctx,
                    last_known_pos,
                    vision_prepare_ms,
                ) {
                    Ok((det, stats)) => {
                        detection = det;
                        detector_stats = stats;
                        detector_stats_ok = true;
                    }
                    Err(err) => {
                        detector_errs += 1;
                        if detector_errs % 50 == 1 {
                            log::warn!(
                                "[{}] detect_ball failed ({} total): {}",
                                active_detector_tag,
                                detector_errs,
                                err
                            );
                        }
                    }
                }
            } else {
                match detect_ball_with_stats(&frame, last_known_pos) {
                    Ok((det, stats)) => {
                        detection = det;
                        detector_stats = stats;
                        detector_stats_ok = true;
                    }
                    Err(err) => {
                        detector_errs += 1;
                        if detector_errs % 50 == 1 {
                            log::warn!(
                                "[{}] detect_ball fallback failed ({} total): {}",
                                active_detector_tag,
                                detector_errs,
                                err
                            );
                        }
                    }
                }
            }
        } else {
            match detect_ball_bgr_with_thresholds(&frame, bgr_cfg) {
                Ok(det) => {
                    detection = det;
                }
                Err(err) => {
                    detector_errs += 1;
                    if detector_errs % 50 == 1 {
                        log::warn!(
                            "[{}] detect_ball failed ({} total): {}",
                            active_detector_tag,
                            detector_errs,
                            err
                        );
                    }
                }
            }
        }
        let hsv_elapsed = t_hsv.elapsed().as_secs_f64();
        if hsv_times.len() == 100 {
            hsv_times.pop_front();
        }
        hsv_times.push_back(hsv_elapsed);

        if detector_stats_ok {
            if det_preprocess_ms.len() == 100 {
                det_preprocess_ms.pop_front();
            }
            det_preprocess_ms.push_back(detector_stats.preprocess_ms);

            if det_threshold_main_ms.len() == 100 {
                det_threshold_main_ms.pop_front();
            }
            det_threshold_main_ms.push_back(detector_stats.threshold_main_ms);

            if det_threshold_seed_ms.len() == 100 {
                det_threshold_seed_ms.pop_front();
            }
            det_threshold_seed_ms.push_back(detector_stats.threshold_seed_ms);

            if det_morphology_ms.len() == 100 {
                det_morphology_ms.pop_front();
            }
            det_morphology_ms.push_back(detector_stats.morphology_ms);

            if det_contour_ms.len() == 100 {
                det_contour_ms.pop_front();
            }
            det_contour_ms.push_back(detector_stats.contour_extract_ms);
        }

        // Accumulator pass — if HSV/partial/seed all failed
        if using_hsv_backend && detection.is_none() {
            let t_accum_path = Instant::now();
            if vision_ctx_ready {
                if let Some(det) = accumulator.update(&vision_ctx.seed_mask) {
                    log::debug!("[accum] ball @ ({},{}) r={}", det.0, det.1, det.2);
                    detection = Some(det);
                }
            }
            frame_accum_path_ms += t_accum_path.elapsed().as_secs_f64() * 1000.0;
        }

        // 2. Update state based on detection result
        if let Some((dcx, dcy, dradius)) = detection {
            no_ball_frames = 0;
            last_radius = dradius;
            hsv_streak += 1;

            if hsv_streak >= HSV_CONFIRM_FRAMES {
                if !prev_hsv_detected {
                    log::info!(
                        "[{}] ball found @ ({},{}) r={}",
                        active_detector_backend,
                        dcx,
                        dcy,
                        dradius
                    );
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
                log::info!("[{}] ball lost", active_detector_backend);
            }
            prev_hsv_detected = false;
            no_ball_frames += 1;

            // Fall back to tracker
            let t_tracker = Instant::now();
            tracked = ball_tracker.update(&frame);
            frame_tracker_ms += t_tracker.elapsed().as_secs_f64() * 1000.0;
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
        let t_ai_fusion = Instant::now();
        ai_mode = select_ai_mode(
            ai_cache.as_ref(),
            no_ball_frames,
            hsv_streak,
            ai_hsv_track_streak_cfg,
        );
        ai_submit_stride_eff = match ai_mode {
            AIMode::Search => ai_stride_search_cfg.max(1),
            AIMode::Track => ai_stride_track_cfg.max(1),
        };

        if frame_count % ai_submit_stride_eff as u64 == 0 {
            if matches!(ai_mode, AIMode::Track) {
                ai_track_submit_count += 1;
            } else {
                ai_track_submit_count = 0;
            }

            let force_fullframe = matches!(ai_mode, AIMode::Track)
                && ai_track_submit_count % ai_track_fullframe_every_cfg as u64 == 0;

            let stable_candidate = ai_use_roi
                && matches!(ai_mode, AIMode::Track)
                && no_ball_frames <= ai_track_max_missing_frames()
                && last_radius > 0
                && last_known_pos.is_some()
                && !force_fullframe;
            if stable_candidate {
                if let Some((roi, offset)) = extract_ai_roi(&frame, last_known_pos, last_radius) {
                    ai.submit_frame_with_offset(&roi, Some(offset));
                } else {
                    ai.submit_frame(&frame);
                }
            } else {
                ai.submit_frame(&frame);
            }
        }
        ai_submit_drops_period += ai.get_and_reset_submit_drops();
        let raw_ai_dets = ai.get_detections();
        if let Some(meta) = ai.get_latest_result() {
            if ai_preprocess_ms.len() == 100 {
                ai_preprocess_ms.pop_front();
            }
            ai_preprocess_ms.push_back(meta.preprocess_ms);

            if ai_infer_ms.len() == 100 {
                ai_infer_ms.pop_front();
            }
            ai_infer_ms.push_back(meta.infer_ms);

            if ai_parse_ms.len() == 100 {
                ai_parse_ms.pop_front();
            }
            ai_parse_ms.push_back(meta.parse_ms);
        }

        ai_conf_eff =
            effective_ai_conf_threshold(ai_mode, no_ball_frames, last_radius * last_radius);

        let best = raw_ai_dets
            .iter()
            .filter(|d| d.conf >= ai_conf_eff)
            .filter(|d| d.conf.is_finite())
            .max_by(|a, b| a.conf.total_cmp(&b.conf))
            .cloned();

        (ai_cache, ai_cache_age) =
            update_ai_cache(best, ai_cache, ai_cache_age, ai_cache_max_age_cfg);

        if let Some(best) = ai_cache.as_ref() {
            let changed = ai_detection_changed(last_logged_ai_det.as_ref(), Some(best));
            if !raw_ai_dets.is_empty() || changed {
                log::debug!(
                    "[ai]  ball @ ({},{}) w={} h={} conf={:.2}",
                    best.cx,
                    best.cy,
                    best.w,
                    best.h,
                    best.conf
                );
                last_logged_ai_det = Some(best.clone());
            }
            let (kcx, kcy) = kalman.update(best.cx as f32, best.cy as f32);
            cx = Some(kcx as i32);
            cy = Some(kcy as i32);
            last_radius = best.w.max(best.h) / 2;
            no_ball_frames = 0;
        } else {
            last_logged_ai_det = None;
        }
        frame_ai_fusion_ms += t_ai_fusion.elapsed().as_secs_f64() * 1000.0;

        if accum_update_ms.len() == 100 {
            accum_update_ms.pop_front();
        }
        accum_update_ms.push_back(frame_accum_path_ms);

        if tracker_update_ms.len() == 100 {
            tracker_update_ms.pop_front();
        }
        tracker_update_ms.push_back(frame_tracker_ms);

        if ai_fusion_ms.len() == 100 {
            ai_fusion_ms.pop_front();
        }
        ai_fusion_ms.push_back(frame_ai_fusion_ms);

        // 5. Motion consistency: reject static candidates for >= STATIC_REJECT_FRAMES
        (cx, cy) = apply_static_rejection(
            cx,
            cy,
            &mut static_hits,
            STATIC_GRID_SIZE,
            STATIC_REJECT_FRAMES,
        );

        // 4. Update last known position for ROI tracking (after static rejection)
        last_known_pos = update_last_known_pos(last_known_pos, cx, cy, no_ball_frames, 30);

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
                    active_detector_backend,
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
                active_detector_backend
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
            if using_hsv_backend && vision_ctx_ready {
                highgui::imshow("HSV mask", &vision_ctx.main_mask).unwrap_or(());
            }

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
            let det_ms = if hsv_times.is_empty() {
                0.0
            } else {
                hsv_times.iter().sum::<f64>() / hsv_times.len() as f64 * 1000.0
            };
            let det_label = if using_hsv_backend {
                "HSV"
            } else {
                active_detector_backend
            };
            let elapsed = t_start.elapsed().as_secs_f64();
            let source = if ai_cache.is_some() {
                "AI"
            } else if detection.is_some() {
                active_detector_backend
            } else if tracked.is_some() {
                "TRACKER"
            } else {
                "KALMAN"
            };
            log::info!(
                "[main] {:6} frames | {:6.1}s | loop {:5.1}ms ({:5.1} FPS) | {} {:.1}ms | src={} | action={} | ball=({},{})",
                frame_count,
                elapsed,
                avg_loop_ms,
                fps,
                det_label,
                det_ms,
                source,
                action.name(),
                cx.map_or(-1, |v| v),
                cy.map_or(-1, |v| v),
            );

            let avg = |w: &VecDeque<f64>| -> f64 {
                if w.is_empty() {
                    0.0
                } else {
                    w.iter().sum::<f64>() / w.len() as f64
                }
            };
            log::info!(
                "[perf] pre={:.2} th_main={:.2} th_seed={:.2} morph={:.2} contour={:.2} accum={:.2} tracker={:.2} ai_pre={:.2} ai_run={:.2} ai_parse={:.2} ai_fuse={:.2} ms",
                avg(&det_preprocess_ms),
                avg(&det_threshold_main_ms),
                avg(&det_threshold_seed_ms),
                avg(&det_morphology_ms),
                avg(&det_contour_ms),
                avg(&accum_update_ms),
                avg(&tracker_update_ms),
                avg(&ai_preprocess_ms),
                avg(&ai_infer_ms),
                avg(&ai_parse_ms),
                avg(&ai_fusion_ms),
            );
            log::info!(
                "[main] ai_mode={:?} ai_stride_eff={} ai_conf_eff={:.3}",
                ai_mode,
                ai_submit_stride_eff,
                ai_conf_eff
            );
            log::info!(
                "[main] ai_submit_drops={} ai_cache_age={}/{}",
                ai_submit_drops_period,
                ai_cache_age,
                ai_cache_max_age_cfg
            );
            log::info!("[main] detector_backend={}", active_detector_backend);
            ai_submit_drops_period = 0;
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
    println!("  AI stride : {}", ai_stride());
    println!(
        "  AI ROI    : {}",
        if ai_roi_enabled() {
            "enabled"
        } else {
            "disabled"
        }
    );
    println!(
        "  AI policy : dual (search stride={}, track stride={}, conf_search={:.2}, conf_track={:.2})",
        ai_stride_search(),
        ai_stride_track(),
        ai_conf_search_base(),
        ai_conf_track_base()
    );
    println!(
        "  AI track  : hsv_streak>={} fullframe_every={} cache_max_age={}",
        ai_hsv_track_streak(),
        ai_track_fullframe_every(),
        ai_cache_max_age()
    );
    let kernel = selected_kernel_info();
    println!(
        "  HSV kernel: {:?}{}",
        kernel.backend,
        if kernel.fallback {
            " (fallback-scalar)"
        } else {
            ""
        }
    );
    println!(
        "  Validation: {}{}",
        if kernel.validation_enabled {
            "enabled"
        } else {
            "disabled"
        },
        if kernel.validation_enabled {
            format!(
                " (mismatch>{:.4} => scalar fallback)",
                kernel.mismatch_threshold
            )
        } else {
            String::new()
        }
    );
    println!("  Detector  : {}", detector_backend_name());
    println!(
        "  BGR fused : {}",
        if kernel.fused_bgr_enabled {
            "enabled (experimental)"
        } else {
            "disabled"
        }
    );
    println!("{}", "=".repeat(52));
}

fn extract_ai_roi(
    frame: &Mat,
    center: Option<(i32, i32)>,
    radius: i32,
) -> Option<(Mat, (i32, i32))> {
    let (cx, cy) = center?;
    let half = (radius + ROI_PADDING).max(ROI_SIZE / 2);
    let x1 = (cx - half).max(0);
    let y1 = (cy - half).max(0);
    let x2 = (cx + half).min(frame.cols());
    let y2 = (cy + half).min(frame.rows());
    if x2 <= x1 || y2 <= y1 {
        return None;
    }

    let roi = frame.roi(Rect::new(x1, y1, x2 - x1, y2 - y1)).ok()?;
    Some((roi.clone_pointee(), (x1, y1)))
}

fn ai_detection_changed(prev: Option<&Detection>, curr: Option<&Detection>) -> bool {
    const POS_EPS: i32 = 1;
    const SIZE_EPS: i32 = 1;
    const CONF_EPS: f32 = 0.01;

    match (prev, curr) {
        (None, None) => false,
        (Some(_), None) | (None, Some(_)) => true,
        (Some(a), Some(b)) => {
            (a.cx - b.cx).abs() > POS_EPS
                || (a.cy - b.cy).abs() > POS_EPS
                || (a.w - b.w).abs() > SIZE_EPS
                || (a.h - b.h).abs() > SIZE_EPS
                || (a.conf - b.conf).abs() > CONF_EPS
        }
    }
}

