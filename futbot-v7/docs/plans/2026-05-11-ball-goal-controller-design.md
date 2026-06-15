Design: Ball-to-Goal Controller

Goal: follow the ball in real time, push it into the selected goal, and never cross white field lines.

Context and evidence:
- Raspberry vision `tick()` measured about 80 FPS, average tick about 9.9 ms, so FPS is acceptable.
- The existing monolithic chase script mixes ball pursuit, goal attack, line safety, ultrasonic avoid, recovery, and search.
- Repeated physical tests showed fixed turn biases and minimum turns do not generalize across ball positions.
- White line detection must run before any motor command; when calibrated with the line visible, full-frame detection caught the line while bottom-only ROI missed it.

Approach:
- Add a pure controller that maps ball/goal/line observations to wheel commands.
- Keep `ATTACK_BLUE=1/0` as the target-goal selector.
- Use continuous arc motion, not stop-and-turn phases.
- Blend control objectives by distance:
  - Far ball: prioritize centering and approaching the ball.
  - Near ball: blend ball centering with target-goal alignment to push toward the selected goal.
  - Goal missing: keep centering the ball and only push when aligned.
- Treat line detection as a hard safety gate before any chase or kick motor command.
- Keep HSV synchronous and YOLO asynchronous; reduce runtime logging noise and add FPS diagnostics.

Verification:
- Unit-test the pure controller across left/right/center ball positions, both target goals, line safety, missing goal, and close push mode.
- Run local and Raspberry tests.
- Run static FPS/vision sampling on Raspberry.
- Run short motor tests with the human observer confirming physical direction and line safety.

No commits will be made.
