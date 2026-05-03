"""Punto de entrada — movimiento simple usando pipeline3."""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")


def main():
    motors = None
    pipeline = None

    try:
        from motors import MotorService
        from pipeline3 import Pipeline3Service 

        log.info("event=controller_started mode=pipeline3_simple")

        motors = MotorService()
        pipeline = Pipeline3Service(motors) 

        pipeline.run()

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
        if pipeline is not None:
            pipeline.stop()
        if motors is not None:
            motors.stop(200)
            motors.close()


if __name__ == "__main__":
    main()