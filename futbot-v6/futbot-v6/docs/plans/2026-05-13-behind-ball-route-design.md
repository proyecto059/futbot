# Behind-Ball Route Design

Goal: stop driving directly at the ball, and make the robot first move to a point behind the ball relative to the target goal.

Context: on `output/attack_geometry_20260513_222121`, the ball is at `(96, 85)` and the blue goal center is at `(15, 73)`. The correct push vector is ball to goal, but the current controller still chooses `CHASE` because the ball radius is small. That drives toward the ball and causes side-passing, accidental pushes, and wall collisions when detection jumps.

Design:
- Add pure geometry helpers that compute:
  - the push vector from ball to goal,
  - the behind-ball target point `ball + normalize(ball - goal) * offset`,
  - a route command toward that point.
- Use the behind point for the overlay, so the image shows:
  - green push vector ball to goal,
  - magenta behind-ball target,
  - cyan intended route from robot image center to the behind-ball target.
- Keep motor behavior conservative:
  - if the robot is not behind the ball yet, avoid forward ball contact;
  - if goal memory is missing or unstable, do not chase aggressively;
  - only push when ball and target goal are tightly aligned.

Recommended approach: implement the route as pure geometry first, visualize it on the saved capture, and only later run motors after the overlay route looks sane. This avoids another blind motor trial.

Testing:
- Unit-test the geometry on the saved-capture coordinates.
- Unit-test the overlay draws the behind-ball target in the expected area.
- Keep existing controller and vision tests green.

Notes:
- No commits are made unless explicitly requested.
- No motor run is part of this design step.
