import math
from strategy.dto.roles_dto import RolesDto


class StrategyService:
    """
    Lógica pura de asignación de roles.
    Decide quién ataca y quién defiende basándose
    en la visión de la pelota y la posición de cada robot.
    """

    def assign_roles(
        self,
        pos_r1: list,
        ve_pelota_r1: bool,
        pos_r2: list,
        ve_pelota_r2: bool
    ) -> RolesDto:

        # Prioridad 1: el que ve la pelota ataca
        if ve_pelota_r1 and not ve_pelota_r2:
            return RolesDto(robot1="atacante", robot2="defensor")

        if ve_pelota_r2 and not ve_pelota_r1:
            return RolesDto(robot1="defensor", robot2="atacante")

        # Prioridad 2: ninguno o ambos ven la pelota
        # el más cercano (menor magnitud de posición) ataca
        d1 = math.hypot(pos_r1[0], pos_r1[1])
        d2 = math.hypot(pos_r2[0], pos_r2[1])

        if d1 <= d2:
            return RolesDto(robot1="atacante", robot2="defensor")
        else:
            return RolesDto(robot1="defensor", robot2="atacante")
