"""Punto de entrada del robot futbolero — pipeline2 (ver pelota → avanzar).

Inicializa visión, motores y pipeline2 y corre el loop principal.
Los imports son lazy (dentro de try) para que los tests puedan importar
funciones puras sin necesitar hardware conectado.

Pipeline2 no usa ultrasonido — solo visión + motores.

El bloque finally cierra todos los servicios en orden inverso: pipeline →
motores → visión.  Maneja inicialización parcial (si un servicio falla,
los anteriores se cierran correctamente).

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
    motors = None
    pipeline = None

    try:
        from vision import HybridVisionService
        from motors import MotorService
        from pipeline2 import Pipeline2Service

        log.info("event=controller_started pipeline=pipeline2")

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