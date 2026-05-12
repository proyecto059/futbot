"""Punto de entrada del robot futbolero — con AP WiFi y WebSocket P2P.

Servicios inicializados en orden (y cerrados en orden inverso):
    1. HybridVisionService  — cámara + YOLO + HSV
    2. UltrasonicService    — sensor de distancia I2C
    3. MotorService         — UART hacia el microcontrolador
    4. WsRunner             — AP WiFi (robot1) + WebSocket P2P en hilo daemon
    5. PipelineService      — FSM principal (loop bloqueante)

Variables de entorno:

    ROBOT_ID      "robot1" (AP/servidor) | "robot2" (cliente)
                  robot1 levanta el AP antes del WebSocket.
                  robot2 espera a conectarse al AP de robot1.

    PEER_IP       IP del robot opuesto.
                  robot1 → 192.168.10.12 (IP fija de robot2 via dnsmasq)
                  robot2 → 192.168.10.1  (IP del AP de robot1)

    WS_PORT       Puerto WebSocket (default 8765)
    ULTRASONIC    "0" para deshabilitar el sensor ultrasónico
    WS_ENABLED    "0" para correr sin WebSocket/AP (modo local de desarrollo)
    SIMULATE_AP   "1" para simular el AP sin hardware (laptop / CI)

Ejecución en la RPi:
    # Robot 1 — enciéndelo primero (levanta el AP)
    ROBOT_ID=robot1 PEER_IP=192.168.10.12 uv run src/main.py

    # Robot 2
    ROBOT_ID=robot2 PEER_IP=192.168.10.1 uv run src/main.py

    # Desarrollo local (sin AP ni hardware)
    WS_ENABLED=0 ULTRASONIC=0 uv run src/main.py
"""

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("turbopi")


# ── Helpers de entorno ────────────────────────────────────────────────────────

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


# ── Configuración ─────────────────────────────────────────────────
ROBOT_ID           = _env_str("ROBOT_ID",     "robot1")
PEER_IP            = _env_str("PEER_IP",       "192.168.10.12")
WS_PORT            = _env_int("WS_PORT",       8765)
ULTRASONIC_ENABLED = _env_bool("ULTRASONIC",   True)
WS_ENABLED         = _env_bool("WS_ENABLED",   True)
SIMULATE_AP        = _env_bool("SIMULATE_AP",  False)

# NUEVAS variables para modos de prueba
CONSOLE_MODE       = _env_bool("CONSOLE_MODE", False)     # servidor como consola
REMOTE_CONTROL     = _env_bool("REMOTE_CONTROL", False)   # cliente recibe comandos


def main() -> None:
    vision     = None
    ultrasonic = None
    motors     = None
    ws_runner  = None
    pipeline   = None

    try:
        from vision import HybridVisionService
        from ultrasonic import UltrasonicService
        from motors import MotorService
        from pipeline import PipelineService
        from communication import RoleState, WsRunner

        log.info(
            "event=controller_started robot_id=%s ws=%s ap=%s sim_ap=%s console=%s remote=%s",
            ROBOT_ID, WS_ENABLED,
            "on" if ROBOT_ID == "robot1" and WS_ENABLED else "off",
            SIMULATE_AP, CONSOLE_MODE, REMOTE_CONTROL,
        )

        # ========== MODO CONSOLA (servidor) ==========
        if CONSOLE_MODE and ROBOT_ID == "robot1":
            if not WS_ENABLED:
                log.error("CONSOLE_MODE requiere WS_ENABLED=1")
                return

            role_state = RoleState(default_role="atacante")
            def dummy_vision_fn():
                return [0.0, 0.0], False

            ws_runner = WsRunner(
                robot_id    = ROBOT_ID,
                peer_ip     = PEER_IP,
                port        = WS_PORT,
                role_state  = role_state,
                vision_fn   = dummy_vision_fn,
                simulate_ap = SIMULATE_AP,
            )
            ws_runner.start()
            log.info("Modo consola activo. Esperando conexión del robot...")
            time.sleep(2)  # dar tiempo a que el cliente se conecte

            print("\n=== Consola de control remoto ===")
            print("Comandos:")
            print("  forward  - avanzar 0.5s")
            print("  backward - retroceder 0.5s")
            print("  left     - girar izquierda 0.5s")
            print("  right    - girar derecha 0.5s")
            print("  stop     - parada de emergencia")
            print("  exit     - salir")
            print()

            while True:
                try:
                    cmd = input("> ").strip().lower()
                    if cmd in ("exit", "quit"):
                        break
                    if cmd == "forward":
                        ws_runner.send_command({"cmd": "forward", "speed": 120, "dur_ms": 500})
                    elif cmd == "backward":
                        ws_runner.send_command({"cmd": "backward", "speed": 120, "dur_ms": 500})
                    elif cmd == "left":
                        ws_runner.send_command({"cmd": "left", "speed": 100, "dur_ms": 500})
                    elif cmd == "right":
                        ws_runner.send_command({"cmd": "right", "speed": 100, "dur_ms": 500})
                    elif cmd == "stop":
                        ws_runner.send_command({"cmd": "emergency_stop"})
                    else:
                        print("Comando no reconocido")
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    log.exception("Error en consola: %s", e)
            return

        # ========== MODO REMOTE CONTROL (cliente) ==========
        if REMOTE_CONTROL and ROBOT_ID == "robot2":
            if not WS_ENABLED:
                log.error("REMOTE_CONTROL requiere WS_ENABLED=1")
                return

            # Necesitamos los servicios de hardware para ejecutar comandos
            motors = MotorService()
            # Opcional: también podríamos tener ultrasonic/vision, pero no son necesarios.

            def command_callback(cmd: dict):
                cmd_type = cmd.get("cmd")
                if cmd_type == "forward":
                    motors.forward(speed=cmd.get("speed", 120), dur_ms=cmd.get("dur_ms", 500))
                elif cmd_type == "backward":
                    motors.reverse(speed=cmd.get("speed", 120), dur_ms=cmd.get("dur_ms", 500))
                elif cmd_type == "left":
                    motors.turn_left(speed=cmd.get("speed", 100), dur_ms=cmd.get("dur_ms", 500))
                elif cmd_type == "right":
                    motors.turn_right(speed=cmd.get("speed", 100), dur_ms=cmd.get("dur_ms", 500))
                elif cmd_type == "emergency_stop":
                    motors.stop()
                    log.warning("EMERGENCY STOP ejecutado")
                else:
                    log.warning("Comando desconocido: %s", cmd_type)

            role_state = RoleState(default_role="atacante")
            def dummy_vision_fn():
                return [0.0, 0.0], False

            ws_runner = WsRunner(
                robot_id    = ROBOT_ID,
                peer_ip     = PEER_IP,
                port        = WS_PORT,
                role_state  = role_state,
                vision_fn   = dummy_vision_fn,
                simulate_ap = SIMULATE_AP,
                command_callback = command_callback,
            )
            ws_runner.start()
            log.info("Modo REMOTE_CONTROL activo. Esperando comandos del servidor...")
            # Mantener el programa vivo
            while True:
                time.sleep(1)
            return

        # ========== MODO NORMAL (autónomo) ==========
        vision     = HybridVisionService()
        ultrasonic = UltrasonicService() if ULTRASONIC_ENABLED else _NullUltrasonic()
        motors     = MotorService()

        role_state = RoleState(default_role="atacante")

        if WS_ENABLED:
            def _vision_fn():
                snap      = vision.tick()
                ball      = snap.get("ball")
                pos       = [float(ball["cx"]), float(ball.get("cy", 0.0))] if ball else [0.0, 0.0]
                ve_pelota = ball is not None
                return pos, ve_pelota

            ws_runner = WsRunner(
                robot_id    = ROBOT_ID,
                peer_ip     = PEER_IP,
                port        = WS_PORT,
                role_state  = role_state,
                vision_fn   = _vision_fn,
                simulate_ap = SIMULATE_AP,
            )
            ws_runner.start()
            log.info(
                "event=ws_runner_started robot_id=%s peer_ip=%s port=%d",
                ROBOT_ID, PEER_IP, WS_PORT,
            )
        else:
            log.warning("event=ws_disabled rol=atacante_permanente")

        pipeline = PipelineService(vision, ultrasonic, motors, role_state=role_state)
        pipeline.run()

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
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


class _NullUltrasonic:
    class _Dto:
        distance_mm = None
    def tick(self):
        return self._Dto()
    def close(self):
        pass


if __name__ == "__main__":
    log.info(
        "🤖 FutbotMX v2 — robot_id=%s peer=%s ws=%s ap=%s",
        ROBOT_ID, PEER_IP,
        "ON" if WS_ENABLED else "OFF",
        "SIMULATE" if SIMULATE_AP else ("ON" if ROBOT_ID == "robot1" else "OFF"),
    )
    main()