# Attack Geometry Goal Celebration Design

## Goal

Make the robot understand ball-to-goal attack geometry before pushing, capture annotated evidence of the current setup, detect when the ball is inside either goal, and celebrate a goal with a 360 degree spin followed by stop.

## Current Context

The current controller uses ball center/radius plus target goal center X. It delays `PUSH` by horizontal alignment, but it does not know the goal bounding box, goal vertical position, or whether the ball is inside the goal. The capture tooling can save annotated frames, but it does not yet show full goal bboxes or attack geometry for the placed ball/goal setup.

## Approved Design

Start by capturing a frame from the Raspberry Pi into `output/attack_geometry_<timestamp>/` with `raw.jpg`, `annotated.jpg`, and `snapshot.json`. The overlay should show the ball, blue/yellow goal regions, target goal center, ball-to-goal vector, and text status.

Then extend vision DTOs to expose goal bounding boxes. This gives the chase layer enough geometry to determine alignment and goal-scored state. The controller should keep arcing while the ball-to-goal vector is not attack-ready. Push should only happen after confirmed ball visibility and enough ball-goal alignment.

Goal detection should be color-agnostic: if the ball center overlaps either `blue_bbox` or `yellow_bbox` for several frames, declare goal scored. The FSM should enter `CELEBRATE_360`, spin in place for `SPIN_360_MS`, send an explicit stop, and remain stopped.

## Components

- `scripts/capture_attack_geometry.py`: one-shot capture script with overlay and JSON output.
- `src/vision/dto/goals_dto.py`: add optional bbox/center metadata for blue/yellow goals.
- `src/vision/operators/goal_color_detection_operator.py`: compute bbox, centroid X/Y, and pixels.
- `src/chase/attack_geometry.py`: pure helpers for `is_push_ready()` and `is_ball_inside_goal()`.
- `src/chase/ball_goal_controller.py`: use geometry helpers to continue `CHASE`/`ALIGN_ARC` before `PUSH`.
- `scripts/test_chase_dynamic.py`: add `CELEBRATE_360` state and goal confirmation streak.

## Safety

Celebration must always end with a motor stop. Goal detection must require multiple frames to avoid celebrating on one false overlap. Existing line safety remains active outside committed push/celebration logic.

## Verification

- Unit tests for goal bbox extraction, push readiness, ball-inside-goal, and celebration trigger helper behavior.
- `py_compile` for touched modules/scripts.
- One-shot capture saved under `output/` for visual inspection before any motorized trial.
- Short physical trial only after capture confirms detections look correct.
