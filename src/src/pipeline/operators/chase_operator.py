"""Cálculo de velocidades de rueda para perseguir la pelota.

Algoritmo proporcional:
    error = cx - centro → rotación proporcional con deadband (±16 px),
    capped al 70 % de la velocidad base.

Kick directo cuando el radio supera el umbral (pelota muy cerca).
"""

from __future__ import annotations

from pipeline.utils.pipeline_constants import (
    CHASE_DEADBAND_PX,
    CHASE_ROT_GAIN,
    CHASE_SPEED_BASE,
    KICK_RADIUS_PX,
)


class ChaseOperator:
    def compute(self, frame_width: int, ball: dict | None) -> tuple[float, float, int]:
        """Calcula (v_left, v_right, dur_ms) para perseguir la pelota."""
        if ball is None:
            return (0.0, 0.0, 0)

        cx = ball["cx"]
        radius = ball["r"]

        if radius >= KICK_RADIUS_PX:
            return (float(CHASE_SPEED_BASE), float(CHASE_SPEED_BASE), 140)

        error = cx - (frame_width / 2)
        if abs(error) <= CHASE_DEADBAND_PX:
            rot = 0.0
        else:
            rot = CHASE_ROT_GAIN * error

        rot = max(-CHASE_SPEED_BASE * 0.7, min(CHASE_SPEED_BASE * 0.7, rot))
        v_left = CHASE_SPEED_BASE + rot
        v_right = CHASE_SPEED_BASE - rot
        return (v_left, v_right, 140)