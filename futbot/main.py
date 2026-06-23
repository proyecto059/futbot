"""Punto de entrada del robot futbolero.

Inicializa los servicios (camara, vision, motores, pipeline) y ejecuta el
bucle principal FSM.

Modos via variable de entorno FUTBOT_MODE:
  real  -> hardware real en Raspberry Pi 5
  stub  -> desarrollo local con stubs (sin hardware)

Uso:
  FUTBOT_MODE=stub python main.py   # desarrollo local
  python main.py                    # hardware real (default)
"""

from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("futbot")

MODE = os.environ.get("FUTBOT_MODE", "real")
running = True


def _shutdown(signum, frame):
    global running
    log.info("Senal %s recibida, apagando...", signum)
    running = False


def main():
    from config import Config

    cfg = Config()
    cam = None
    mot = None

    log.info("futbot iniciando en modo %s", MODE)

    try:
        if MODE == "stub":
            from stubs.camera_stub import CameraStub
            from stubs.motors_stub import MotorsStub
            cam = CameraStub(cfg)
            mot = MotorsStub(cfg)
            log.info("Usando stubs de hardware")
        else:
            from camera import Camera
            from motors import Motors
            cam = Camera(cfg)
            mot = Motors(cfg)

        from vision import Vision
        from pipeline import Pipeline

        vis = Vision(cfg)
        pip = Pipeline(cfg)
        pip.set_frame_width(cam.width)

        log.info("Servicios inicializados. Ancho de frame: %d", cam.width)
        log.info("Bucle principal iniciado")

        while running:
            frame = cam.grab()
            if frame is None:
                time.sleep(0.005)
                continue

            dets = vis.detect(frame)
            cmd = pip.tick(dets)
            mot.send(cmd)

            time.sleep(0.01)

    except KeyboardInterrupt:
        log.info("Apagado por teclado")
    except Exception as exc:
        log.exception("Error en runtime: %s", exc)
    finally:
        if mot is not None:
            try:
                mot.stop(200)
                mot.close()
            except Exception:
                pass
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass
        log.info("futbot apagado")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    main()
