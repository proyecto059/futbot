# Image Model Analyzer Design

Goal: add a local diagnostic script that analyzes `image.png` with the exported YOLO model, preferring the Ultralytics `.pt` model and falling back to ONNX and NCNN if earlier backends are unavailable or fail.

Context:
- The repo already stores the NCNN export in `models/ncnn/best_snapshot_ncnn_model/` with `model.ncnn.param`, `model.ncnn.bin`, and metadata for classes `ball` and `robot`.
- The ONNX fallback is available at `models/onnx/best_snapshot.onnx`.
- The PyTorch model is available at `models/yolo26n_futbot/best.pt` and runs through Ultralytics.
- Existing YOLO code expects model output rows shaped as `(x1, y1, x2, y2, conf, cls_id)`. The NCNN export uses `640x640`; the ONNX backend should use the model input shape when it is statically available.
- The diagnostic should be standalone and safe to run from the project root without touching robot hardware.

Design:
- Create `scripts/analyze_image.py`.
- Resolve project paths relative to the script location so it works from any current directory.
- Load the `.pt` model first using Ultralytics from `models/yolo26n_futbot/best.pt`.
- If `.pt` import, model load, or inference fails, print the failure reason and load ONNX Runtime from `models/onnx/best_snapshot.onnx`.
- If ONNX also fails, fall back to NCNN with `ncnn.Net`, `model.ncnn.param`, and `model.ncnn.bin`.
- Preprocess `image.png` with OpenCV to a normalized RGB blob matching the selected model input.
- Parse YOLO rows into scaled image-space boxes for `ball` and `robot` detections above the normal confidence threshold. Weak candidates are only shown when `--debug-low-conf` is enabled so they are not confused with real detections.
- Print backend, model path, image path, and detections to the console.
- Save an annotated image with bounding boxes, class labels, and confidence values.
- Label weak diagnostic candidates with `LOW` when debug mode is enabled.

Testing:
- Compile the script with `py_compile`.
- Run the script against `image.png`.
- Verify console output names the backend used and that an annotated output file is written.

Notes:
- No commit unless explicitly requested.
