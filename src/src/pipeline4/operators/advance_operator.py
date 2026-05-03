" Operador de avance para pipeline3.

from pipeline3.utils import ADVANCE_SPEED, ADVANCE_DUR_MS


class AdvanceOperator:
 def compute(self, ball_visible: bool) -> tuple:
 if ball_visible:
 return (ADVANCE_SPEED, ADVANCE_SPEED, ADVANCE_DUR_MS)
 return (0.0, 0.0, 0)