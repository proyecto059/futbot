"""Runner del WebSocket — corre el loop asyncio en un hilo daemon separado.

El pipeline síncrono (PipelineService) y el WebSocket (asyncio) coexisten
sin bloquearse. La comunicación entre ambos ocurre a través del RoleState
(thread-safe).

Modo servidor (robot1 — AP):
    1. ApManager arranca hostapd + dnsmasq.
    2. Espera a que wlan0 tenga IP 192.168.10.1 (hasta AP_READY_TIMEOUT).
    3. Escucha conexiones WebSocket de robot2 en :8765.
    4. Por cada mensaje: recibe estado de robot2, calcula roles, responde.
    5. Actualiza RoleState del pipeline local.

Modo cliente (robot2):
    1. Espera a que wlan0 tenga una IP en la subred 192.168.10.x.
    2. Conecta a ws://192.168.10.1:8765 (reintento cada CLIENT_RECONNECT_SECS).
    3. Envía su propio estado a 10 Hz, recibe roles asignados.
    4. Actualiza RoleState del pipeline local.

Al cerrar (stop()):
    - Señaliza el hilo asyncio.
    - robot1: ApManager.stop() → detiene hostapd + dnsmasq.

Uso desde main.py::

    runner = WsRunner(
        robot_id   = "robot1",
        peer_ip    = "192.168.10.12",
        port       = 8765,
        role_state = rol_state,
        vision_fn  = lambda: (pos, ve_pelota),
        simulate_ap = False,   # True en desarrollo local
    )
    runner.start()
    # ... loop principal ...
    runner.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time
from typing import Callable

import websockets
import websockets.exceptions

from communication.ap_manager import ApManager, AP_IP, AP_IFACE
from communication.communication_gateway import CommunicationGateway
from communication.role_state import RoleState

log = logging.getLogger("turbopi.communication.ws_runner")

CLIENT_SEND_HZ       = 10
CLIENT_RECONNECT_SECS = 2.0

# Tiempo máximo esperando a que robot2 tenga IP en la subred del AP
NET_WAIT_TIMEOUT = 30.0
NET_WAIT_POLL    = 1.0
AP_SUBNET_PREFIX = "192.168.10."


class WsRunner:
    def __init__(
        self,
        robot_id:    str,
        peer_ip:     str,
        port:        int,
        role_state:  RoleState,
        vision_fn:   Callable[[], tuple[list[float], bool]],
        simulate_ap: bool = False,
        command_callback: Optional[Callable[[dict], None]] = None,   # NUEVO
    ) -> None:
        self._robot_id   = robot_id
        self._peer_ip    = peer_ip
        self._port       = port
        self._role_state = role_state
        self._vision_fn  = vision_fn
        self._is_server  = robot_id == "robot1"
        self._command_callback = command_callback   # solo cliente
        self._gateway    = CommunicationGateway(robot_id, role_state)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None   # NUEVO

        # ApManager solo en robot1
        self._ap: ApManager | None = (
            ApManager(simulate=simulate_ap) if self._is_server else None
        )

        # Cola de comandos (solo servidor)
        if self._is_server:
            self._command_queue: asyncio.Queue = asyncio.Queue()
            self._websocket: websockets.WebSocketServerProtocol | None = None

    # ── API pública ────────────────────────────────────────────────────
    def start(self) -> None:
        if self._is_server and self._ap is not None:
            self._ap.start()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ws-runner",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "event=ws_runner_started robot_id=%s mode=%s",
            self._robot_id,
            "server/AP" if self._is_server else "client",
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        if self._is_server and self._ap is not None:
            self._ap.stop()
        log.info("event=ws_runner_stopped robot_id=%s", self._robot_id)

    def send_command(self, cmd: dict) -> None:
        """Envía un comando al cliente conectado (solo servidor)."""
        if not self._is_server:
            raise RuntimeError("Only server can send commands")
        if self._loop is None:
            log.warning("send_command: loop asyncio no disponible aún")
            return
        asyncio.run_coroutine_threadsafe(
            self._command_queue.put(cmd), self._loop
        )

    # ── Bucle asyncio interno ────────────────────────────────────────
    def _run_loop(self) -> None:
        asyncio.run(self._run_server() if self._is_server else self._run_client())

    # ── Modo Servidor ─────────────────────────────────────────────────
    async def _run_server(self) -> None:
        self._loop = asyncio.get_running_loop()
        asyncio.create_task(self._send_commands())   # tarea que envía comandos

        async def handler(websocket):
            self._websocket = websocket
            addr = websocket.remote_address
            log.info("event=remote_connected addr=%s", addr)
            try:
                async for raw_msg in websocket:
                    if self._stop_event.is_set():
                        break
                    pos, ve_pelota = self._vision_fn()
                    self._gateway.update_local_state(pos, ve_pelota)
                    await self._gateway.on_message(websocket, raw_msg)
            except websockets.exceptions.ConnectionClosed:
                log.warning("event=remote_disconnected addr=%s", addr)
            finally:
                self._websocket = None

        log.info("event=ws_server_listening ip=%s port=%d", AP_IP, self._port)
        async with websockets.serve(handler, AP_IP, self._port):
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)

    async def _send_commands(self) -> None:
        """Consume la cola y envía comandos al cliente conectado."""
        while not self._stop_event.is_set():
            cmd = await self._command_queue.get()
            # Esperar conexión activa
            while self._websocket is None and not self._stop_event.is_set():
                await asyncio.sleep(0.1)
            if self._stop_event.is_set():
                break
            try:
                await self._websocket.send(json.dumps(cmd))
                log.debug("Comando enviado: %s", cmd)
            except Exception as e:
                log.warning("Error enviando comando: %s", e)

    # ── Modo Cliente ─────────────────────────────────────────────────
    async def _run_client(self) -> None:
        await self._wait_for_network_async()
        uri = f"ws://{self._peer_ip}:{self._port}"
        interval = 1.0 / CLIENT_SEND_HZ

        while not self._stop_event.is_set():
            try:
                async with websockets.connect(uri) as ws:
                    log.info("event=ws_client_connected uri=%s", uri)
                    while not self._stop_event.is_set():
                        pos, ve_pelota = self._vision_fn()
                        await ws.send(json.dumps({"pos": pos, "ve_pelota": ve_pelota}))

                        raw_resp = await ws.recv()
                        resp = json.loads(raw_resp)

                        # ---- Manejo de comandos remotos ----
                        if "cmd" in resp:
                            if self._command_callback:
                                self._command_callback(resp["cmd"])
                            else:
                                log.warning("Comando recibido sin callback")
                            continue

                        # ---- Asignación de roles estándar ----
                        if "error" in resp:
                            log.warning("event=server_error msg=%s", resp["error"])
                        else:
                            mi_rol = resp.get(self._robot_id, "espera")
                            self._role_state.set(mi_rol)
                            log.debug(
                                "event=roles_received roles=%s mi_rol=%s",
                                resp, mi_rol,
                            )
                        await asyncio.sleep(interval)

            except Exception as exc:
                if not self._stop_event.is_set():
                    log.warning(
                        "event=ws_client_disconnected error=%s retry_in=%.1fs",
                        exc, CLIENT_RECONNECT_SECS,
                    )
                    await asyncio.sleep(CLIENT_RECONNECT_SECS)


    # ── Helpers de red ───────────────────────────────────────────────────

    async def _wait_for_network_async(self) -> None:
        """Espera (non-blocking) a que wlan0 tenga IP en 192.168.10.x."""
        deadline = time.monotonic() + NET_WAIT_TIMEOUT
        log.info(
            "event=net_wait iface=%s subnet=%s timeout=%.0fs",
            AP_IFACE, AP_SUBNET_PREFIX, NET_WAIT_TIMEOUT,
        )
        while time.monotonic() < deadline:
            if self._iface_in_subnet(AP_IFACE, AP_SUBNET_PREFIX):
                log.info("event=net_ready iface=%s", AP_IFACE)
                return
            await asyncio.sleep(NET_WAIT_POLL)

        log.warning(
            "event=net_timeout — continuando sin confirmar red. "
            "¿Está activo el AP de robot1?"
        )

    @staticmethod
    def _iface_in_subnet(iface: str, prefix: str) -> bool:
        """Devuelve True si la interfaz tiene alguna IP con el prefijo dado."""
        import subprocess
        try:
            r = subprocess.run(
                ["ip", "addr", "show", iface],
                capture_output=True, text=True,
            )
            return prefix in r.stdout
        except Exception:
            return False