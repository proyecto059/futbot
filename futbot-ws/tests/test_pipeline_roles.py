"""tests/test_pipeline_roles.py — FSM con conciencia de rol.

Verifica que PipelineService responde correctamente a atacante / defensor /
espera usando mocks de hardware, sin RPi.

Cambios v2 reflejados:
  - PipelineOutputDto es frozen=True con campos v_left, v_right, dur_ms, ts.
  - AVOID eliminado — el defensor solo hace SEARCH lento.
  - .run() ya no traga excepciones; el stop() es separado de close().
"""

import types
import pytest

from communication.role_state import RoleState
from pipeline.pipeline_service import PipelineService


# ── Mocks ──────────────────────────────────────────────────────────────────────

class _Ultrasonic:
    def __init__(self, dist_mm=None):
        self._dist = dist_mm

    def tick(self):
        return types.SimpleNamespace(distance_mm=self._dist)

    def close(self): pass


class _Motors:
    def __init__(self):
        self.calls = []

    def stop(self, *a, **kw):    self.calls.append("stop")
    def forward(self, *a, **kw): self.calls.append("forward")
    def reverse(self, *a, **kw): self.calls.append("reverse")
    def turn_left(self, *a, **kw):  self.calls.append("turn_left")
    def turn_right(self, *a, **kw): self.calls.append("turn_right")
    def drive(self, *a, **kw):   self.calls.append("drive")
    def close(self): pass


class _Vision:
    def __init__(self, ball=None):
        self._ball = ball
        self.frame_width = 320

    def tick(self, command=None):
        return {"ball": self._ball}

    def close(self): pass


def _make(role, ball=None, dist_mm=None):
    rs       = RoleState(default_role=role)
    vision   = _Vision(ball=ball)
    ultra    = _Ultrasonic(dist_mm=dist_mm)
    motors   = _Motors()
    pipeline = PipelineService(vision, ultra, motors, role_state=rs)
    return pipeline, motors, rs


# ── Tests: estado ESPERA ───────────────────────────────────────────────────────

class TestRolEspera:
    def test_para_motores(self):
        p, motors, _ = _make("espera")
        out = p.tick()
        assert out.state == "ESPERA"
        assert "stop" in motors.calls

    def test_dto_tiene_campos_v2(self):
        p, _, _ = _make("espera")
        out = p.tick()
        assert hasattr(out, "v_left")
        assert hasattr(out, "v_right")
        assert hasattr(out, "dur_ms")
        assert hasattr(out, "ts")


# ── Tests: rol ATACANTE ────────────────────────────────────────────────────────

class TestRolAtacante:
    def test_search_sin_pelota(self):
        p, _, _ = _make("atacante", ball=None)
        out = p.tick()
        assert out.state == "SEARCH"

    def test_chase_con_pelota(self):
        ball = {"cx": 160, "cy": 120, "r": 30}
        p, _, _ = _make("atacante", ball=ball)
        out = p.tick()
        assert out.state == "CHASE"

    def test_chase_velocidades_no_cero(self):
        """En CHASE con pelota visible, v_left o v_right deben ser != 0."""
        ball = {"cx": 160, "cy": 120, "r": 30}
        p, _, _ = _make("atacante", ball=ball)
        out = p.tick()
        assert out.v_left != 0 or out.v_right != 0

    def test_chase_giro_derecha_pelota_a_derecha(self):
        """Pelota a la derecha del centro → rueda izquierda más rápida."""
        ball = {"cx": 260, "cy": 120, "r": 30}   # cx > centro (160)
        p, _, _ = _make("atacante", ball=ball)
        out = p.tick()
        # Con el nuevo algoritmo proporcional: v_left >= v_right
        assert out.v_left >= out.v_right

    def test_chase_giro_izquierda_pelota_a_izquierda(self):
        """Pelota a la izquierda del centro → rueda derecha más rápida."""
        ball = {"cx": 60, "cy": 120, "r": 30}    # cx < centro
        p, _, _ = _make("atacante", ball=ball)
        out = p.tick()
        assert out.v_right >= out.v_left

    def test_sin_role_state_comporta_como_atacante(self):
        """Sin role_state, actúa siempre como atacante."""
        p = PipelineService(_Vision(), _Ultrasonic(), _Motors(), role_state=None)
        out = p.tick()
        assert out.state in ("SEARCH", "CHASE")

    def test_no_hay_estado_avoid(self):
        """v2 eliminó AVOID — nunca debe aparecer ese estado."""
        p, _, _ = _make("atacante", dist_mm=50)  # ultrasonido muy cerca
        out = p.tick()
        assert "AVOID" not in out.state


# ── Tests: rol DEFENSOR ────────────────────────────────────────────────────────

class TestRolDefensor:
    def test_state_contiene_defensor(self):
        p, _, _ = _make("defensor")
        out = p.tick()
        assert "DEFENSOR" in out.state

    def test_no_persigue_pelota(self):
        """Con pelota visible, el defensor NO debe entrar en CHASE."""
        ball = {"cx": 160, "cy": 120, "r": 30}
        p, _, _ = _make("defensor", ball=ball)
        out = p.tick()
        assert "CHASE" not in out.state

    def test_no_hay_avoid_en_defensor(self):
        """v2 eliminó AVOID también del defensor."""
        p, _, _ = _make("defensor", dist_mm=50)
        out = p.tick()
        assert "AVOID" not in out.state


# ── Tests: cambio de rol en caliente ──────────────────────────────────────────

class TestCambioDeRol:
    def test_atacante_a_defensor(self):
        ball = {"cx": 160, "cy": 120, "r": 30}
        p, _, rs = _make("atacante", ball=ball)

        out1 = p.tick()
        assert "DEFENSOR" not in out1.state

        rs.set("defensor")
        out2 = p.tick()
        assert "DEFENSOR" in out2.state

    def test_defensor_a_espera(self):
        p, motors, rs = _make("defensor")
        p.tick()

        rs.set("espera")
        out = p.tick()
        assert out.state == "ESPERA"
        assert "stop" in motors.calls