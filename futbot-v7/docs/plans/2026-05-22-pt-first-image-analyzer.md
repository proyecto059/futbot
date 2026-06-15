# PT-First Image Analyzer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `scripts/analyze_image.py` execute `models/yolo26n_futbot/best.pt` first, then fall back to ONNX and NCNN.

**Architecture:** Add a small Ultralytics runner that converts YOLO `.pt` results into the same row format used by the existing parser: `(x1, y1, x2, y2, conf, cls_id)`. Keep backend selection centralized in `run_with_fallback`, and preserve existing annotation, low-confidence debug mode, and CLI behavior.

**Tech Stack:** Python, OpenCV, NumPy, Ultralytics YOLO, ONNX Runtime, optional NCNN.

---

### Task 1: Backend Order Tests

**Files:**
- Modify: `tests/test_analyze_image_script.py`
- Modify: `scripts/analyze_image.py`

**Step 1: Write failing tests**

Add tests proving `run_with_fallback()` calls the PT runner first, falls back to ONNX when PT fails, and falls back to NCNN when both PT and ONNX fail.

**Step 2: Run red tests**

Run: `pytest -q tests/test_analyze_image_script.py::test_run_with_fallback_uses_pt_first tests/test_analyze_image_script.py::test_run_with_fallback_uses_onnx_when_pt_fails tests/test_analyze_image_script.py::test_run_with_fallback_uses_ncnn_when_pt_and_onnx_fail`

Expected: FAIL because the PT runner and order do not exist yet.

**Step 3: Implement minimal backend order**

Add `PT_MODEL_PATH`, a `pt_runner` parameter, and order runners as PT, ONNX, NCNN.

**Step 4: Run tests**

Run: `pytest -q tests/test_analyze_image_script.py`

Expected: PASS.

### Task 2: Ultralytics Runner

**Files:**
- Modify: `scripts/analyze_image.py`
- Modify: `tests/test_analyze_image_script.py`

**Step 1: Write conversion test**

Add a focused test for converting Ultralytics boxes into row format.

**Step 2: Implement conversion helper and runner**

Load `YOLO(str(PT_MODEL_PATH))`, call `model.predict(frame, imgsz=MODEL_IMAGE_SIZE, conf=LOW_CONF_THRESHOLD, verbose=False)`, and convert boxes to NumPy rows.

**Step 3: Run tests**

Run: `pytest -q tests/test_analyze_image_script.py`

Expected: PASS.

### Task 3: Dependency and Docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/plans/2026-05-22-image-model-analyzer-design.md`
- Modify: `docs/plans/2026-05-22-image-model-analyzer.md`

**Step 1: Add dependency**

Add `ultralytics` to project dependencies.

**Step 2: Update docs**

Change descriptions from ONNX-first to PT-first.

### Task 4: Verification

**Files:**
- No edits unless verification fails.

**Step 1: Run unit tests**

Run: `pytest -q tests/test_analyze_image_script.py`

Expected: PASS.

**Step 2: Compile script**

Run: `/usr/bin/python -m py_compile scripts/analyze_image.py`

Expected: PASS.

**Step 3: Install/check dependency and run script**

Run dependency installation through the project tool if needed, then run: `/usr/bin/python scripts/analyze_image.py`.

Expected: `backend: pt` when Ultralytics/Torch are installed; otherwise a clear fallback reason and ONNX/NCNN result.

### Notes

- Do not commit unless explicitly requested.
