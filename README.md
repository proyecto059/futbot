# Futbot v9

Robot autónomo de fútbol para Raspberry Pi 5 con cámara CSI IMX219 y detección híbrida YOLO + HSV.

---

## Tabla de Contenidos

1. [Descripción General](#descripción-general)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Uso Rápido](#uso-rápido)
5. [Estructura del Proyecto](#estructura-del-proyecto)
6. [Arquitectura](#arquitectura)
7. [Tests](#tests)
8. [Documentación Adicional](#documentación-adicional)

---

## Descripción General

Futbot es un robot autónomo diseñado para jugar fútbol de manera independiente. Utiliza una Raspberry Pi 5 como cerebro central, una cámara CSI IMX219 para percepción visual, y un driver de motores controlado vía UART para movimiento.

**Capacidades principales:**
- Detección híbrida de pelota mediante YOLO (red neuronal) y HSV (visión por color)
- Soporte multi-backend YOLO: ONNX Runtime, NCNN (optimizado ARM) y TensorRT
- Máquina de estados finita (FSM) con tres modos: búsqueda, persecución y recuperación
- Control de motores diferencial con 4 ruedas y servos de cámara (pan/tilt)
- Modo de desarrollo local sin hardware (stubs)

---

## Requisitos

### Hardware

| Componente | Especificación |
|-----------|---------------|
| Computadora | Raspberry Pi 5 |
| Cámara | CSI IMX219 (vía ribbon cable) |
| Driver de motores | Placa conectada por UART (`/dev/ttyAMA0`, 1 MBaud) |
| Servos | 2 servos (pan/tilt) para orientar la cámara |
| Motores | 4 motores con tracción diferencial |

### Software

| Dependencia | Versión | Propósito |
|------------|---------|-----------|
| Python | ≥3.11, <3.15 | Lenguaje base |
| OpenCV | ≥4.13 | Captura y procesamiento de imágenes |
| NumPy | ≥2, <3 | Operaciones numéricas |
| PySerial | ≥3.5 | Comunicación UART con motores |
| ONNX Runtime | ≥1.24 (opcional) | Inferencia YOLO vía ONNX |
| NCNN | (opcional) | Inferencia YOLO optimizada para ARM |
| Pytest | ≥9.0 (dev) | Framework de pruebas |

---

## Instalación

```bash
# 1. Instalar uv (gestor de paquetes rápido)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clonar el repositorio
git clone <repo-url>
cd futbot/futbot

# 3. Instalar dependencias base
uv sync

# 4. Instalar backend YOLO (al menos uno)
uv sync --group onnx     # ONNX Runtime (recomendado)
# o
uv sync --group ncnn     # NCNN (optimizado para ARM en RPi)

# 5. (Opcional) Herramientas de entrenamiento de modelos
uv sync --group model-tools
```

---

## Uso Rápido

### Desarrollo local (PC sin hardware)

```bash
cd futbot
FUTBOT_MODE=stub uv run python main.py
```

En modo stub, la cámara genera frames sintéticos (campo verde con pelota naranja) y los comandos de motores se registran en lugar de enviarse por UART. Ideal para probar la lógica del pipeline sin el robot físico.

### Robot real (Raspberry Pi 5)

```bash
cd futbot
uv run python main.py
```

El robot iniciará en modo autónomo: buscará la pelota, la perseguirá y se recuperará si la pierde. Presiona `Ctrl+C` para un apagado limpio.

---

## Estructura del Proyecto

```
futbot/
├── main.py           # Punto de entrada: orquesta el bucle principal
├── config.py         # Constantes globales (velocidades, puertos, umbrales HSV, CRC8)
├── camera.py         # Captura de frames (libcamera/GStreamer/picamera2/V4L2)
├── vision.py         # Detección híbrida YOLO + HSV + fusión
├── pipeline.py       # FSM: BUSCAR → PERSEGUIR → RECUPERAR
├── motors.py         # Control UART de motores (protocolo binario + CRC8 + servos)
├── stubs/            # Mocks de hardware para desarrollo local sin RPi
│   ├── camera_stub.py
│   └── motors_stub.py
├── models/           # Modelos de red neuronal (ONNX, NCNN)
│   ├── onnx/
│   ├── tensorrt/
│   └── yoloe26n_v2/
├── scripts/          # Herramientas de diagnóstico y calibración (12 scripts)
├── tests/            # Suite de tests con pytest (6 archivos, 16 tests)
├── pyproject.toml    # Dependencias y configuración del proyecto
└── README.md
```

---

## Arquitectura

### Flujo de Datos

```
┌─────────┐   np.ndarray   ┌─────────┐   Detections   ┌──────────┐   MotorCommand   ┌────────┐
│ camera  │ ──────────────►│ vision  │ ──────────────►│ pipeline │ ────────────────►│ motors │
│   .py   │                │   .py   │                │   .py    │                   │  .py   │
└─────────┘                └─────────┘                └──────────┘                   └────────┘
                                                                                         │
                                                                                    UART serial
                                                                                         │
                                                                               ┌─────────▼─────────┐
                                                                               │ Driver de motores  │
                                                                               │ (/dev/ttyAMA0)     │
                                                                               └───────────────────┘
```

### Reglas de Dependencia

- Todos los módulos dependen de `config.py`
- `vision.py` define los dataclasses `Detections`, `Ball`, `Goal`, `WhiteLine`
- `motors.py` define el dataclass `MotorCommand`
- `pipeline.py` importa de `vision.py` y `motors.py`
- `main.py` instancia y conecta todos los módulos
- **Sin inyección de dependencias compleja ni frameworks**

### Dataclasses Compartidos

```python
@dataclass
class Ball:          # x, y, radius normalizados (0.0-1.0), confidence
@dataclass
class Goal:          # color ("blue"|"yellow"), x, y
@dataclass
class WhiteLine:     # detected (bool), position ("left"|"right"|"center")
@dataclass
class Detections:    # ball, goal, white_line, timestamp
@dataclass
class MotorCommand:  # left_speed, right_speed, dur_ms, pan_angle, tilt_angle
```

### Máquina de Estados (FSM)

```
            ┌──────────────┐
            │              │
            ▼              │
        ┌────────┐  ball   ┌────────┐
        │ SEARCH │ ───────►│ CHASE  │
        └────────┘         └────────┘
            ▲                  │
            │    timeout       │ ball lost
            └──────────────────┘
            ▲                  │
            │    timeout       ▼
            │            ┌──────────┐
            └────────────│ RECOVERY │
                         └──────────┘
```

- **SEARCH:** Barrido rotacional progresivo buscando la pelota
- **CHASE:** Servo visual con giro proporcional al error horizontal. Patada directa si la pelota está cerca
- **RECOVERY:** Secuencia retroceso-giro-avance para reencontrar la pelota. Detecta líneas blancas para evitar salir del campo

---

## Tests

```bash
# Ejecutar todos los tests (requiere FUTBOT_MODE=stub)
cd futbot
FUTBOT_MODE=stub uv run pytest tests/ -v

# Test individual
FUTBOT_MODE=stub uv run pytest tests/test_pipeline.py -v
```

**Cobertura de tests:**
| Archivo de test | Qué verifica |
|----------------|-------------|
| `test_config.py` | Carga de constantes, función CRC8 |
| `test_camera.py` | Instanciación de cámara sin hardware |
| `test_vision.py` | Dataclasses, detección HSV de pelota |
| `test_motors.py` | MotorCommand, mapeo diferencial, PWM, CRC8 |
| `test_pipeline.py` | Transiciones FSM, servo visual, recuperación |
| `test_integration.py` | Bucle completo con stubs |

---

## Documentación Adicional

- **[../docs/GUIDE_USERS.md](GUIDE_USERS.md)** — Guía práctica para operar el robot físicamente
- **[../docs/GUIDE_TECHNICAL.md](GUIDE_TECHNICAL.md)** — Documentación técnica para desarrolladores
- **[../Changelog.md](../Changelog.md)** — Historial completo de versiones (v2 → v9)
