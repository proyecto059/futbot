# FutbotMX v2 — Robot Autónomo de Fútbol con Comunicación P2P

Robot autónomo para Copa FutBotMX 2026. Dos robots se comunican por
WebSocket para coordinar roles (atacante / defensor) en tiempo real.

---

## Estructura del proyecto

```
futbot-v2/
├── src/                         ← Código principal (corre en la RPi)
│   ├── main.py                  ← Entry point integrado ★
│   ├── communication/           ← Módulo WebSocket P2P ★ NUEVO
│   │   ├── communication_gateway.py
│   │   ├── communication_service.py
│   │   ├── role_state.py        ← Puente thread-safe WS ↔ pipeline
│   │   ├── ws_runner.py         ← WS asyncio en hilo daemon
│   │   └── dto/robot_state_dto.py
│   ├── strategy/                ← Lógica de roles ★ NUEVO
│   │   ├── strategy_service.py
│   │   └── dto/roles_dto.py
│   ├── pipes/                   ← Validación de mensajes ★ NUEVO
│   │   └── validation_pipe.py
│   ├── pipeline/                ← FSM principal ★ MODIFICADO
│   │   ├── pipeline_service.py  ← Ahora es role-aware
│   │   ├── operators/           ← avoid / chase / search
│   │   └── utils/pipeline_constants.py ← Reconstruido
│   ├── vision/                  ← HybridVisionService (YOLO + HSV)
│   ├── motors/                  ← MotorService (UART → Arduino)
│   └── ultrasonic/              ← UltrasonicService (I2C)
│
├── test-robot/                  ← Sub-proyecto legacy (hardware directo)
│   ├── play_futbot.py           ← Modo fútbol completo (standalone)
│   ├── hardware.py              ← Capa de hardware directa
│   ├── diag_*.py                ← Scripts de diagnóstico
│   └── tests/                  ← Tests del sub-proyecto
│
├── tests/                       ← Tests del proyecto principal ★ NUEVO
│   ├── test_communication.py    ← RoleState, Strategy, WS
│   └── test_pipeline_roles.py   ← FSM por rol
│
├── stubs/                       ← Stubs de hardware para local ★ NUEVO
│   └── hardware_stubs.py        ← serial, smbus2, cv2 mockeados
│
├── docs/                        ← Planes de diseño
├── scripts/                     ← Calibración de motores
├── Makefile                     ← Comandos de desarrollo y deploy ★ NUEVO
├── config.env                   ← Plantilla de variables de entorno ★ NUEVO
├── conftest.py                  ← Setup de pytest ★ NUEVO
└── pyproject.toml               ← Dependencias (con websockets) ★ ACTUALIZADO
```

> ★ = archivo nuevo o modificado en esta integración

---

## Setup en tu máquina local (macOS / Linux / Windows WSL)

### 1. Instalar uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Reinicia la terminal o ejecuta: source ~/.bashrc
```

### 2. Instalar dependencias

```bash
cd futbot-v2/
uv sync
```

### 3. Copiar variables de entorno

```bash
cp config.env .env
# Edita .env si quieres cambiar IPs, puertos, etc.
```

---

## Correr el proyecto

### Modo solo — sin hardware, sin WebSocket (ideal para desarrollo local)

```bash
make run-solo
# equivalente a:
WS_ENABLED=0 ULTRASONIC=0 uv run src/main.py
```

### Simulación de 2 robots en una misma máquina

Abre dos terminales:

```bash
# Terminal 1 — Robot 1 (servidor)
ROBOT_ID=robot1 PEER_IP=127.0.0.1 WS_ENABLED=1 ULTRASONIC=0 uv run src/main.py

# Terminal 2 — Robot 2 (cliente)
ROBOT_ID=robot2 PEER_IP=127.0.0.1 WS_ENABLED=1 ULTRASONIC=0 uv run src/main.py
```

### En producción (RPi)

```bash
# Robot 1
ROBOT_ID=robot1 PEER_IP=192.168.22.47 uv run src/main.py

# Robot 2
ROBOT_ID=robot2 PEER_IP=192.168.22.17 uv run src/main.py
```

---

## Tests

```bash
make test
# o directamente:
uv run pytest tests/ -v
```

Los tests no requieren hardware. Los stubs en `stubs/hardware_stubs.py`
remplazan `serial` y `smbus2` automáticamente vía `conftest.py`.

---

## Deploy a la Raspberry Pi

Edita las IPs en el `Makefile`:

```makefile
ROBOT1_IP  ?= 192.168.22.17
ROBOT2_IP  ?= 192.168.22.47
ROBOT_USER ?= pi
```

Luego:

```bash
make deploy-r1     # rsync → robot 1
make deploy-r2     # rsync → robot 2
make deploy-all    # ambos de una vez
```

Tras el deploy, en cada RPi:

```bash
cd ~/futbot-v2 && uv sync
ROBOT_ID=robot1 PEER_IP=192.168.22.47 uv run src/main.py
```

---

## Cómo funciona la comunicación P2P

```
Robot 1 (servidor)                       Robot 2 (cliente)
┌──────────────────────┐                ┌──────────────────────┐
│  HybridVisionService │                │  HybridVisionService │
│   ball? pos?         │                │   ball? pos?         │
└──────────┬───────────┘                └──────────┬───────────┘
           │ vision_fn()                           │ vision_fn()
┌──────────▼───────────┐  WebSocket :8765  ┌──────▼───────────────┐
│      WsRunner        │◄─────────────────►│      WsRunner        │
│   (hilo daemon)      │  {pos, ve_pelota} │   (hilo daemon)      │
│  CommunicationGateway│──── roles JSON ──►│                      │
│  StrategyService     │                   │                      │
└──────────┬───────────┘                   └──────┬───────────────┘
           │ RoleState.set("atacante")             │ RoleState.set("defensor")
┌──────────▼───────────┐                   ┌──────▼───────────────┐
│   PipelineService    │                   │   PipelineService    │
│   rol = atacante     │                   │   rol = defensor     │
│   SEARCH→CHASE→KICK  │                   │   giro defensivo     │
└──────────────────────┘                   └──────────────────────┘
```

### Roles del pipeline

| Rol        | Comportamiento                                           |
|------------|----------------------------------------------------------|
| `atacante` | FSM normal: SEARCH → CHASE → evadir obstáculos           |
| `defensor` | Giro defensivo lento, evasión sólo si ultrasonido activa |
| `espera`   | Motor detenido (esperando asignación de WS)              |

---

## Variables de entorno

| Variable     | Default         | Descripción                              |
|--------------|-----------------|------------------------------------------|
| `ROBOT_ID`   | `robot1`        | `robot1` (servidor) / `robot2` (cliente) |
| `PEER_IP`    | `192.168.22.47` | IP del robot opuesto                     |
| `WS_PORT`    | `8765`          | Puerto WebSocket                         |
| `ULTRASONIC` | `1`             | `0` para deshabilitar sensor             |
| `WS_ENABLED` | `1`             | `0` para modo solo (siempre atacante)    |

---

## Dependencias

| Paquete                   | Para qué                           |
|---------------------------|------------------------------------|
| `opencv-python-headless`  | Captura y procesamiento de frames  |
| `numpy`                   | Operaciones de imagen              |
| `onnxruntime`             | Inferencia YOLO (`.onnx`)          |
| `pyserial`                | UART → microcontrolador            |
| `smbus2`                  | I2C → ultrasonido y LEDs           |
| `websockets`              | Comunicación P2P entre robots ★    |

---

## Archivos de hardware no incluidos

Los siguientes archivos **no se incluyen en el repositorio** (deben
copiarse manualmente desde el robot o pedirse al equipo):

- `src/vision/models/futbot.onnx` — modelo YOLO entrenado
- Cualquier archivo `.onnx` o `.pt`

Para correr sin el modelo, el `HybridVisionService` cae en modo HSV puro.
