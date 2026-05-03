"""Valida datos entrantes de mensajes WebSocket — similar al ValidationPipe de NestJS."""


class ValidationPipe:

    @staticmethod
    def transform(data: dict, required_fields: list) -> dict:
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Campo requerido faltante: '{field}'")
        return data
