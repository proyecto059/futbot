# Task 2 Report: Create camera.py

**Status:** DONE

## Commits Created
- `3a11b7c` — feat: crear camera.py con resolucion de backend unificada

## Test Summary
- 3/3 tests passing (1 camera, 2 config)

## Files
- Created: `futbot/camera.py` (286 lines)
- Created: `futbot/tests/test_camera.py` (16 lines)

## TDD Cycle
1. RED: `ModuleNotFoundError: No module named 'camera'` — confirmed
2. GREEN: `test_camera_creates_instance` passes — Camera raises `RuntimeError` with "cámara" in message on Windows (no /dev/video*, no picamera2, no GStreamer)
3. REFACTOR: N/A (mechanical transcription)

## Notes
- Backend resolution falls through all 4 backends on Windows, correctly raising RuntimeError as expected by the test
- All existing tests (`test_config_defaults`, `test_crc8`) continue to pass
