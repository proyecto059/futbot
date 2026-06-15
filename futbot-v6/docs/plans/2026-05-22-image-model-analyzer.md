# Image Model Analyzer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone script that analyzes `image.png` with the exported YOLO model, loading the Ultralytics `.pt` model first and falling back to ONNX and NCNN.

**Architecture:** Keep the diagnostic self-contained in `scripts/analyze_image.py`. The script resolves model and image paths, runs one selected backend, parses YOLO detection rows, prints results, and writes an annotated image.

**Tech Stack:** Python, OpenCV, NumPy, Ultralytics, ONNX Runtime, optional `ncnn`.

---

### Task 1: Script Skeleton and CLI

**Files:**
- Create: `scripts/analyze_image.py`

**Step 1: Add script constants and argument parsing**

Create constants for project root, NCNN paths, ONNX path, default image path, default output path, class names, image size, and confidence threshold. Add `argparse` options for `--image`, `--output`, and `--conf`.

**Step 2: Add image loading and validation**

Read the input image with `cv2.imread` and exit with a clear error if it cannot be loaded.

### Task 2: Backend Implementations

**Files:**
- Modify: `scripts/analyze_image.py`

**Step 1: Add preprocessing**

Resize to the selected backend input size, convert BGR to RGB, transpose to CHW, normalize to `float32` `[0,1]`, and add the batch dimension when needed. Use `640x640` for NCNN and the ONNX input shape when it is statically available.

**Step 2: Add NCNN inference**

Import `ncnn` inside the function, load param/bin files, feed input name `in0`, extract `out0`, and return a NumPy output array.

**Step 3: Add ONNX inference**

Import `onnxruntime` inside the function, create a CPU session, feed the first input name, and return the first output array.

**Step 4: Add fallback selection**

Try `.pt` first. If it raises any exception, print a concise warning and run ONNX. If ONNX also raises, run NCNN.

### Task 3: Detection Parsing and Annotation

**Files:**
- Modify: `scripts/analyze_image.py`

**Step 1: Parse detections**

Normalize output shape to rows, filter rows with at least six values and confidence above threshold, scale coordinates from model space to original image size, and sort by confidence descending.

**Step 2: Print detections**

Print one line per detection with class name, confidence, and integer bbox. Keep the default confidence at the real detection threshold and expose `--debug-low-conf` for weak diagnostic candidates.

**Step 3: Draw annotation**

Draw rectangles and labels on a copy of the image and write it to the output path.

### Task 4: Verification

**Files:**
- No code edits unless verification fails.

**Step 1: Compile script**

Run: `/usr/bin/python -m py_compile scripts/analyze_image.py`

Expected: PASS.

**Step 2: Run diagnostic**

Run: `python scripts/analyze_image.py`

Expected: prints backend/model/detections and writes `image_annotated.png`.

### Notes

- Do not commit unless explicitly requested.
- Keep the script standalone; do not wire it into robot runtime code.
