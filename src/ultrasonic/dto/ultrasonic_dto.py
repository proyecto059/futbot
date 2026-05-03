"""DTO de una lectura del sensor ultrasónico."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UltrasonicDto:
    """Distancia medida en milímetros con timestamp de la lectura."""

    distance_mm: Optional[int]
    ts: float

    def to_dict(self) -> dict:
        """Serializa el DTO a un ``dict`` JSON-serializable."""
        return {
            "distance_mm": self.distance_mm,
            "ts": self.ts,
        }

    @classmethod
    def empty(cls) -> UltrasonicDto:
        """Crea un DTO sin lectura válida (``distance_mm=None``).

        Se usa como fallback cuando el sensor no responde o la lectura
        falla, para que el consumidor siempre reciba un objeto del mismo
        tipo.
        """
        return cls(distance_mm=None, ts=time.time())