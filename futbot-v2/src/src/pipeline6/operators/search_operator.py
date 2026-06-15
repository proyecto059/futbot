"""Decide direccion de giro para buscar la pelota.

Usa la ultima posicion conocida (last_cx) para girar hacia donde se vio la
pelota por ultima vez. Si no hay referencia, gira a la izquierda por defecto.
"""

from __future__ import annotations

from typing import Optional


class SearchOperator:
    def choose_direction(self, last_cx: Optional[float], frame_center_x: float) -> str:
        """Retorna 'left' o 'right' segun la ultima posicion conocida de la pelota."""
        if last_cx is None:
            return "left"
        if last_cx < frame_center_x:
            return "left"
        return "right"
