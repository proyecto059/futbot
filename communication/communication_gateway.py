from communication.communication_service import CommunicationService
from strategy.strategy_service import StrategyService


class CommunicationGateway:
    """
    Gateway WebSocket — equivalente al @WebSocketGateway de NestJS.
    Orquesta el flujo: recibe mensaje → valida → calcula roles → responde.
    """

    def __init__(self):
        self.comm_service = CommunicationService()
        self.strategy_service = StrategyService()

        self.estado_local  = {"pos": [0.0, 0.0], "ve_pelota": False}
        self.estado_remoto = {"pos": [0.0, 0.0], "ve_pelota": False}

    def update_local_state(self, pos: list, ve_pelota: bool):
        """Actualiza el estado del robot local antes de procesar mensajes"""
        self.estado_local["pos"] = pos
        self.estado_local["ve_pelota"] = ve_pelota

    async def on_message(self, websocket, raw_msg: str):
        """
        Maneja un mensaje entrante del robot remoto.
        Equivalente a @SubscribeMessage() en NestJS.
        """
        try:
            # Pipeline: parseo + validación
            estado = self.comm_service.parse_message(raw_msg)

            # Actualizar estado remoto
            self.estado_remoto["pos"]       = estado.pos
            self.estado_remoto["ve_pelota"] = estado.ve_pelota

            # Calcular roles
            roles = self.strategy_service.assign_roles(
                pos_r1=self.estado_local["pos"],
                ve_pelota_r1=self.estado_local["ve_pelota"],
                pos_r2=self.estado_remoto["pos"],
                ve_pelota_r2=self.estado_remoto["ve_pelota"]
            )

            # Responder con los roles calculados
            await websocket.send(
                self.comm_service.serialize(roles.to_dict())
            )

            return roles

        except ValueError as e:
            error_msg = self.comm_service.serialize({"error": str(e)})
            await websocket.send(error_msg)
            return None
