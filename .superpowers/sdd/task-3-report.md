# Task 3 Report: Crear `vision.py`

## Status: DONE

## Summary

Created `futbot/vision.py` with the hybrid YOLO + HSV detection pipeline and its test suite.

## TDD Execution

| Phase | Result |
|---|---|
| RED | 4 tests FAILED — `ModuleNotFoundError: No module named 'vision'` |
| GREEN | 4 tests PASSED + 3 existing tests PASSED (7 total) |

## Tests

- `test_detections_dataclass` — verifies Ball, Goal, WhiteLine, Detections dataclasses
- `test_detections_empty` — verifies Detections defaults to None for all fields
- `test_vision_hsv_ball_detection` — synthetic orange circle detected by HSV pipeline
- `test_vision_no_ball` — empty frame returns no detections

## Files Created

- `futbot/vision.py` (377 lines) — Vision class with `detect()`, dataclasses, HSV + YOLO backends
- `futbot/tests/test_vision.py` (50 lines) — 4 tests

## Commit

```
532a12c feat: crear vision.py con deteccion hibrida YOLO+HSV
```

## Regression Check

All 7 tests pass (3 existing + 4 new), no regressions.
