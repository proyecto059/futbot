"""Calculo dinamico frame-by-frame para ir hacia la pelota.

Ambas ruedas siempre hacia adelante. La rueda externa va mas rapido
y la interna mas lento proporcionalmente al error.

    error_norm = |error| / (frame_width / 2)   -> 0..1
    diff = base * error_norm * 0.8

    rueda externa = base + diff  (rapida)
    rueda interna = base - diff  (lenta pero siempre >= 0)

Esto garantiza avance continuo con giro suave y progresivo.
"""

from __future__ import annotations

from src.pipeline6.utils.pipeline_constants import (
    CHASE_SPEED_BASE,
    CHASE_DEADBAND_PX,
    KICK_RADIUS_PX,
)


class ChaseOperator:
    def compute(self, frame_width: int, ball: dict | None) -> tuple[float, float, int]:
        if ball is None:
            return (0.0, 0.0, 0)

        cx = ball["cx"]
        radius = ball["r"]
        half_w = frame_width / 2

        if radius >= KICK_RADIUS_PX:
            return (float(CHASE_SPEED_BASE), float(CHASE_SPEED_BASE), 100)

        error = cx - half_w

        if abs(error) <= CHASE_DEADBAND_PX:
            return (float(CHASE_SPEED_BASE), float(CHASE_SPEED_BASE), 100)

        error_norm = min(abs(error) / half_w, 1.0)
        diff = CHASE_SPEED_BASE * error_norm * 0.8

        if error > 0:
            v_left = CHASE_SPEED_BASE + diff
            v_right = CHASE_SPEED_BASE - diff
        else:
            v_left = CHASE_SPEED_BASE - diff
            v_right = CHASE_SPEED_BASE + diff

        v_left = max(0.0, v_left)
        v_right = max(0.0, v_right)
        return (v_left, v_right, 100)
