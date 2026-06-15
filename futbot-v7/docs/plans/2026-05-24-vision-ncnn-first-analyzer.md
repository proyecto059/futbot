# Vision NCNN-First Analyzer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `src/vision` load YOLO through NCNN first with ONNX fallback, and add `scripts/analyze_image.py --vision` to test that same path.

**Architecture:** Add a small backend abstraction under `src/vision/utils` with `run(frame) -> rows` where rows are `(x1, y1, x2, y2, conf, cls_id)`. `YoloInferenceOperator` will call the backend instead of an ONNX session directly. The analyzer keeps its existing standalone mode and gains `--vision` for the shared `src/vision` backend.

**Tech Stack:** Python, OpenCV, NumPy, optional NCNN, ONNX Runtime, pytest.

---

### Task 1: Tests First

**Files:**
- Create: `tests/test_yolo_backend_factory.py`
- Modify: `tests/test_analyze_image_script.py`

**Step 1: Write failing tests**

Add tests proving factory tries NCNN before ONNX, falls back to ONNX when NCNN fails, and `--vision` is accepted by the analyzer parser.

**Step 2: Run red tests**

Run: `pytest -q tests/test_yolo_backend_factory.py tests/test_analyze_image_script.py::test_vision_flag_uses_src_vision_backend`

Expected: FAIL because backend factory and `--vision` do not exist yet.

### Task 2: Backend Factory

**Files:**
- Create: `src/vision/utils/yolo_backend_factory.py`
- Modify: `src/vision/utils/__init__.py`
- Modify: `src/vision/utils/vision_constants.py`

**Step 1: Implement minimal backend classes**

Add `NcnnYoloBackend`, `OnnxYoloBackend`, and `YoloBackendFactory.create()`.

**Step 2: Keep `YOLO_IMGSZ = 320`**

Do not change `YOLO_IMGSZ` yet per user request.

### Task 3: Runtime Wiring

**Files:**
- Modify: `src/vision/operators/yolo_inference_operator.py`
- Modify: `src/vision/hybrid_vision_service.py`

**Step 1: Use backend in worker**

Replace direct `session.run` usage with `backend.run(frame)`.

**Step 2: Create backend in service**

Replace `OnnxSessionFactory.create()` with `YoloBackendFactory.create()`.

### Task 4: Analyzer Vision Mode

**Files:**
- Modify: `scripts/analyze_image.py`

**Step 1: Add `--vision`**

When set, run the shared `src/vision` backend and parse/annotate with the existing analyzer output logic.

### Task 5: Verification

**Files:**
- No edits unless verification fails.

**Step 1: Run tests**

Run: `pytest -q tests/test_yolo_backend_factory.py tests/test_analyze_image_script.py`

Expected: PASS.

**Step 2: Compile**

Run: `/usr/bin/python -m py_compile src/vision/utils/yolo_backend_factory.py src/vision/operators/yolo_inference_operator.py src/vision/hybrid_vision_service.py scripts/analyze_image.py`

Expected: PASS.

**Step 3: Run analyzer**

Run: `uv run scripts/analyze_image.py --vision --debug`

Expected: Uses `backend: ncnn` if NCNN is installed; otherwise `backend: onnx` with fallback reason.

### Notes

- Do not commit unless explicitly requested.
- Leave `YOLO_IMGSZ = 320` for now.
