"""Punto de entrada del robot futbolero.

Inicializa los 4 servicios (visión, ultrasonido, motores, pipeline) y corre
el loop principal.  Los imports son lazy (dentro de try) para que los tests
puedan importar funciones puras sin necesitar hardware conectado.

El bloque finally cierra todos los servicios en orden inverso: pipeline →
motores → ultrasonido → visión.  Maneja inicialización parcial (si un
servicio falla, los anteriores se cierran correctamente).

Uso:
    python src/main.py        # en la Raspberry Pi
    uv run main.py            # con uv
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
    ultrasonic = None
    motors = None
    pipeline = None

    try:
        from vision import HybridVisionService
        from ultrasonic import UltrasonicService
        from motors import MotorService
        from pipeline import PipelineService

        log.info("event=controller_started")

        vision = HybridVisionService()
        ultrasonic = UltrasonicService()
        motors = MotorService()

        pipeline = PipelineService(vision, ultrasonic, motors)
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
        if ultrasonic is not None:
            ultrasonic.close()
        if vision is not None:
            vision.close()


if __name__ == "__main__":
    main()
