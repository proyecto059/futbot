# yoloe26n_v2 NCNN Model Switch Design

## Goal

Use the new `models/yoloe26n_v2/` export for the live vision pipeline and for `scripts/analyze_image.py`.

## Selected Approach

Switch the shared YOLO configuration to the new export and add class grouping so the rest of the robot still consumes the existing `ball` and `robot` concepts.

## Model Details

- NCNN model directory: `models/yoloe26n_v2/ncnn/yoloe26n_v2_ncnn_model`
- ONNX model path: `models/yoloe26n_v2/onnx/yoloe26n_v2.onnx`
- Input size: `320x320`
- Task: `segment`
- Ball classes: `0, 1, 2, 3`
- Robot classes: `4, 5, 6, 7, 8, 9, 10, 11`

## Pipeline Changes

- Update shared constants in `src/vision/utils/vision_constants.py` to point at the new model paths and use `YOLO_IMGSZ = 320`.
- Update `YoloInferenceOperator` to treat any ball class as a ball and any robot/vehicle class as a robot.
- Update NCNN/ONNX output decoding to support YOLOe segmentation-style output by keeping boxes and class scores while ignoring mask coefficients.
- Update `scripts/analyze_image.py` to use the new model paths, grouped labels, and the same segmentation-compatible output decoding.

## Non-Goals

- Do not decode segmentation masks yet.
- Do not add fallback compatibility for the old model unless a caller explicitly passes old paths.

## Verification

- Add/update focused tests for model paths, image size, class grouping, and segmentation output decode.
- Run targeted vision/analyzer tests.
- Compile `scripts/analyze_image.py`.
- Sync to Raspberry Pi and run `--rpi --debug` plus a short `--video` capture.
