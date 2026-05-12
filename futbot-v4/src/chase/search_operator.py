from __future__ import annotations


class SearchOperator:
    def recover_step(self, last_cx, frame_w) -> tuple[str, float, float]:
        third = frame_w / 3.0
        speed = 30.0

        if last_cx is None or last_cx < third:
            return ("left", -speed, -(speed * 2.0))
        elif last_cx < 2.0 * third:
            return ("forward", speed, -speed)
        else:
            return ("right", speed * 2.0, speed)

    def map_step(self, step_index: int, last_cx, frame_w) -> tuple[str, float, float]:
        speed = 30.0
        if last_cx is None or last_cx < frame_w / 2.0:
            pattern = ["left", "right", "left"]
        else:
            pattern = ["right", "left", "right"]

        direction = pattern[step_index % 3]
        if direction == "left":
            return ("left", -speed, -(speed * 2.0))
        elif direction == "right":
            return ("right", speed * 2.0, speed)
