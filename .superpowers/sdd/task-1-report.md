# Task 1 Report

**Status:** DONE

## Commits
- `27774cd` — `feat: crear config.py con constantes unificadas de v8`

## Test Summary
2 passed — `test_config_defaults` and `test_crc8` both pass against the new `futbot/config.py`.

## Files Created
- `futbot/config.py` — `Config` dataclass, `CRC8_TABLE`, `crc8()` function
- `futbot/tests/test_config.py` — 2 tests per task brief spec

## Notes
- Followed TDD: wrote test, confirmed RED (`ModuleNotFoundError`), wrote implementation, confirmed GREEN (2 passed), committed.
