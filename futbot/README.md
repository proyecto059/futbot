# Futbot v9

Robot autónomo de fútbol sobre Raspberry Pi 5 con cámara CSI IMX219.

## Estructura

```
futbot/
├── main.py           # Punto de entrada
├── config.py         # Constantes globales
├── camera.py         # Captura de frames (libcamera/GStreamer/V4L2)
├── vision.py         # Detección híbrida YOLO + HSV
├── pipeline.py       # FSM: BUSCAR → PERSEGUIR → RECUPERAR
├── motors.py         # Control UART de motores y servos
├── stubs/            # Mocks para desarrollo local
├── models/           # Modelos ML (ONNX, NCNN)
├── scripts/          # Diagnóstico y calibración
└── tests/            # Tests con pytest
```

## Requisitos

- Python 3.11+
- Raspberry Pi 5 (para hardware real)
- Cámara CSI IMX219
- Driver de motores conectado por UART (/dev/ttyAMA0)

## Instalación

```bash
# Instalar uv (gestor de paquetes)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependencias
uv sync

# Opcional: instalar backend YOLO
uv sync --group onnx    # ONNX Runtime
uv sync --group ncnn    # NCNN (optimizado ARM)
```

## Uso

```bash
# Desarrollo local (sin hardware)
FUTBOT_MODE=stub uv run python main.py

# Hardware real en Raspberry Pi 5
uv run python main.py
```

## Tests

```bash
FUTBOT_MODE=stub uv run pytest tests/ -v
```

## Arquitectura

Flujo de datos: `camera.py → vision.py → pipeline.py → motors.py`

Cada módulo depende solo de `config.py` y de los dataclasses compartidos:
- `vision.py` define `Detections`, `Ball`, `Goal`, `WhiteLine`
- `motors.py` define `MotorCommand`
- `pipeline.py` importa ambos

Sin inyección de dependencias compleja: `main.py` instancia y conecta todo.

## Changelog

Ver `../Changelog.md` para el historial completo de versiones (v2 → v9).

## Diseño

Ver `../docs/superpowers/specs/2026-06-22-futbot-refactor-design.md` para el documento de diseño.
