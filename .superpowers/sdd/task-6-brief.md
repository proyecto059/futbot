### Tarea 6: Crear `main.py` + stubs

**Archivos a crear:**
- `futbot/main.py`
- `futbot/stubs/__init__.py`
- `futbot/stubs/camera_stub.py`
- `futbot/stubs/motors_stub.py`
- `futbot/tests/test_integration.py`

**Interfaces:**
- Produce: `main()` function (entry point)
- Consume: `Config`, `Camera`, `Vision`, `Motors`, `Pipeline` (todos existen)
- Stubs deben tener misma interfaz que sus contrapartes reales

- [ ] **Paso 1: Escribir el test de integración**

```python
# futbot/tests/test_integration.py
import sys
sys.path.insert(0, ".")

def test_full_loop_with_stubs():
    """Ejecuta el bucle completo con stubs y verifica que no crashea."""
    import os
    os.environ["FUTBOT_MODE"] = "stub"

    from config import Config
    from stubs.camera_stub import CameraStub
    from stubs.motors_stub import MotorsStub
    from vision import Vision
    from pipeline import Pipeline

    cfg = Config()
    cam = CameraStub(cfg)
    vis = Vision(cfg)
    mot = MotorsStub(cfg)
    pip = Pipeline(cfg)

    for _ in range(10):
        frame = cam.grab()
        if frame is None:
            continue
        dets = vis.detect(frame)
        cmd = pip.tick(dets)
        mot.send(cmd)

    history = mot.get_history()
    assert len(history) > 0, "Debe haber al menos un comando enviado"
    for cmd in history:
        assert -300 <= cmd.left_speed <= 300
        assert -300 <= cmd.right_speed <= 300
```

- [ ] **Paso 2: Ejecutar test — debe fallar (no hay stubs)**

```bash
cd futbot; python -m pytest tests/test_integration.py -v
```
Esperado: FAIL — `ModuleNotFoundError: No module named 'stubs'`

- [ ] **Paso 3: Crear los stubs**

```python
# futbot/stubs/__init__.py
"""Stubs de hardware para desarrollo local sin Raspberry Pi.

Uso:
    export FUTBOT_MODE=stub
    python main.py
"""

from stubs.camera_stub import CameraStub
from stubs.motors_stub import MotorsStub
```

```python
# futbot/stubs/camera_stub.py
"""Camara stub: reproduce frames pregrabados o genera frames sinteticos."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import Config


class CameraStub:
    """Camara fake para desarrollo local."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._width = config.camera_width
        self._height = config.camera_height
        self._frame_idx = 0
        self._frames = self._load_test_frames()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Devuelve un frame sintetico o pregrabado."""
        if self._frames:
            frame = self._frames[self._frame_idx % len(self._frames)]
            self._frame_idx += 1
            return frame.copy()

        # Frame sintetico: fondo verde con circulo naranja
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:] = (50, 120, 50)  # BGR verde campo

        # Pelota naranja en posicion aleatoria
        cx = random.randint(self._width // 4, 3 * self._width // 4)
        cy = random.randint(self._height // 4, 3 * self._height // 4)
        cv2.circle(frame, (cx, cy), 25, (0, 140, 255), -1)

        return frame

    def release(self) -> None:
        pass

    def _load_test_frames(self) -> list[np.ndarray]:
        """Carga frames pregrabados desde stubs/test_frames/ si existen."""
        test_dir = Path(__file__).parent / "test_frames"
        if not test_dir.exists():
            return []
        frames = []
        for path in sorted(test_dir.glob("*.png")):
            frame = cv2.imread(str(path))
            if frame is not None:
                frames.append(frame)
        return frames
```

```python
# futbot/stubs/motors_stub.py
"""Motores stub: registra comandos en vez de enviarlos por UART."""

from __future__ import annotations

from motors import MotorCommand


class MotorsStub:
    """Motores fake que loguean comandos para desarrollo local."""

    def __init__(self, config) -> None:
        self._cfg = config
        self._history: list[MotorCommand] = []

    def send(self, cmd: MotorCommand) -> None:
        self._history.append(MotorCommand(
            left_speed=cmd.left_speed,
            right_speed=cmd.right_speed,
            dur_ms=cmd.dur_ms,
            pan_angle=cmd.pan_angle,
            tilt_angle=cmd.tilt_angle,
        ))

    def stop(self, dur_ms: int = 300) -> None:
        self._history.append(MotorCommand(0.0, 0.0, dur_ms))

    def close(self) -> None:
        pass

    def get_history(self) -> list[MotorCommand]:
        return self._history
```

- [ ] **Paso 4: Ejecutar test de integración — debe pasar**

```bash
cd futbot; $env:FUTBOT_MODE="stub"; python -m pytest tests/test_integration.py -v
```
Esperado: 1 passed

- [ ] **Paso 5: Escribir `main.py`**

```python
"""Punto de entrada del robot futbolero.

Inicializa los servicios (camara, vision, motores, pipeline) y ejecuta el
bucle principal FSM.

Modos via variable de entorno FUTBOT_MODE:
  real  -> hardware real en Raspberry Pi 5
  stub  -> desarrollo local con stubs (sin hardware)

Uso:
  FUTBOT_MODE=stub python main.py   # desarrollo local
  python main.py                    # hardware real (default)
"""

from __future__ import annotations

import logging
import os
import signal
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("futbot")

MODE = os.environ.get("FUTBOT_MODE", "real")
running = True


def _shutdown(signum, frame):
    global running
    log.info("Senal %s recibida, apagando...", signum)
    running = False


def main():
    from config import Config

    cfg = Config()
    cam = None
    mot = None

    log.info("futbot iniciando en modo %s", MODE)

    try:
        if MODE == "stub":
            from stubs.camera_stub import CameraStub
            from stubs.motors_stub import MotorsStub
            cam = CameraStub(cfg)
            mot = MotorsStub(cfg)
            log.info("Usando stubs de hardware")
        else:
            from camera import Camera
            from motors import Motors
            cam = Camera(cfg)
            mot = Motors(cfg)

        from vision import Vision
        from pipeline import Pipeline

        vis = Vision(cfg)
        pip = Pipeline(cfg)
        pip.set_frame_width(cam.width)

        log.info("Servicios inicializados. Ancho de frame: %d", cam.width)
        log.info("Bucle principal iniciado")

        while running:
            frame = cam.grab()
            if frame is None:
                time.sleep(0.005)
                continue

            dets = vis.detect(frame)
            cmd = pip.tick(dets)
            mot.send(cmd)

            time.sleep(0.01)

    except KeyboardInterrupt:
        log.info("Apagado por teclado")
    except Exception as exc:
        log.exception("Error en runtime: %s", exc)
    finally:
        if mot is not None:
            try:
                mot.stop(200)
                mot.close()
            except Exception:
                pass
        if cam is not None:
            try:
                cam.release()
            except Exception:
                pass
        log.info("futbot apagado")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    main()
```

- [ ] **Paso 6: Ejecutar todos los tests**

```bash
cd futbot; $env:FUTBOT_MODE="stub"; python -m pytest tests/ -v
```
Esperado: todos los tests pasan (~16 tests)

- [ ] **Paso 7: Commit**

```bash
git add futbot/main.py futbot/stubs/ futbot/tests/test_integration.py
git commit -m "feat: crear main.py con orquestador y stubs de hardware"
```
