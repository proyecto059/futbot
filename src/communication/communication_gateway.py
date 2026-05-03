"""Gateway WebSocket — orquesta el flujo de comunicación entre robots.

Adaptado para integrarse con HybridVisionService del proyecto futbot-v2.
En lugar de usar stubs de visión, recibe el estado local del robot a través
de `update_local_state()`, que es llamado por el loop principal con datos
reales de `HybridVisionService`.

Flujo:
    Robot remoto envía estado JSON → parse + validación → asignar roles
    → responder con roles → actualizar RoleState compartido.
"""

from __future__ import annotations

import logging

from communication.communication_service import CommunicationService
from communication.role_state import RoleState
from strategy.strategy_service import StrategyService

log = logging.getLogger("turbopi.communication.gateway")


class CommunicationGateway:
    """
    Gateway WebSocket — equivalente al @WebSocketGateway de NestJS.
    Orquesta el flujo: recibe mensaje → valida → calcula roles → responde.

    Args:
        robot_id:   Identificador del robot local ("robot1" o "robot2").
        role_state: Estado compartido que escribe tras cada asignación de roles.
    """

    def __init__(self, robot_id: str, role_state: RoleState) -> None:
        self._robot_id     = robot_id
        self._role_state   = role_state
        self._comm_service = CommunicationService()
        self._strategy     = StrategyService()

        self._estado_local  = {"pos": [0.0, 0.0], "ve_pelota": False}
        self._estado_remoto = {"pos": [0.0, 0.0], "ve_pelota": False}

        log.info("event=gateway_init robot_id=%s", robot_id)

    # ── API pública para el loop de visión ───────────────────────────────

    def update_local_state(self, pos: list[float], ve_pelota: bool) -> None:
        """Actualiza el estado local con datos reales de HybridVisionService.

        Llamado desde el hilo principal antes de procesar cada mensaje.

        Args:
            pos:        Posición estimada del robot [x, y] en píxeles o mm.
            ve_pelota:  True si la cámara detecta la pelota en este frame.
        """
        self._estado_local["pos"]       = pos
        self._estado_local["ve_pelota"] = ve_pelota

    # ── Handler de mensaje entrante ──────────────────────────────────────

    async def on_message(self, websocket, raw_msg: str):
        """Maneja un mensaje entrante del robot remoto.

        Equivalente a @SubscribeMessage() en NestJS.

        Returns:
            RolesDto si todo fue bien, None si hubo error de validación.
        """
        try:
            estado = self._comm_service.parse_message(raw_msg)

            self._estado_remoto["pos"]       = estado.pos
            self._estado_remoto["ve_pelota"] = estado.ve_pelota

            roles = self._strategy.assign_roles(
                pos_r1=self._estado_local["pos"],
                ve_pelota_r1=self._estado_local["ve_pelota"],
                pos_r2=self._estado_remoto["pos"],
                ve_pelota_r2=self._estado_remoto["ve_pelota"],
            )

            # ── Actualizar RoleState compartido ─────────────────────────
            mi_rol = roles.robot1 if self._robot_id == "robot1" else roles.robot2
            self._role_state.set(mi_rol)
            log.debug(
                "event=roles_assigned robot1=%s robot2=%s mi_rol=%s",
                roles.robot1, roles.robot2, mi_rol,
            )

            await websocket.send(self._comm_service.serialize(roles.to_dict()))
            return roles

        except ValueError as exc:
            log.warning("event=message_validation_error error=%s", exc)
            await websocket.send(self._comm_service.serialize({"error": str(exc)}))
            return None
