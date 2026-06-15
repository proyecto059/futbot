# Blue Goal Runtime Fix Design

Goal: make the blue-goal attack run stop chasing tiny HSV noise, avoid false goal celebrations, and push sooner when the ball is visibly aligned with the blue goal.

Context from the May 19 Raspberry logs:
- The target was blue, but several frames only saw yellow, so the robot correctly had no target goal.
- Many tracked balls had `r=4..7`, which is too small and noisy for motor decisions.
- The robot declared `GOAL scored color=blue` without a recent `PUSH`, so visual overlap alone can trigger a false celebration.
- The robot often saw aligned blue-goal cases around `r=24..36`, but `goal_push_radius=45` kept it in `CHASE`/`ALIGN_ARC` instead of pushing.
- Goal memory can still jump between opposite sides after intermittent detections, causing route commands toward stale or wrong goal centers.

Design:
- Raise the default runtime ball visibility radius from `4` to `8` pixels.
- Lower the controller's aligned-goal push radius from `45` to `30` pixels while keeping `push_alignment_dx=35`.
- Gate scoring so `CELEBRATE_360` only starts after a recent confirmed `PUSH`, not from visual overlap alone.
- Make goal memory reject side flips more consistently while memory is still fresh.
- Keep all changes conservative and testable; no color-goal broadening and no ultrasonic/IMU assumptions.

Testing:
- Unit-test the smaller aligned push threshold.
- Unit-test that scoring is ignored without recent push context and accepted with push context.
- Unit-test stricter fresh goal-memory side flip rejection.
- Run focused pytest suites and py_compile before syncing to Raspberry.
- Run Raspberry trial with a bounded timeout and explicit stop.

Notes:
- No commit unless explicitly requested.
- Trial target is blue (`ATTACK_BLUE=1`).
