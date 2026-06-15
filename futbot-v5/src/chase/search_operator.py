from __future__ import annotations


class SearchOperator:
    def local_reacquire_step(
        self,
        last_cx,
        last_r,
        frame_w,
    ) -> tuple[str, float, float]:
        scan_speed = 42.0
        arc_speed = 28.0
        forward_speed = 55.0
        center = float(frame_w) / 2.0
        deadband = float(frame_w) * 0.16

        if last_cx is None or float(last_cx) <= 0.0:
            return ("scan", -scan_speed, -scan_speed)

        error = float(last_cx) - center
        if abs(error) <= deadband:
            if float(last_r) <= 24.0:
                return ("forward", forward_speed, -forward_speed)
            return ("scan", -scan_speed, -scan_speed)

        turn_speed = min(70.0, 38.0 + abs(error) / max(1.0, center) * 34.0)
        if error > 0.0:
            return ("right", arc_speed + turn_speed, -(arc_speed - turn_speed))
        return ("left", arc_speed - turn_speed, -(arc_speed + turn_speed))

    def field_search_step(self, step_index: int) -> tuple[str, float, float]:
        scan_speed = 46.0
        forward_speed = 62.0
        arc_speed = 34.0
        pattern = (
            ("scan_left", -scan_speed, -scan_speed),
            ("forward", forward_speed, -forward_speed),
            ("scan_right", scan_speed, scan_speed),
            ("forward", forward_speed, -forward_speed),
            ("arc_left", arc_speed * 0.55, -(arc_speed * 1.45)),
            ("forward", forward_speed, -forward_speed),
            ("arc_right", arc_speed * 1.45, -(arc_speed * 0.55)),
            ("forward", forward_speed, -forward_speed),
        )
        return pattern[int(step_index) % len(pattern)]

    def line_aware_field_search_step(
        self,
        step_index: int,
        line_cx,
        frame_w,
    ) -> tuple[str, float, float]:
        scan_speed = 48.0
        arc_speed = 18.0
        turn_speed = 58.0

        if line_cx is None or float(frame_w) <= 0.0:
            turn = scan_speed if int(step_index) % 2 else -scan_speed
            return ("line_scan", turn, turn)

        if float(line_cx) < float(frame_w) / 2.0:
            return ("line_away_right", arc_speed + turn_speed, -(arc_speed - turn_speed))
        return ("line_away_left", arc_speed - turn_speed, -(arc_speed + turn_speed))

    def recover_step(self, last_cx, frame_w) -> tuple[str, float, float]:
        return self.local_reacquire_step(last_cx, 0.0, frame_w)

    def map_step(self, step_index: int, last_cx, frame_w) -> tuple[str, float, float]:
        return self.field_search_step(step_index)
