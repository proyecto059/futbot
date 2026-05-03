"""Paquete `pipeline` — FSM que orquesta visión + ultrasonido + motores.

Punto de entrada único:
    from pipeline import PipelineService

    pipeline = PipelineService(vision, ultrasonic, motors)
    pipeline.run()
"""

from pipeline.pipeline_service import PipelineService

__all__ = ["PipelineService"]