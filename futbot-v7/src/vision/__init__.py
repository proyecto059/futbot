"""Paquete `vision` — pipeline de visión híbrida para el robot futbolero.

Punto de entrada único:
    from vision import HybridVisionService

    vision = HybridVisionService()
    snapshot = vision.tick()        # dict con ball / robots / goals / line / ts
    vision.close()
"""

__all__ = ["HybridVisionService"]


def __getattr__(name: str):
    if name == "HybridVisionService":
        from vision.hybrid_vision_service import HybridVisionService

        return HybridVisionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
