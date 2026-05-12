"""Request a `HybridVisionService.tick(command)` (parámetros por invocación)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DetectVisionCommand:
    """Request opcional para un tick específico.

    En la práctica casi siempre se pasa None a `tick()` y el servicio infiere
    `now_ts = time.time()`. Esta clase existe para tests que necesitan inyectar
    un timestamp determinista o desactivar debug en un tick puntual.
    """

    now_ts: Optional[float] = None
    include_debug: bool = True