import time
import logging

BACKWARD_SPEED = -50
BACKWARD_DUR_MS = 300

TURN_SPEED = 50
TURN_DUR_MS = 500

STOP_DUR_MS = 200

NUM_TURNS = 3

class Pipeline3Service:
    def __init__(self, motors):
        self._motors = motors
        self._running = False
        self._phase = 0

    def tick(self):
        if self._phase == 0:
            self._motors.drive(BACKWARD_SPEED, BACKWARD_SPEED, BACKWARD_DUR_MS)
            logging.info("Movimiento: Retroceder")
            self._phase = 1

        elif self._phase == 1:
            turn_count = 0
            while turn_count < NUM_TURNS:
                self._motors.turn_right(TURN_SPEED, TURN_DUR_MS)
                logging.info(f"Movimiento: Giro derecha ({turn_count + 1}/{NUM_TURNS})")
                turn_count += 1
            self._phase = 2

        elif self._phase == 2:
            self._motors.drive(BACKWARD_SPEED, BACKWARD_SPEED, BACKWARD_DUR_MS)
            logging.info("Movimiento: Retroceder")
            self._phase = 3

        time.sleep(0.05)

    def run(self):
        self._running = True
        logging.info("Pipeline3Service iniciado")

        while self._running:
            self.tick()

    def stop(self):
        self._running = False
        self._motors.stop(STOP_DUR_MS)
        logging.info("Pipeline3Service detenido")