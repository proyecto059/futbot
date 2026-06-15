# yoloe26n_v2 Model Switch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Use the `models/yoloe26n_v2/` NCNN export in the live vision pipeline and `scripts/analyze_image.py`.

**Architecture:** The shared vision constants become the single source of truth for the new NCNN/ONNX paths, `320` input size, and class grouping. The YOLO backend decoder keeps bbox and class scores from YOLOe segment output while ignoring mask coefficients. The analyzer mirrors the same paths and grouping so single-image, RPi, and video modes report grouped `ball` and `robot` detections.

**Tech Stack:** Python, OpenCV, NumPy, NCNN, optional ONNXRuntime, pytest.

---

### Task 1: Update Shared Model Constants

**Files:**
- Modify: `src/vision/utils/vision_constants.py`
- Test: `tests/test_yolo_backend_factory.py`
- Test: `tests/test_vision_operators.py`

**Step 1: Write failing tests**

Update `tests/test_yolo_backend_factory.py::test_yolo_image_size_matches_current_ncnn_export` to assert:

```python
assert "0=2100 1=2" in param_text
assert YOLO_IMGSZ == 320
assert resolve_yolo_ncnn_model_dir().as_posix().endswith(
    "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
)
```

Add assertions for grouped class constants:

```python
from vision.utils.vision_constants import YOLO_BALL_CLASS_IDS, YOLO_ROBOT_CLASS_IDS

assert YOLO_BALL_CLASS_IDS == frozenset({0, 1, 2, 3})
assert YOLO_ROBOT_CLASS_IDS == frozenset({4, 5, 6, 7, 8, 9, 10, 11})
```

**Step 2: Run tests to verify failure**

Run: `pytest -q tests/test_yolo_backend_factory.py::test_yolo_image_size_matches_current_ncnn_export`

Expected: FAIL because constants still point at the old `640` model.

**Step 3: Implement constants**

In `src/vision/utils/vision_constants.py`, set:

```python
YOLO_IMGSZ = 320
YOLO_BALL_CLASS_ID = 0
YOLO_ROBOT_CLASS_ID = 4
YOLO_BALL_CLASS_IDS = frozenset({0, 1, 2, 3})
YOLO_ROBOT_CLASS_IDS = frozenset({4, 5, 6, 7, 8, 9, 10, 11})
YOLO_NCNN_MODEL_DIR = "models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model"
YOLO_ONNX_MODEL_PATH = "models/yoloe26n_v2/onnx/yoloe26n_v2.onnx"
```

**Step 4: Run tests to verify pass**

Run: `pytest -q tests/test_yolo_backend_factory.py::test_yolo_image_size_matches_current_ncnn_export`

Expected: PASS.

---

### Task 2: Decode YOLOe Segment Output

**Files:**
- Modify: `src/vision/utils/yolo_backend_factory.py`
- Test: `tests/test_yolo_backend_factory.py`

**Step 1: Write failing test**

Add a test where output has `4 bbox + 12 classes + 32 mask coefficients` rows and `2100` anchors. Assert `_as_detection_rows()` returns `(N, 6)` rows using only bbox and class scores.

```python
def test_as_detection_rows_decodes_yoloe_segment_output():
    output = np.zeros((48, 3), dtype=np.float32)
    output[:4, 0] = [100.0, 80.0, 40.0, 20.0]
    output[:4, 1] = [200.0, 120.0, 30.0, 30.0]
    output[4 + 2, 0] = 0.90
    output[4 + 7, 1] = 0.80
    output[16:, :] = 1.0

    rows = _as_detection_rows(output)

    assert rows.shape == (2, 6)
    assert rows[0].tolist() == [80.0, 70.0, 120.0, 90.0, pytest.approx(0.90), 2.0]
    assert rows[1].tolist() == [185.0, 105.0, 215.0, 135.0, pytest.approx(0.80), 7.0]
```

**Step 2: Run test to verify failure**

Run: `pytest -q tests/test_yolo_backend_factory.py::test_as_detection_rows_decodes_yoloe_segment_output`

Expected: FAIL because mask coefficients are treated as classes.

**Step 3: Implement minimal decoder update**

In `src/vision/utils/yolo_backend_factory.py`, import grouped class constants and add helper logic so channels-first output uses only classes up to the largest known class ID:

```python
known_class_count = max(YOLO_BALL_CLASS_IDS | YOLO_ROBOT_CLASS_IDS) + 1
scores = output[4 : 4 + known_class_count]
```

Keep existing NMS and bbox conversion.

**Step 4: Run test to verify pass**

Run: `pytest -q tests/test_yolo_backend_factory.py::test_as_detection_rows_decodes_yoloe_segment_output`

Expected: PASS.

---

### Task 3: Group Classes In Live Vision

**Files:**
- Modify: `src/vision/operators/yolo_inference_operator.py`
- Test: `tests/test_vision_operators.py`

**Step 1: Write failing test**

Add a test that builds a fake backend returning one ball subclass and one robot subclass. Call `_run_once()` and assert the latest output has one ball and one robot.

```python
def test_yolo_inference_groups_yoloe_ball_and_robot_classes():
    from vision.operators.yolo_inference_operator import YoloInferenceOperator

    class Backend:
        name = "fake"
        image_size = 320

        def run(self, _frame):
            return np.array(
                [
                    [10, 20, 30, 40, 0.90, 2],
                    [100, 110, 140, 150, 0.80, 7],
                ],
                dtype=np.float32,
            )

    operator = YoloInferenceOperator(Backend())
    operator._run_once(np.zeros((240, 320, 3), dtype=np.uint8), 0.0)

    raw = operator.get_latest_output()
    assert raw["ball_bbox"] is not None
    assert len(raw["robot_bboxes"]) == 1
```

**Step 2: Run test to verify failure**

Run: `pytest -q tests/test_vision_operators.py::test_yolo_inference_groups_yoloe_ball_and_robot_classes`

Expected: FAIL because only class `0` and `1` are recognized today.

**Step 3: Implement grouping**

In `src/vision/operators/yolo_inference_operator.py`, replace single-ID checks with set membership:

```python
if cls_id in YOLO_BALL_CLASS_IDS:
    ...
elif cls_id in YOLO_ROBOT_CLASS_IDS:
    ...
```

Keep the raw bbox entry class ID unchanged for debug visibility.

**Step 4: Run test to verify pass**

Run: `pytest -q tests/test_vision_operators.py::test_yolo_inference_groups_yoloe_ball_and_robot_classes`

Expected: PASS.

---

### Task 4: Update Analyzer Paths, Decode, And Labels

**Files:**
- Modify: `scripts/analyze_image.py`
- Test: `tests/test_analyze_image_script.py`

**Step 1: Write failing tests**

Update `test_export_paths_match_updated_model_layout` to expect:

```python
assert analyzer.ONNX_MODEL_PATH.as_posix().endswith("models/yoloe26n_v2/onnx/yoloe26n_v2.onnx")
assert analyzer.NCNN_MODEL_DIR.as_posix().endswith("models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model")
assert analyzer.MODEL_IMAGE_SIZE == 320
```

Add tests for grouped labels and segmentation output decode:

```python
def test_parse_detections_groups_yoloe_classes():
    analyzer = import_analyzer()
    output = np.array([[[10, 20, 50, 60, 0.80, 2], [100, 120, 150, 170, 0.70, 7]]], dtype=np.float32)
    detections = analyzer.parse_detections(output, image_shape=(320, 320, 3), conf_threshold=0.40)
    assert [det["class_name"] for det in detections] == ["ball", "robot"]

def test_analyzer_decodes_yoloe_segment_output():
    analyzer = import_analyzer()
    output = np.zeros((48, 1), dtype=np.float32)
    output[:4, 0] = [100.0, 80.0, 40.0, 20.0]
    output[4 + 2, 0] = 0.90
    rows = analyzer._as_detection_rows(output)
    assert rows[0].tolist() == [80.0, 70.0, 120.0, 90.0, pytest.approx(0.90), 2.0]
```

**Step 2: Run tests to verify failure**

Run: `pytest -q tests/test_analyze_image_script.py::test_export_paths_match_updated_model_layout tests/test_analyze_image_script.py::test_parse_detections_groups_yoloe_classes tests/test_analyze_image_script.py::test_analyzer_decodes_yoloe_segment_output`

Expected: FAIL because analyzer still points at the old model and treats class IDs literally.

**Step 3: Implement analyzer update**

In `scripts/analyze_image.py`:

- Update `NCNN_MODEL_DIR`, `ONNX_MODEL_PATH`, and `MODEL_IMAGE_SIZE`.
- Add `BALL_CLASS_IDS` and `ROBOT_CLASS_IDS`.
- Add class grouping in `parse_detections()` when backend-specific `class_names` is not provided.
- Update `_as_detection_rows()` to mirror the shared segmentation-compatible decode.

**Step 4: Run tests to verify pass**

Run: `pytest -q tests/test_analyze_image_script.py::test_export_paths_match_updated_model_layout tests/test_analyze_image_script.py::test_parse_detections_groups_yoloe_classes tests/test_analyze_image_script.py::test_analyzer_decodes_yoloe_segment_output`

Expected: PASS.

---

### Task 5: Full Focused Verification And Raspberry Smoke

**Files:**
- Verify: `scripts/analyze_image.py`
- Verify: `src/vision/**`
- Verify: `tests/**`

**Step 1: Run focused tests**

Run:

```bash
pytest -q tests/test_analyze_image_script.py tests/test_focus_camera_script.py tests/test_camera_backend_resolver.py tests/test_libcamera_worker.py tests/test_yolo_backend_factory.py tests/test_project_dependencies.py tests/test_vision_operators.py
```

Expected: PASS.

**Step 2: Compile analyzer**

Run: `/usr/bin/python -m py_compile scripts/analyze_image.py`

Expected: exit code `0`.

**Step 3: Sync changed files to Raspberry Pi**

Run:

```bash
scp scripts/analyze_image.py raspi@raspi.local:/home/raspi/futbot-v2/scripts/analyze_image.py
scp src/vision/utils/vision_constants.py raspi@raspi.local:/home/raspi/futbot-v2/src/vision/utils/vision_constants.py
scp src/vision/utils/yolo_backend_factory.py raspi@raspi.local:/home/raspi/futbot-v2/src/vision/utils/yolo_backend_factory.py
scp src/vision/operators/yolo_inference_operator.py raspi@raspi.local:/home/raspi/futbot-v2/src/vision/operators/yolo_inference_operator.py
```

Expected: files copied with no output.

**Step 4: Compile on Raspberry Pi**

Run:

```bash
ssh raspi@raspi.local 'cd /home/raspi/futbot-v2 && python3 -m py_compile scripts/analyze_image.py src/vision/utils/vision_constants.py src/vision/utils/yolo_backend_factory.py src/vision/operators/yolo_inference_operator.py'
```

Expected: exit code `0`.

**Step 5: Run RPi single-frame smoke**

Run:

```bash
ssh raspi@raspi.local 'cd /home/raspi/futbot-v2 && /home/raspi/.local/bin/uv run --no-dev --extra rpi scripts/analyze_image.py --rpi --debug --output output/analyze_image_yoloe26n_v2/image_annotated.png'
```

Expected: prints `backend: ncnn`, model path under `models/yoloe26n_v2`, and writes an annotated image.

**Step 6: Run RPi video smoke**

Run:

```bash
ssh raspi@raspi.local 'cd /home/raspi/futbot-v2 && rm -rf output/analyze_image_yoloe26n_v2_video && /home/raspi/.local/bin/uv run --no-dev --extra rpi scripts/analyze_image.py --video 2 --debug --output output/analyze_image_yoloe26n_v2_video'
```

Expected: prints per-frame FPS and writes raw/annotated frames plus `summary.json`.
