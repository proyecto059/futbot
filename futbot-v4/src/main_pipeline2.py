"""Punto de entrada del robot futbolero - Pipeline2 (sin ultrasónico).

Inicializa los 3 servicios (visión, motores, pipeline2) y corre
el loop principal.

El bloque finally cierra todos los servicios en orden inverso: pipeline →
motores → visión.

Uso:
    python src/main_pipeline2.py
    uv run main_pipeline2.py
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")


def main():
    vision = None
    motors = None
    pipeline = None

    try:
        from vision import HybridVisionService
        from motors import MotorService
        from pipeline2 import Pipeline2Service

        log.info("event=controller_started mode=pipeline2")

        vision = HybridVisionService()
        motors = MotorService()

        pipeline = Pipeline2Service(vision, motors)
        pipeline.run()

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
        if pipeline is not None:
            pipeline.close()
        if motors is not None:
            motors.stop(200)
            motors.close()
        if vision is not None:
            vision.close()


if __name__ == "__main__":
    main()