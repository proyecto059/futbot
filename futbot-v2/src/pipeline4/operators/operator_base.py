import time


class OperatorBase:
    def __init__(self):
        self._step = 0
        self._sequence = [
            (150, 150, 3000),   # avanzar 3s
            (150,   0,  500),   # girar izq 0.5s
            (150, 150, 1500),   # avanzar 1.5s
            (150,   0,  500),
            (150, 150, 3000),
            (150,   0,  500),
            (150, 150, 1500),
            (150,   0,  500),
        ]

    def get_current(self):
        return self._sequence[self._step]

    def advance(self):
        self._step += 1

    def reset(self):
        self._step = 0

    # ── move() comentado como referencia ──

    # def move(self, step: int):
    #     moves = [
    #         (150.0,  150.0),   # 0: Avanzar
    #         (0,      150.0),   # 1: Adelante derecha
    #         (150.0,  0),       # 2: Adelante izquierda
    #         (-150.0, -150.0),  # 3: Retroceder
    #         (-150.0, 0),       # 4: Retroceder derecha
    #         (0,     -150.0),   # 5: Retroceder izquierda
    #     ]
    #     v_left, v_right = moves[step]
    #     return v_left, v_right, self._dur_ms
