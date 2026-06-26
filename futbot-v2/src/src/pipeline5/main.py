"""Pipeline 5 — Punto de entrada principal.

Wiring de los 3 servicios que componen el robot:
  1. HybridVisionService  → captura de cámara + detección de pelota (HSV + YOLO)
  2. MotorService         → control de motores vía I2C/Serial
  3. Pipeline5Service     → FSM que orquesta búsqueda y persecución

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
    """Instancia los servicios y ejecuta el loop principal del pipeline5."""
    vision = None
    motors = None
    pipeline = None

    try:
        from vision import HybridVisionService
        from motors import MotorService

        # Importar el nuevo Pipeline5 refactorizado
        from src.pipeline5.pipeline_service import Pipeline5Service

        log.info("event=controller_started mode=pipeline5")

        vision = HybridVisionService()
        motors = MotorService()

        pipeline = Pipeline5Service(vision, motors)
        pipeline.run()  # Loop infinito hasta que se llame a stop() o llegue Ctrl+C

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
        # Cleanup ordenado: pipeline → motores → visión
        if pipeline is not None:
            pipeline.close()
        if motors is not None:
            motors.stop(200)
            motors.close()
        if vision is not None:
            vision.close()

if __name__ == "__main__":
    main()
