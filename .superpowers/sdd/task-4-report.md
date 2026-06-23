# Task 4 Report: Crear `motors.py`

- **Status:** DONE
- **Commits created:** `b3713ee` — `feat: crear motors.py con protocolo UART y control diferencial`
- **Test summary:** 4 passed — `test_motor_command_dataclass`, `test_differential_mapping`, `test_pwm_conversion`, `test_crc8_uart_frame`
- **Report file:** `.superpowers/sdd/task-4-report.md`

## TDD Trace

| Phase | Action | Result |
|-------|--------|--------|
| RED | Wrote `test_motors.py` (4 tests) | 1 failed (`ModuleNotFoundError: motors`), 3 passed |
| GREEN | Wrote `motors.py` with `MotorCommand` dataclass + `Motors` class | 4 passed |
| COMMIT | Staged + committed both files | `b3713ee` |

## Files Created

- `futbot/motors.py` — `MotorCommand` dataclass and `Motors` class with UART protocol, differential mapping, angle-to-PWM conversion, and CRC8 checksums. `import serial` is lazy inside `Motors.__init__`.
- `futbot/tests/test_motors.py` — 4 unit tests covering dataclass fields, differential wheel-to-motor mapping, angle-to-PWM conversion, and CRC8 frame checksum.
