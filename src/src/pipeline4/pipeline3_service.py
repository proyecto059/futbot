import time
import logging

BACKWARD_SPEED = -50
BACKWARD_DUR_MS = 300

TURN_SPEED = 50
TURN_DUR_MS = 400

STOP_DUR_MS = 200


class SimpleMotionService:
    def __init__(self, motors):
        self._motors = motors
        self._running = False
        self._step = 0  # Controla la secuencia

    def tick(self):
        if self._step == 0:
            # 1. Retroceder
            self._motors.drive(BACKWARD_SPEED, BACKWARD_SPEED, BACKWARD_DUR_MS)
            logging.info("Movimiento: Retroceder")

        elif self._step == 1:
            # 2. Girar a la derecha
            self._motors.drive(TURN_SPEED, 0, TURN_DUR_MS)
            logging.info("Movimiento: Giro derecha")

        elif self._step == 2:
            # 3. Girar a la izquierda
            self._motors.drive(0, TURN_SPEED, TURN_DUR_MS)
            logging.info("Movimiento: Giro izquierda")

        # Avanza al siguiente paso
        self._step = (self._step + 1) % 3

        time.sleep(0.05)  # pequeña pausa entre acciones

    def run(self):
        self._running = True
        logging.info("SimpleMotion iniciado")

        while self._running:
            self.tick()

    def stop(self):
        self._running = False
        self._motors.stop(STOP_DUR_MS)
        logging.info("SimpleMotion detenido")