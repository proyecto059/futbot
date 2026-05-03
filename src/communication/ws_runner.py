"""Runner del WebSocket — corre el loop asyncio en un hilo daemon separado.

De esta forma el pipeline síncrono (PipelineService) y el WebSocket
(asyncio) coexisten sin bloquearse mutuamente.  La comunicación entre
ambos ocurre a través del objeto `RoleState` (thread-safe).

Modo servidor (robot1):
    Escucha conexiones entrantes de robot2.
    Recibe el estado de robot2, calcula roles, responde y actualiza RoleState.

Modo cliente (robot2):
    Se conecta al servidor (robot1) cada 2 s si hay desconexión.
    Envía su propio estado, recibe los roles asignados y actualiza RoleState.

Uso desde main.py::

    from communication.ws_runner import WsRunner

    runner = WsRunner(
        robot_id="robot1",
        peer_ip="192.168.22.47",
        port=8765,
        role_state=rol_state,
        vision_fn=lambda: (vision.last_position(), vision.ball_visible()),
    )
    runner.start()          # lanza el hilo daemon
    # ... loop principal ...
    runner.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable

import websockets
import websockets.exceptions

from communication.communication_gateway import CommunicationGateway
from communication.role_state import RoleState

log = logging.getLogger("turbopi.communication.ws_runner")

# Frecuencia de envío del estado en modo cliente (10 Hz)
CLIENT_SEND_HZ = 10
CLIENT_RECONNECT_SECS = 2.0


class WsRunner:
    """Corre el WebSocket en un hilo daemon independiente.

    Args:
        robot_id:   "robot1" (servidor) | "robot2" (cliente).
        peer_ip:    IP del robot opuesto (relevante sólo para robot2).
        port:       Puerto WebSocket.
        role_state: Estado compartido que escribe tras cada asignación.
        vision_fn:  Callable que devuelve (pos: list[float], ve_pelota: bool)
                    con datos actuales de HybridVisionService.
                    Ejemplo: lambda: ([cx, cy], ball_visible)
    """

    def __init__(
        self,
        robot_id: str,
        peer_ip: str,
        port: int,
        role_state: RoleState,
        vision_fn: Callable[[], tuple[list[float], bool]],
    ) -> None:
        self._robot_id   = robot_id
        self._peer_ip    = peer_ip
        self._port       = port
        self._role_state = role_state
        self._vision_fn  = vision_fn
        self._is_server  = robot_id == "robot1"
        self._gateway    = CommunicationGateway(robot_id, role_state)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Ciclo de vida ────────────────────────────────────────────────────

    def start(self) -> None:
        """Arranca el hilo daemon del WebSocket."""
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ws-runner",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "event=ws_runner_started robot_id=%s mode=%s",
            self._robot_id,
            "server" if self._is_server else "client",
        )

    def stop(self) -> None:
        """Señala al hilo que debe detenerse."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("event=ws_runner_stopped robot_id=%s", self._robot_id)

    # ── Loop asyncio interno ─────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.run(
            self._run_server() if self._is_server else self._run_client()
        )

    # ── Modo Servidor — Robot 1 ──────────────────────────────────────────

    async def _run_server(self) -> None:
        async def handler(websocket):
            log.info("event=remote_connected addr=%s", websocket.remote_address)
            try:
                async for raw_msg in websocket:
                    if self._stop_event.is_set():
                        break
                    # Actualizar estado local con datos reales de visión
                    pos, ve_pelota = self._vision_fn()
                    self._gateway.update_local_state(pos, ve_pelota)
                    await self._gateway.on_message(websocket, raw_msg)
            except websockets.exceptions.ConnectionClosed:
                log.warning("event=remote_disconnected addr=%s", websocket.remote_address)

        log.info("event=ws_server_listening port=%d", self._port)
        async with websockets.serve(handler, "0.0.0.0", self._port):
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)

    # ── Modo Cliente — Robot 2 ───────────────────────────────────────────

    async def _run_client(self) -> None:
        uri = f"ws://{self._peer_ip}:{self._port}"
        interval = 1.0 / CLIENT_SEND_HZ

        while not self._stop_event.is_set():
            try:
                async with websockets.connect(uri) as ws:
                    log.info("event=ws_client_connected uri=%s", uri)

                    while not self._stop_event.is_set():
                        pos, ve_pelota = self._vision_fn()
                        payload = json.dumps({"pos": pos, "ve_pelota": ve_pelota})
                        await ws.send(payload)

                        raw_resp = await ws.recv()
                        respuesta = json.loads(raw_resp)

                        if "error" in respuesta:
                            log.warning("event=server_error msg=%s", respuesta["error"])
                        else:
                            mi_rol = respuesta.get(self._robot_id, "espera")
                            self._role_state.set(mi_rol)
                            log.debug("event=roles_received roles=%s mi_rol=%s", respuesta, mi_rol)

                        await asyncio.sleep(interval)

            except Exception as exc:
                if not self._stop_event.is_set():
                    log.warning(
                        "event=ws_client_disconnected error=%s retry_in=%.1fs",
                        exc, CLIENT_RECONNECT_SECS,
                    )
                    await asyncio.sleep(CLIENT_RECONNECT_SECS)
