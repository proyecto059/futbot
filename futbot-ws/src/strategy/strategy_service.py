"""Lógica pura de asignación de roles entre dos robots.

Decide quién ataca y quién defiende basándose en la visión de la pelota
y la posición relativa de cada robot en el campo.

Criterios (en orden de prioridad):
    1. El robot que ve la pelota → atacante.
    2. Si ambos o ninguno la ven → el más cercano al centro → atacante.
"""

from __future__ import annotations

import math
import logging

from strategy.dto.roles_dto import RolesDto

log = logging.getLogger("turbopi.strategy")


class StrategyService:

    def assign_roles(
        self,
        pos_r1: list[float],
        ve_pelota_r1: bool,
        pos_r2: list[float],
        ve_pelota_r2: bool,
    ) -> RolesDto:
        # Prioridad 1: el que ve la pelota ataca
        if ve_pelota_r1 and not ve_pelota_r2:
            return RolesDto(robot1="atacante", robot2="defensor")

        if ve_pelota_r2 and not ve_pelota_r1:
            return RolesDto(robot1="defensor", robot2="atacante")

        # Prioridad 2: ninguno o ambos ven la pelota →
        # el más cercano al origen del campo (coordenadas más bajas) ataca
        d1 = math.hypot(pos_r1[0], pos_r1[1])
        d2 = math.hypot(pos_r2[0], pos_r2[1])

        if d1 <= d2:
            roles = RolesDto(robot1="atacante", robot2="defensor")
        else:
            roles = RolesDto(robot1="defensor", robot2="atacante")

        log.debug(
            "event=roles_computed d1=%.1f d2=%.1f r1=%s r2=%s",
            d1, d2, roles.robot1, roles.robot2,
        )
        return roles
