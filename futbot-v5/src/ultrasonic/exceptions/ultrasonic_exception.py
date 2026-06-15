"""Excepción base del paquete `ultrasonic`.

Heredar de esta clase hace fácil que el consumidor pueda hacer un solo
``except UltrasonicException`` para capturar cualquier fallo del sensor.
"""


class UltrasonicException(Exception):
    """Raíz de las excepciones del sensor ultrasónico."""

    pass
