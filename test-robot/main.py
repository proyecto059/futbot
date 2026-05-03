"""main.py — Entry point del test-robot (TurboPi / robot legacy).

Este archivo era binario en el repositorio original. Es el punto de entrada
del sub-proyecto `test-robot/` que usa la capa de hardware directa (hardware.py)
en lugar de los servicios modulares de `src/`.

Para ejecutar en el robot:
    cd test-robot/
    uv run main.py

Para pruebas específicas ve directamente a:
    uv run play_futbot.py     # modo fútbol completo
    uv run test_motors.py     # prueba de motores
    uv run diag_vision.py     # diagnóstico de visión
"""

import sys
import time
import logging

log = logging.getLogger("turbopi.test_robot")


def main():
    log.info("=== FutbotMX test-robot ===")
    log.info("Selecciona un modo:")
    log.info("  1. play_futbot.py   — Jugar fútbol")
    log.info("  2. diag_vision.py   — Diagnóstico de visión")
    log.info("  3. test_motors.py   — Prueba de motores")
    log.info("  4. test_sonic.py    — Prueba de ultrasonido")
    log.info("")
    log.info("Ejecuta directamente: uv run <script>.py")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
