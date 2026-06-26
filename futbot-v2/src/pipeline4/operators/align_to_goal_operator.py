"""Operador de alineación a portería — rota lentamente hasta centrar pelota y portería.

Estrategia:
  1. Selecciona la portería visible (yellow > blue).
  2. Calcula error combinado de pelota (70%) y portería (30%) respecto al centro.
  3. Rota en la dirección que reduce el error con pulsos cortos.
  4. Marca alineado cuando ambos están dentro de la tolerancia.
"""

from src.pipeline4.utils.pipeline_constants import (
    ALIGN_SPEED,
    ALIGN_TURN_DUR_MS,
    ALIGN_CENTER_TOLERANCE,
    STOP_DUR_MS,
)


class AlignToGoalOperator:
    def __init__(self):
        self._aligned = False

    def compute(self, frame_width, ball, goals):
        """Retorna (v_left, v_right, dur_ms) para rotar hacia la alineación.

        Args:
            frame_width: Ancho del frame en píxeles.
            ball: Dict con ball["cx"], ball["cy"], ball["r"] o None.
            goals: Dict con goals["yellow"], goals["yellow_cx"],
                   goals["blue"], goals["blue_cx"].

        Returns:
            (v_left, v_right, dur_ms) — signos opuestos = giro sobre eje.
        """
        target_cx = None
        if goals.get("yellow"):
            target_cx = goals.get("yellow_cx")
        elif goals.get("blue"):
            target_cx = goals.get("blue_cx")

        if ball is None or target_cx is None:
            self._aligned = False
            return 0.0, 0.0, STOP_DUR_MS

        half_w = frame_width / 2.0
        ball_error = ball["cx"] - half_w
        goal_error = target_cx - half_w

        if abs(ball_error) <= ALIGN_CENTER_TOLERANCE and abs(goal_error) <= ALIGN_CENTER_TOLERANCE:
            self._aligned = True
            return 0.0, 0.0, STOP_DUR_MS

        self._aligned = False

        combined_error = 0.7 * ball_error + 0.3 * goal_error

        if combined_error > 0:
            return float(ALIGN_SPEED), -float(ALIGN_SPEED), ALIGN_TURN_DUR_MS
        else:
            return -float(ALIGN_SPEED), float(ALIGN_SPEED), ALIGN_TURN_DUR_MS

    def is_aligned(self):
        return self._aligned

    def reset(self):
        self._aligned = False
