"""DTO interno de transporte: un frame BGR con metadata de timestamp/tamaño."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass(frozen=True)
class FrameDto:
    """Frame BGR + timestamp de captura.

    No se serializa a JSON: es transporte entre `FrameCaptureOperator` y el
    resto del pipeline. El `image` se comparte por referencia — los operadores
    lo tratan como read-only (hacen `.copy()` si necesitan mutar).
    """

    image: np.ndarray
    ts: float
    shape: Tuple[int, int, int]  # (h, w, channels)

    @classmethod
    def of(cls, image: np.ndarray, ts: float) -> "FrameDto":
        return cls(image=image, ts=ts, shape=image.shape)

    @property
    def width(self) -> int:
        return int(self.shape[1])

    @property
    def height(self) -> int:
        return int(self.shape[0])