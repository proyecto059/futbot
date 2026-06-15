# Resolution Search Diagnostic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and run a motor-free diagnostic that checks whether the ball is visible at multiple camera resolutions using both the real vision pipeline and raw OpenCV capture, while reporting FPS.

**Architecture:** Add one standalone script under `scripts/` with no runtime integration into chase control. The script runs each resolution twice: once through `HybridVisionService` and once through raw `cv2.VideoCapture`, saving raw frames, annotated frames, and JSON summaries.

**Tech Stack:** Python, OpenCV, existing `vision` package, Raspberry Pi `uv` execution.

---

### Task 1: Add Script Tests

**Files:**
- Create: `tests/test_search_ball_resolutions.py`
- Create: `scripts/search_ball_resolutions.py`

**Steps:**
- Write tests for parsing resolution lists, FPS computation, and summary aggregation.
- Run `pytest -q tests/test_search_ball_resolutions.py` and verify it fails because the script does not exist.

### Task 2: Implement Diagnostic Script

**Files:**
- Create: `scripts/search_ball_resolutions.py`

**Steps:**
- Implement env-driven config: `BALL_SEARCH_RESOLUTIONS`, `BALL_SEARCH_FRAMES`, `BALL_SEARCH_OUTPUT`.
- Implement pipeline mode using `VisionConfigCommand(camera_width=w, camera_height=h, yolo_model_path=resolve_yolo_model_path())` and `HybridVisionService`.
- Implement raw OpenCV mode using `cv2.VideoCapture(0)` with requested width/height.
- Save `raw_*.jpg`, `annotated_*.jpg`, `records.json`, `summary.json` per mode and resolution.

### Task 3: Verify Locally

**Steps:**
- Run `pytest -q tests/test_search_ball_resolutions.py`.
- Run `python -m py_compile scripts/search_ball_resolutions.py`.

### Task 4: Sync And Run On Raspberry

**Steps:**
- Stop `futbot-api.service`.
- Sync the script to `~/futbot-v2`.
- Run with `/home/raspi/.local/bin/uv` at `320x240,424x240,512x384,640x480`.
- Copy `output/resolution_search_1/` locally.
- Report FPS and detection counts.
