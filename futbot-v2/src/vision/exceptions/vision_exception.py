"""Excepción base del paquete `vision`.

Heredar de esta clase hace fácil que el consumidor pueda hacer un solo
`except VisionException` para capturar cualquier fallo del pipeline.
"""


class VisionException(Exception):
    """Raíz de todas las excepciones del pipeline de visión."""
