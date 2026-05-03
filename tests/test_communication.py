"""tests/test_communication.py — Tests del módulo de comunicación WebSocket.

Cubre:
  - RoleState: thread-safety, set/get, propiedades
  - StrategyService: lógica de asignación de roles
  - CommunicationService: parseo y serialización de mensajes
  - ValidationPipe: validación de campos requeridos
"""

import json
import threading
import pytest

from communication.role_state import RoleState, ROL_ATACANTE, ROL_DEFENSOR
from strategy.strategy_service import StrategyService
from communication.communication_service import CommunicationService
from pipes.validation_pipe import ValidationPipe


# ── RoleState ─────────────────────────────────────────────────────────────────

class TestRoleState:

    def test_default_role(self):
        rs = RoleState(default_role="atacante")
        assert rs.get() == "atacante"

    def test_set_get(self):
        rs = RoleState()
        rs.set("defensor")
        assert rs.get() == "defensor"

    def test_es_atacante(self):
        rs = RoleState(default_role="atacante")
        assert rs.es_atacante is True
        assert rs.es_defensor is False

    def test_es_defensor(self):
        rs = RoleState(default_role="defensor")
        assert rs.es_defensor is True
        assert rs.es_atacante is False

    def test_thread_safety(self):
        """Múltiples hilos leyendo y escribiendo no deben causar race conditions."""
        rs = RoleState(default_role="atacante")
        errors = []

        def writer():
            for _ in range(1000):
                rs.set("defensor")
                rs.set("atacante")

        def reader():
            for _ in range(1000):
                val = rs.get()
                if val not in ("atacante", "defensor"):
                    errors.append(f"Valor inesperado: {val}")

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Race condition: {errors}"


# ── StrategyService ───────────────────────────────────────────────────────────

class TestStrategyService:

    def setup_method(self):
        self.svc = StrategyService()

    def test_r1_ve_pelota_es_atacante(self):
        roles = self.svc.assign_roles([0, 0], True, [0, 0], False)
        assert roles.robot1 == "atacante"
        assert roles.robot2 == "defensor"

    def test_r2_ve_pelota_es_atacante(self):
        roles = self.svc.assign_roles([0, 0], False, [0, 0], True)
        assert roles.robot1 == "defensor"
        assert roles.robot2 == "atacante"

    def test_ninguno_ve_pelota_mas_cercano_ataca(self):
        # r1 más cerca del origen → r1 ataca
        roles = self.svc.assign_roles([1, 1], False, [5, 5], False)
        assert roles.robot1 == "atacante"
        assert roles.robot2 == "defensor"

    def test_ambos_ven_pelota_mas_cercano_ataca(self):
        # r2 más cerca → r2 ataca
        roles = self.svc.assign_roles([10, 10], True, [1, 1], True)
        assert roles.robot1 == "defensor"
        assert roles.robot2 == "atacante"

    def test_to_dict(self):
        roles = self.svc.assign_roles([0, 0], True, [0, 0], False)
        d = roles.to_dict()
        assert "robot1" in d and "robot2" in d


# ── CommunicationService ──────────────────────────────────────────────────────

class TestCommunicationService:

    def setup_method(self):
        self.svc = CommunicationService()

    def test_parse_valid_message(self):
        raw = json.dumps({"pos": [1.5, 2.3], "ve_pelota": True})
        dto = self.svc.parse_message(raw)
        assert dto.pos == [1.5, 2.3]
        assert dto.ve_pelota is True

    def test_parse_missing_field_raises(self):
        raw = json.dumps({"pos": [0, 0]})  # falta ve_pelota
        with pytest.raises(ValueError):
            self.svc.parse_message(raw)

    def test_serialize(self):
        result = self.svc.serialize({"robot1": "atacante", "robot2": "defensor"})
        parsed = json.loads(result)
        assert parsed["robot1"] == "atacante"


# ── ValidationPipe ────────────────────────────────────────────────────────────

class TestValidationPipe:

    def test_valid_data_passes(self):
        data = {"pos": [0, 0], "ve_pelota": False}
        result = ValidationPipe.transform(data, ["pos", "ve_pelota"])
        assert result == data

    def test_missing_field_raises(self):
        with pytest.raises(ValueError, match="ve_pelota"):
            ValidationPipe.transform({"pos": [0, 0]}, ["pos", "ve_pelota"])
