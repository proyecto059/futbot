# Task 6 Report: Create main.py + stubs

## Status: DONE

## Summary
Created the stubs subsystem, integration test, and main entry point for the futbot refactor.

## Files Created

| File | Purpose |
|------|---------|
| `futbot/stubs/__init__.py` | Package init, re-exports CameraStub and MotorsStub |
| `futbot/stubs/camera_stub.py` | Synthetic camera stub (green field + orange ball) |
| `futbot/stubs/motors_stub.py` | Command-recording motors stub |
| `futbot/tests/test_integration.py` | Full-loop integration test with stubs |
| `futbot/main.py` | Entry point with FSM orchestration loop |

## Test Results

All 16 tests pass:

- `test_camera.py`: 1 test
- `test_config.py`: 2 tests
- `test_integration.py`: 1 test (new)
- `test_motors.py`: 4 tests
- `test_pipeline.py`: 4 tests
- `test_vision.py`: 4 tests

## TDD Workflow

1. Wrote integration test → FAIL (no stubs module)
2. Created stubs → test PASSED
3. Created main.py
4. Full test suite → 16 passed

## Commit

```
feat: crear main.py con orquestador y stubs de hardware
```
