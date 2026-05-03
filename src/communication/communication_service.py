"""Gestiona parseo, validación y serialización de mensajes WebSocket."""

from __future__ import annotations

import json

from communication.dto.robot_state_dto import RobotStateDto
from pipes.validation_pipe import ValidationPipe


class CommunicationService:
    """Parseo, validación y serialización de mensajes entre robots."""

    REQUIRED_FIELDS = ["pos", "ve_pelota"]

    def parse_message(self, raw: str) -> RobotStateDto:
        """Parsea y valida el mensaje entrante — aplica el ValidationPipe."""
        data = json.loads(raw)
        validated = ValidationPipe.transform(data, self.REQUIRED_FIELDS)
        return RobotStateDto.from_dict(validated)

    def serialize(self, data: dict) -> str:
        """Serializa un dict a JSON para enviar por WebSocket."""
        return json.dumps(data)
