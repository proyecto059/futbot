"""Módulo de comunicación WebSocket P2P + AP — FutbotMX."""

from communication.ap_manager import ApManager
from communication.communication_gateway import CommunicationGateway
from communication.communication_service import CommunicationService
from communication.role_state import RoleState, ROL_ATACANTE, ROL_DEFENSOR, ROL_ESPERA
from communication.ws_runner import WsRunner

__all__ = [
    "ApManager",
    "CommunicationGateway",
    "CommunicationService",
    "RoleState",
    "ROL_ATACANTE",
    "ROL_DEFENSOR",
    "ROL_ESPERA",
    "WsRunner",
]