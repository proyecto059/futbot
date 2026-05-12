Goal: reduce zigzag during ball chase.

Evidence from `output/test_goal_blue_2/test_chase_dynamic_attack_blue.log` shows the robot enters `TRACK` and sends motor commands, but short HSV misses immediately transition into `PREDICT`, `RECOVER`, `MAP`, and line escape. Those recovery/search turns alternate direction and make the robot zigzag instead of continuously approaching the ball.

Design: keep `TRACK` active through brief ball dropouts. On a short miss, reuse the last valid forward/turn command with decay for a small number of consecutive frames. Only transition to `PREDICT` and then `RECOVER/MAP` after the ball has been absent long enough to be truly lost. This preserves continuous chase behavior while still allowing search when the ball is gone.

Testing: add a pure helper test for the miss-tolerance decision so one-frame and short dropouts do not leave tracking, while longer loss still does.
