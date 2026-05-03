"""Módulo de comunicación WebSocket entre robots — FutbotMX."""

from communication.communication_gateway import CommunicationGateway
from communication.communication_service import CommunicationService
from communication.role_state import RoleState, ROL_ATACANTE, ROL_DEFENSOR, ROL_ESPERA
from communication.ws_runner import WsRunner

__all__ = [
    "CommunicationGateway",
    "CommunicationService",
    "RoleState",
    "ROL_ATACANTE",
    "ROL_DEFENSOR",
    "ROL_ESPERA",
    "WsRunner",
]
