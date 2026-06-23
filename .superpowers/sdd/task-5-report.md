# Task 5 Report: `pipeline.py`

**Status:** DONE

**Commits:**
- `c8c6cec` — `feat: crear pipeline.py con FSM SEARCH/CHASE/RECOVERY`

**Test summary:** 4/4 passed — starts in SEARCH, SEARCH→CHASE on ball detection, CHASE→RECOVERY on ball loss after timeout, centered ball produces straight forward motion. All 15 existing tests also pass (no regressions).

**Notes:**
- `test_chase_to_recovery_transition` required a minor timing fix: `_miss_start` is set to `now` on the first tick *without* a ball (not retroactively), so the sleep must happen *after* that first empty tick to accumulate `miss_secs`. Added `pip.tick(Detections())` before `time.sleep(1.0)` to anchor `_miss_start` correctly.
- `opencv-python` and `numpy` were installed via `python -m ensurepip` + `python -m pip install opencv-python numpy` in the venv (they were missing).

**Report file:** `.superpowers/sdd/task-5-report.md`
