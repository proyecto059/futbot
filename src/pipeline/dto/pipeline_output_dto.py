"""DTO de salida del pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PipelineOutputDto:
    state: str
    ball: Optional[dict] = field(default=None)
