"""Plan de evasión secuencial: primero retroceso, luego alternancia giro/avance.

Funciones:
    should_avoid()      → detecta obstáculos por umbral de distancia.
    is_ball_proximity()  → suprime falsos triggers cuando el robot está
                           junto a la pelota (la lectura ultrasónica es la
                           pelota, no una pared).
    build_plan()         → genera la lista de pasos (reverse / turn / forward).
"""

from __future__ import annotations

from typing import Optional

from pipeline.utils.pipeline_constants import (
    AVOID_MAX_STEPS,
    AVOID_REVERSE_MS,
    AVOID_REVERSE_SPEED,
    AVOID_TURN_MS,
    AVOID_TURN_SPEED,
    BALL_TOUCH_DIST_MM,
    DIST_TRIGGER_MM,
)


class AvoidOperator:
    def build_plan(
        self,
        last_cx: Optional[float],
        frame_center_x: float,
        max_steps: int = AVOID_MAX_STEPS,
    ) -> list[tuple[str, int, int]]:
        """Genera plan de evasión: retroceso + alternancia giro/avance."""
        steps: list[tuple[str, int, int]] = []
        steps.append(("reverse", AVOID_REVERSE_SPEED, AVOID_REVERSE_MS))

        turn_dir = (
            "turn_left"
            if (last_cx is None or last_cx < frame_center_x)
            else "turn_right"
        )

        for i in range(1, max_steps):
            if i % 2 == 1:
                steps.append((turn_dir, AVOID_TURN_SPEED, AVOID_TURN_MS))
            else:
                steps.append(("forward", AVOID_REVERSE_SPEED, AVOID_REVERSE_MS))

        return steps

    def should_avoid(self, distance_mm: Optional[int]) -> bool:
        """Retorna True si la distancia ultrasónica está por debajo del umbral."""
        return distance_mm is not None and distance_mm <= DIST_TRIGGER_MM

    def is_ball_proximity(
        self,
        ball_visible: bool,
        distance_mm: Optional[int],
        recent_ball: bool,
    ) -> bool:
        """Suprime avoid si la pelota está visible y muy cerca (falso trigger)."""
        if (
            ball_visible
            and recent_ball
            and distance_mm is not None
            and distance_mm <= BALL_TOUCH_DIST_MM
        ):
            return True
        return False
