# Line-Aware Search And Arc Goal Design

## Goal

Make `scripts/test_chase_dynamic.py` keep moving intelligently near field lines while preserving safety, reacquire the orange ball more actively, and avoid direct pushes unless the ball-goal geometry is aligned enough to score.

## Current Problem

The latest physical trial showed the robot was legitimately near white boundary lines. The current FSM treats line detection plus no visible ball as a stop condition during cooldown, so it repeatedly prints `LINE hold: no ball, no blind search` and spends most of the trial stationary. The controller also allows `PUSH` when the ball is close and a goal is visible, even if the robot has not dynamically positioned behind the ball relative to the goal.

## Approved Approach

Use the line as an avoidance signal, not a freeze signal. When a line is confirmed, the robot should retreat, turn away from the line, and resume search immediately. During line cooldown, the robot may rotate or arc away from the line, but should not drive straight forward blindly.

Use ball-goal geometry to delay push. When the ball is close but off the scoring line, the controller should stay in `CHASE` and drive a continuous arc that reduces the ball-goal angular gap. It should only enter `PUSH` when the ball is close and reasonably aligned with the target goal.

## Behavior Targets

- If the ball starts in the upper-left and the target goal is lower-right, the robot should not drive straight into the ball.
- The robot should follow the ball in real time while arcing to a better attack angle.
- The robot should push only after the ball and target goal are aligned enough for a scoring attempt.
- If the robot sees a boundary line while searching, it should avoid the line and keep searching rather than staying stopped.
- If no ball is visible and line cooldown is active, the robot should prefer safe turning/arc-away search commands over forward search commands.

## Components

- `src/chase/search_operator.py`: add line-aware search variants that replace unsafe forward steps with safe turns/arcs during line cooldown.
- `src/chase/ball_goal_controller.py`: add alignment-gated push logic and stronger close-ball arc behavior when the goal is offset from the ball.
- `src/chase/visual_servo_controller.py`: adjust the no-ball/line hold helper so cooldown does not block all motion.
- `scripts/test_chase_dynamic.py`: store the last line center and use line-aware search after line avoidance.
- Focused tests in `tests/test_search_operator.py`, `tests/test_ball_goal_controller.py`, and `tests/test_visual_servo_controller.py`.

## Safety

Line detection still prevents blind forward motion near a boundary. The change is to replace indefinite stop with retreat plus safe turning/arc-away movement. Push commit still requires confirmed ball frames.

## Verification

- Run focused unit tests for search, controller, and visual-servo helpers.
- Compile the physical script and touched modules.
- Sync to Raspberry Pi only after local verification passes.
- Run a short physical trial with the approved layout and inspect whether the log contains search movement, continuous arc chase, and delayed push.
