"""Paquete `vision` — pipeline de visión híbrida para el robot futbolero.

Punto de entrada único:
    from vision import HybridVisionService

    vision = HybridVisionService()
    snapshot = vision.tick()        # dict con ball / robots / goals / line / ts
    vision.close()
"""

from vision.hybrid_vision_service import HybridVisionService

__all__ = ["HybridVisionService"]