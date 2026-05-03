"""tests/test_pipeline_roles.py — Tests de la FSM con conciencia de rol.

Verifica que el PipelineService responde correctamente a los roles
atacante / defensor / espera sin necesitar hardware real.
"""

import types
import pytest

from communication.role_state import RoleState
from pipeline.pipeline_service import PipelineService


# ── Mocks de servicios de hardware ────────────────────────────────────────────

class MockUltrasonic:
    def __init__(self, dist_mm=None):
        self._dist = dist_mm

    def tick(self):
        dto = types.SimpleNamespace(distance_mm=self._dist)
        return dto

    def close(self): pass


class MockMotors:
    def __init__(self):
        self.calls = []

    def stop(self, *a, **kw): self.calls.append("stop")
    def forward(self, *a, **kw): self.calls.append("forward")
    def reverse(self, *a, **kw): self.calls.append("reverse")
    def turn_left(self, *a, **kw): self.calls.append("turn_left")
    def turn_right(self, *a, **kw): self.calls.append("turn_right")
    def drive(self, *a, **kw): self.calls.append("drive")
    def close(self): pass


class MockVision:
    def __init__(self, ball=None):
        self._ball = ball
        self.frame_width = 320

    def tick(self, command=None):
        return {"ball": self._ball}

    def close(self): pass


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestPipelineRoles:

    def _make_pipeline(self, role, ball=None, dist_mm=None):
        role_state = RoleState(default_role=role)
        vision     = MockVision(ball=ball)
        ultrasonic = MockUltrasonic(dist_mm=dist_mm)
        motors     = MockMotors()
        pipeline   = PipelineService(vision, ultrasonic, motors, role_state=role_state)
        return pipeline, motors

    def test_espera_para_motors(self):
        pipeline, motors = self._make_pipeline("espera")
        out = pipeline.tick()
        assert out.state == "ESPERA"
        assert "stop" in motors.calls

    def test_atacante_state_es_search_sin_pelota(self):
        pipeline, _ = self._make_pipeline("atacante", ball=None)
        out = pipeline.tick()
        assert "SEARCH" in out.state or out.state == "SEARCH"

    def test_atacante_state_es_chase_con_pelota(self):
        ball = {"cx": 160, "cy": 120, "r": 30}
        pipeline, _ = self._make_pipeline("atacante", ball=ball)
        out = pipeline.tick()
        # Primer tick: detecta la pelota, pasa a CHASE
        assert out.state == "CHASE"

    def test_defensor_state_contiene_defensor(self):
        pipeline, _ = self._make_pipeline("defensor", ball=None)
        out = pipeline.tick()
        assert "DEFENSOR" in out.state

    def test_defensor_no_persigue_pelota(self):
        """Con rol defensor y pelota visible, el estado NO debe ser CHASE."""
        ball = {"cx": 160, "cy": 120, "r": 30}
        pipeline, _ = self._make_pipeline("defensor", ball=ball)
        out = pipeline.tick()
        assert "CHASE" not in out.state

    def test_rol_cambia_en_caliente(self):
        """El pipeline debe reaccionar a un cambio de rol sin reiniciar."""
        role_state = RoleState(default_role="atacante")
        vision     = MockVision(ball=None)
        ultrasonic = MockUltrasonic()
        motors     = MockMotors()
        pipeline   = PipelineService(vision, ultrasonic, motors, role_state=role_state)

        out1 = pipeline.tick()
        assert "DEFENSOR" not in out1.state

        role_state.set("defensor")
        out2 = pipeline.tick()
        assert "DEFENSOR" in out2.state

    def test_sin_role_state_comportamiento_atacante(self):
        """Sin role_state, el pipeline actúa siempre como atacante."""
        vision     = MockVision(ball=None)
        ultrasonic = MockUltrasonic()
        motors     = MockMotors()
        pipeline   = PipelineService(vision, ultrasonic, motors, role_state=None)
        out = pipeline.tick()
        assert out.state in ("SEARCH", "CHASE", "AVOID")
