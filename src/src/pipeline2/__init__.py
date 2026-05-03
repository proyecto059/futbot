"""Paquete `pipeline2` — modo simple: ver pelota → avanzar.

Punto de entrada único:
    from pipeline2 import Pipeline2Service

    pipeline = Pipeline2Service(vision, motors)
    pipeline.run()
"""

from pipeline2.pipeline2_service import Pipeline2Service

__all__ = ["Pipeline2Service"]