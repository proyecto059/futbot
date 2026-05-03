"""Operador de búsqueda — cuando pierde la pelota busca girando."""

from pipeline3.utils import BACKUP_SPEED, BACKUP_DUR_MS, SEARCH_SPEED, SEARCH_TURN_DUR_MS


class SearchOperator:
    def __init__(self):
        self._turn_count = 0
        self._backup_done = False
        self._search_start_time = 0

    def compute(self, lost_ball, search_phase):
        if not lost_ball:
            self._turn_count = 0
            self._backup_done = False
            return (0.0, 0.0, 0)

        if search_phase == "backup":
            if not self._backup_done:
                self._backup_done = True
                return (BACKUP_SPEED, BACKUP_SPEED, BACKUP_DUR_MS)
            return (0.0, 0.0, 0)

        if search_phase == "search":
            self._turn_count += 1
            if self._turn_count % 2 == 0:
                return (SEARCH_SPEED, -SEARCH_SPEED, SEARCH_TURN_DUR_MS)
            else:
                return (-SEARCH_SPEED, SEARCH_SPEED, SEARCH_TURN_DUR_MS)

        return (0.0, 0.0, 0)

    def reset(self):
        self._turn_count = 0
        self._backup_done = False