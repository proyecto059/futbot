"""Punto de entrada del robot futbolero — con comunicación WebSocket P2P.

Inicializa 5 servicios en este orden:
    1. HybridVisionService  — cámara + YOLO + HSV (2 hilos en background)
    2. UltrasonicService    — sensor de distancia
    3. MotorService         — UART hacia el microcontrolador
    4. WsRunner             — WebSocket P2P en hilo daemon
    5. PipelineService      — FSM principal (loop bloqueante)

El `RoleState` es el objeto compartido que conecta al WsRunner
(lo escribe) con el PipelineService (lo lee en cada tick).

Configuración por variables de entorno o editando la sección marcada:

    ROBOT_ID   "robot1" (servidor) | "robot2" (cliente)
    PEER_IP    IP del robot opuesto
    WS_PORT    Puerto WebSocket (default 8765)
    ULTRASONIC "0" para deshabilitar el sensor ultrasónico

Ejecución::

    # Robot 1 (servidor) — enciéndelo primero
    ROBOT_ID=robot1 PEER_IP=192.168.22.47 uv run src/main.py

    # Robot 2 (cliente)
    ROBOT_ID=robot2 PEER_IP=192.168.22.17 uv run src/main.py

    # Sin WebSocket (sólo pipeline local, siempre atacante)
    WS_ENABLED=0 uv run src/main.py
"""

from __future__ import annotations

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")


# ── Helpers de entorno ───────────────────────────────────────────────────────

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ── Configuración ─────────────────────────────────────────────────────────────
# Edita estas constantes o pásalas como variables de entorno.

ROBOT_ID          = _env_str("ROBOT_ID",   "robot1")    # "robot1" | "robot2"
PEER_IP           = _env_str("PEER_IP",    "192.168.22.47")
WS_PORT           = _env_int("WS_PORT",    8765)
ULTRASONIC_ENABLED = _env_bool("ULTRASONIC", True)
WS_ENABLED        = _env_bool("WS_ENABLED", True)       # False = sin WebSocket

# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    vision     = None
    ultrasonic = None
    motors     = None
    ws_runner  = None
    pipeline   = None

    try:
        # ── 1. Visión ────────────────────────────────────────────────────
        from vision import HybridVisionService
        vision = HybridVisionService()
        log.info("event=vision_started frame_width=%d", vision.frame_width)

        # ── 2. Ultrasonido ───────────────────────────────────────────────
        from ultrasonic import UltrasonicService
        ultrasonic = UltrasonicService() if ULTRASONIC_ENABLED else _NullUltrasonic()
        log.info("event=ultrasonic_started enabled=%s", ULTRASONIC_ENABLED)

        # ── 3. Motores ───────────────────────────────────────────────────
        from motors import MotorService
        motors = MotorService()
        log.info("event=motors_started")

        # ── 4. RoleState + WsRunner ──────────────────────────────────────
        from communication import RoleState, WsRunner

        role_state = RoleState(default_role="atacante")

        if WS_ENABLED:
            def vision_fn():
                """Provee el estado local al gateway WebSocket.

                Usa el último snapshot de visión para:
                - pos:       centro de la pelota en píxeles [cx, cy]
                             (o [0,0] si no se detecta)
                - ve_pelota: True si la pelota está visible en el frame.
                """
                snap = vision.tick()
                ball = snap.get("ball")
                if ball:
                    pos       = [float(ball["cx"]), float(ball.get("cy", 0.0))]
                    ve_pelota = True
                else:
                    pos       = [0.0, 0.0]
                    ve_pelota = False
                return pos, ve_pelota

            ws_runner = WsRunner(
                robot_id=ROBOT_ID,
                peer_ip=PEER_IP,
                port=WS_PORT,
                role_state=role_state,
                vision_fn=vision_fn,
            )
            ws_runner.start()
            log.info(
                "event=ws_runner_started robot_id=%s peer_ip=%s port=%d",
                ROBOT_ID, PEER_IP, WS_PORT,
            )
        else:
            log.warning("event=ws_disabled reason=WS_ENABLED=0 rol=atacante_permanente")

        # ── 5. Pipeline principal ────────────────────────────────────────
        from pipeline import PipelineService

        pipeline = PipelineService(
            vision,
            ultrasonic,
            motors,
            role_state=role_state,   # ← integración con WebSocket
        )
        log.info("event=pipeline_started robot_id=%s", ROBOT_ID)
        pipeline.run()  # bloqueante hasta KeyboardInterrupt

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
        # Cierre en orden inverso
        if pipeline is not None:
            pipeline.close()
        if ws_runner is not None:
            ws_runner.stop()
        if motors is not None:
            motors.stop(200)
            motors.close()
        if ultrasonic is not None:
            ultrasonic.close()
        if vision is not None:
            vision.close()
        log.info("event=all_services_closed")


# ── Stub de ultrasonido deshabilitado ────────────────────────────────────────

class _NullUltrasonic:
    """Reemplaza UltrasonicService cuando el sensor está deshabilitado."""

    class _Dto:
        distance_mm = None

    def tick(self):
        return self._Dto()

    def close(self):
        pass


if __name__ == "__main__":
    log.info(
        "🤖 FutbotMX v2 — robot_id=%s ws=%s peer=%s:%d",
        ROBOT_ID, "ON" if WS_ENABLED else "OFF", PEER_IP, WS_PORT,
    )
    main()
