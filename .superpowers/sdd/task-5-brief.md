### Tarea 5: Crear `pipeline.py`

**Archivos:**
- Crear: `futbot/pipeline.py`
- Test: `futbot/tests/test_pipeline.py`

**Interfaces:**
- Produce: `Pipeline` class con `tick(dets: Detections) -> MotorCommand`, `state` property, `set_frame_width(w)`
- Consume: `Config` de `config.py`, `Detections` y `Ball` de `vision.py`, `MotorCommand` de `motors.py`

Todos existen de tareas anteriores.

- [ ] **Paso 1: Escribir el test**

```python
# futbot/tests/test_pipeline.py
import sys
sys.path.insert(0, ".")

def test_pipeline_starts_in_search():
    from pipeline import Pipeline
    from config import Config
    cfg = Config()
    pip = Pipeline(cfg)
    assert pip.state == "SEARCH"

def test_search_to_chase_transition():
    """Al detectar pelota, debe transicionar a CHASE."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    dets = Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9))
    cmd = pip.tick(dets)
    assert pip.state == "CHASE"
    assert cmd.left_speed != 0 or cmd.right_speed != 0

def test_chase_to_recovery_transition():
    """Al perder la pelota por suficiente tiempo, debe ir a RECOVERY."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    import time
    cfg = Config()
    pip = Pipeline(cfg)
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    assert pip.state == "CHASE"
    time.sleep(0.1)  # dar tiempo para que la pelota se "pierda"
    for _ in range(50):
        cmd = pip.tick(Detections())
    assert pip.state in ("RECOVERY", "SEARCH")

def test_ball_centered_goes_straight():
    """Pelota en el centro debe producir avance recto."""
    from pipeline import Pipeline
    from config import Config
    from vision import Detections, Ball
    cfg = Config()
    pip = Pipeline(cfg)
    pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    cmd = pip.tick(Detections(ball=Ball(x=0.5, y=0.5, radius=0.1, confidence=0.9)))
    assert cmd.left_speed > 0
    assert cmd.right_speed > 0
```

- [ ] **Paso 2: Ejecutar test para verificar que falla**

```bash
cd futbot; python -m pytest tests/test_pipeline.py -v
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Paso 3: Escribir `pipeline.py`**

```python
"""Pipeline FSM — maquina de estados del robot.

Estados:
  SEARCH    -> barrido rotacional buscando la pelota.
  CHASE     -> servo visual: avance con giro proporcional al error.
  RECOVERY  -> busqueda en espiral para re-adquirir la pelota.

Transiciones:
  SEARCH -> CHASE    (pelota detectada)
  CHASE  -> RECOVERY (pelota perdida > timeout)
  RECOVERY -> CHASE  (pelota re-detectada)
  RECOVERY -> SEARCH (timeout sin encontrar)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from config import Config
from motors import MotorCommand
from vision import Ball, Detections

log = logging.getLogger("futbot.pipeline")

SEARCH = "SEARCH"
CHASE = "CHASE"
RECOVERY = "RECOVERY"


class Pipeline:
    """Controlador FSM que convierte detecciones en comandos de motores."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._state: str = SEARCH
        self._last_cx: Optional[float] = None
        self._miss_start: Optional[float] = None
        self._last_ball_time: float = 0.0
        self._last_search_time: float = 0.0
        self._last_chase_time: float = 0.0
        self._recovery_step: int = 0
        self._recovery_dir: str = "left"
        self._frame_width: int = config.camera_width

    @property
    def state(self) -> str:
        return self._state

    def set_frame_width(self, w: int) -> None:
        self._frame_width = w

    def tick(self, dets: Detections) -> MotorCommand:
        """Evalua el estado actual, decide transicion y retorna comando."""
        now = time.time()
        ball: Optional[Ball] = dets.ball
        ball_visible = ball is not None
        line = dets.white_line
        frame_center = self._frame_width / 2

        cx = None
        if ball_visible:
            cx = ball.x * self._frame_width
        if ball_visible:
            self._last_cx = cx
            self._miss_start = None
        elif self._miss_start is None:
            self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0

        prev = self._state

        if self._state == CHASE:
            if not ball_visible and miss_secs >= self._cfg.chase_miss_secs:
                self._state = RECOVERY

        elif self._state == RECOVERY:
            if ball_visible:
                self._state = CHASE
            elif self._recovery_step >= self._cfg.recovery_max_steps * 2:
                self._state = SEARCH

        elif self._state == SEARCH:
            if ball_visible:
                self._state = CHASE

        if self._state != prev:
            log.info("fsm: %s -> %s", prev, self._state)
            if self._state == SEARCH:
                self._last_search_time = 0.0
                self._last_cx = None
            elif self._state == CHASE:
                self._last_chase_time = 0.0
            elif self._state == RECOVERY:
                self._recovery_step = 0
                self._recovery_dir = (
                    "left" if self._last_cx is None or self._last_cx < frame_center
                    else "right"
                )

        if self._state == SEARCH:
            cmd = self._tick_search(now)
        elif self._state == CHASE:
            cmd = self._tick_chase(now, ball, ball_visible, frame_center)
        elif self._state == RECOVERY:
            cmd = self._tick_recovery(now, ball_visible, line)
        else:
            cmd = MotorCommand(0.0, 0.0, 100)

        return cmd

    def _tick_search(self, now: float) -> MotorCommand:
        if now - self._last_search_time >= self._cfg.search_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < self._frame_width / 2
            ) else "right"
            speed = self._cfg.search_turn_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_search_time = now
            return MotorCommand(v_left, v_right, self._cfg.search_turn_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_chase(
        self, now: float, ball: Optional[Ball], ball_visible: bool, frame_center: float
    ) -> MotorCommand:
        if ball_visible and ball is not None:
            self._last_ball_time = now
            cx = ball.x * self._frame_width
            radius = ball.radius * max(self._frame_width, self._cfg.camera_height)

            if radius >= self._cfg.kick_radius_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error = cx - frame_center
            if abs(error) <= self._cfg.chase_deadband_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error_norm = min(abs(error) / frame_center, 1.0)
            diff = self._cfg.chase_speed_base * error_norm * self._cfg.chase_rot_gain
            base = self._cfg.chase_speed_base

            if error > 0:
                v_left = base + diff
                v_right = max(0.0, base - diff)
            else:
                v_left = max(0.0, base - diff)
                v_right = base + diff
            return MotorCommand(v_left, v_right, 100)

        if now - self._last_ball_time < self._cfg.chase_miss_secs:
            return MotorCommand(self._cfg.chase_blind_speed,
                                self._cfg.chase_blind_speed, 100)

        if now - self._last_chase_time >= self._cfg.chase_blind_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < frame_center
            ) else "right"
            speed = self._cfg.chase_blind_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_chase_time = now
            return MotorCommand(v_left, v_right, self._cfg.chase_blind_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_recovery(
        self, now: float, ball_visible: bool, line
    ) -> MotorCommand:
        if line is not None and line.detected:
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)

        step = self._recovery_step
        self._recovery_step += 1

        if step == 0:
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
        elif step % 2 == 1:
            speed = self._cfg.recovery_turn_speed
            if self._recovery_dir == "left":
                return MotorCommand(-speed, speed, self._cfg.recovery_turn_ms)
            else:
                return MotorCommand(speed, -speed, self._cfg.recovery_turn_ms)
        else:
            return MotorCommand(self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
```

- [ ] **Paso 4: Ejecutar tests**

```bash
cd futbot; python -m pytest tests/test_pipeline.py -v
```
Esperado: 4 passed

- [ ] **Paso 5: Commit**

```bash
git add futbot/pipeline.py futbot/tests/test_pipeline.py
git commit -m "feat: crear pipeline.py con FSM SEARCH/CHASE/RECOVERY"
```
