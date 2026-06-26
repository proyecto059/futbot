"""Pipeline 4 — Punto de entrada principal.

Wiring de los 3 servicios que componen el robot:
  1. HybridVisionService  → captura de cámara + detección de pelota/porterías (HSV + YOLO)
  2. MotorService         → control de motores vía Serial
  3. Pipeline4Service     → FSM que orquesta búsqueda, avance, alineación y disparo

Ejecutar con:
    python main.py

Para detener: Ctrl+C (manejado vía KeyboardInterrupt, hace cleanup ordenado).
"""

import sys
import os
import logging

# Añadir el directorio 'src' principal al PYTHONPATH para importar correctamente 'vision' y 'motors'
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")


def main():
    """Instancia los servicios y ejecuta el loop principal del pipeline4."""
    vision = None
    motors = None
    pipeline = None

    try:
        from vision import HybridVisionService
        from motors import MotorService

        from src.pipeline4.pipeline_service import Pipeline4Service

        log.info("event=controller_started mode=pipeline4")

        vision = HybridVisionService()
        motors = MotorService()

        pipeline = Pipeline4Service(vision, motors)
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
