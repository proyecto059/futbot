Design: Chase and Vision Fix

Goal: make `scripts/test_chase_dynamic.py` track the ball in real time, attack the goal, and avoid crossing white field lines.

Root-cause evidence:
- Live vision on the Raspberry sees the ball at `cx ~= 187` in a 320 px frame, so the ball is to the robot's right.
- `test_chase_dynamic.py` creates `VisualServoController` but currently bypasses it in TRACK with an inline wheel calculation.
- The inline diagnostic math uses `vL + vR` as forward speed and `vL - vR` as turn, which is inverted for the repo's signed differential convention.

Approach:
- Restore one continuous control path through `VisualServoController.compute`.
- Apply cache and prediction scaling after the controller output using the correct forward/turn decomposition.
- Keep the motor mapping from `DifferentialOperator`, which matches `scripts/test_motors_raw.py`.
- Improve white line detection with a bottom ROI, morphology, and a threshold based on white-pixel ratio.
- Improve goal detection by filtering color masks through large connected components instead of raw mask centroids.

Verification:
- Add/adjust unit tests for control decomposition, goal components, and white-line detection.
- Run local tests.
- Deploy/run short live checks on the Raspberry only after code and tests pass.

No commits will be made.
