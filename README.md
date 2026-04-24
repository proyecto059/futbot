# FutbotMX — Comunicación P2P entre Robots

## Instalación de uv (si no lo tienes)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Setup del entorno

```bash
# Crear entorno virtual e instalar dependencias
uv sync
```

## Configuración

Edita `main.py` y cambia estas dos líneas según el robot:

```python
# Robot 1 (servidor):
ROBOT_ID = "robot1"
PEER_IP  = "192.168.10.12"  # IP del Robot 2

# Robot 2 (cliente):
ROBOT_ID = "robot2"
PEER_IP  = "192.168.10.11"  # IP del Robot 1
```

Para pruebas con RPi descomenta:
```python
#PEER_IP = "192.168.22.47"
```

## Ejecución

```bash
# En Robot 1 (servidor) — encender primero
uv run main.py

# En Robot 2 (cliente)
uv run main.py
```

## Agregar dependencias futuras

```bash
# Ejemplo: agregar opencv para visión
uv add opencv-python
```

## Estructura del proyecto

```
futbot_ws/
├── main.py                              # Entry point
├── pyproject.toml                       # Dependencias (uv)
├── communication/
│   ├── communication_gateway.py         # WebSocket handler
│   ├── communication_service.py         # Parseo y serialización
│   └── dto/
│       └── robot_state_dto.py
├── strategy/
│   ├── strategy_service.py              # Lógica de roles
│   └── dto/
│       └── roles_dto.py
├── vision/
│   └── vision_service.py                # Stubs de visión (TODO: OpenCV)
└── pipes/
    └── validation_pipe.py               # Validación de mensajes
```
