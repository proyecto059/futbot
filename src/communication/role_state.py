"""Estado de rol compartido entre el hilo WebSocket y el pipeline síncrono.

Este objeto actúa como puente thread-safe entre:
  - El hilo asyncio del módulo WebSocket (escribe el rol asignado)
  - El loop síncrono de PipelineService (lee el rol en cada tick)

Uso::

    from communication.role_state import RoleState

    rol_state = RoleState(default_role="atacante")

    # En el hilo WebSocket:
    rol_state.set("defensor")

    # En el pipeline:
    if rol_state.get() == "defensor":
        ...
"""

from __future__ import annotations

import threading
import logging

log = logging.getLogger("turbopi.communication.role_state")

ROL_ATACANTE = "atacante"
ROL_DEFENSOR = "defensor"
ROL_ESPERA   = "espera"


class RoleState:
    """Contenedor thread-safe del rol actual del robot."""

    def __init__(self, default_role: str = ROL_ATACANTE) -> None:
        self._role = default_role
        self._lock = threading.Lock()
        log.info("event=role_state_init default_role=%s", default_role)

    def set(self, role: str) -> None:
        """Actualiza el rol (llamado desde el hilo WebSocket)."""
        with self._lock:
            if self._role != role:
                log.info("event=role_changed old=%s new=%s", self._role, role)
            self._role = role

    def get(self) -> str:
        """Lee el rol actual (llamado desde el pipeline)."""
        with self._lock:
            return self._role

    @property
    def es_atacante(self) -> bool:
        return self.get() == ROL_ATACANTE

    @property
    def es_defensor(self) -> bool:
        return self.get() == ROL_DEFENSOR
