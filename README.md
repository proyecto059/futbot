# Futbot v9

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red)](https://www.raspberrypi.com/products/raspberry-pi-5/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-stable-success)]()

**Sistema embebido de robótica autónoma para fútbol sobre Raspberry Pi 5.**

Futbot es un robot autónomo diseñado para competir en torneos de fútbol robótico. Integra percepción visual con redes neuronales (YOLO), una máquina de estados finita para navegación reactiva, y control de motores en tiempo real vía UART. Opera completamente sin intervención humana: busca, persigue y recupera la pelota usando solo su cámara CSI IMX219.

---

## Tabla de Contenidos

- [Propósito del Proyecto](#propósito-del-proyecto)
- [Quickstart](#quickstart)
- [Requisitos](#requisitos)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Arquitectura](#arquitectura)
- [Rendimiento](#rendimiento)
- [Tests](#tests)
- [Contribuir](#contribuir)
- [Licencia](#licencia)
- [Documentación Adicional](#documentación-adicional)

---

## Propósito del Proyecto

Futbot fue desarrollado para competiciones de fútbol robótico donde robots autónomos de pequeña escala juegan partidos 1v1 o 2v2 en un campo delimitado con porterías de color y una pelota naranja estándar.

### Problema que resuelve

Los robots de fútbol tradicionales dependen de hardware especializado costoso (LiDAR, cámaras depth, FPGAs) y stacks de software complejos (ROS, middlewares). Futbot demuestra que un robot competitivo puede construirse con:

- **Hardware commodity:** Raspberry Pi 5 + cámara CSI estándar + driver de motores genérico
- **Software simple:** ~1,500 líneas de Python en 6 módulos planos, sin frameworks de inyección de dependencias ni capas de middleware
- **Pipeline de visión híbrido:** YOLO para detección de alto nivel + HSV clásico como fallback determinista

### Capacidades

| Categoría | Funcionalidad |
|-----------|-------------|
| **Percepción** | Detección de pelota por red neuronal (YOLO) y visión clásica (HSV) |
| **Percepción** | Detección de porterías por color (azul/amarillo) |
| **Percepción** | Detección de línea blanca del campo para contención espacial |
| **Navegación** | FSM de 3 estados: SEARCH → CHASE → RECOVERY |
| **Navegación** | Servo visual proporcional con zona muerta y ganancia configurable |
| **Control** | Tracción diferencial de 4 motores con cap de velocidad |
| **Control** | Servos pan/tilt para orientación de cámara |
| **ML** | Backends YOLO intercambiables: ONNX Runtime, NCNN (ARM NEON), TensorRT |
| **Cámara** | 4 backends de captura: picamera2, libcamera, GStreamer, V4L2 |
| **DevOps** | Modo stub para desarrollo y pruebas sin hardware físico |

---

## Quickstart

### 1. Clonar e instalar dependencias (~2 min)

```bash
git clone <repo-url> && cd futbot/futbot
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### 2. Instalar backend de inferencia (~1 min)

```bash
uv sync --group onnx    # ONNX Runtime (recomendado, multiplataforma)
# o
uv sync --group ncnn    # NCNN (optimizado ARM, solo RPi)
```

### 3. Ejecutar

```bash
# Desarrollo local (PC, sin robot):
FUTBOT_MODE=stub uv run python main.py

# Robot real (Raspberry Pi 5):
uv run python main.py
```

> **Resultado esperado:** En modo stub verás logs del pipeline procesando frames sintéticos y el FSM alternando entre estados. En modo real, el robot comenzará a moverse autónomamente.

---

## Requisitos

### Hardware

| Componente | Especificación | Notas |
|-----------|---------------|-------|
| Computadora | Raspberry Pi 5 (4 GB+) | Arquitectura aarch64 |
| Cámara | CSI IMX219 | Conectada vía ribbon cable al puerto CSI |
| Driver de motores | Placa UART propietaria | `/dev/ttyAMA0`, 1,000,000 baud |
| Servos | 2× servo digital (pan/tilt) | Rango 0-180°, PWM 500-2500 µs |
| Motores | 4× motor DC con encoder | Tracción diferencial |
| Batería | LiPo 3S (11.1V) | ≥2200 mAh recomendado |

### Software

| Dependencia | Versión | Propósito | Obligatoria |
|------------|---------|-----------|-------------|
| Python | ≥3.11, <3.15 | Runtime | Sí |
| OpenCV | ≥4.13 | Captura y procesamiento de imagen | Sí |
| NumPy | ≥2, <3 | Operaciones numéricas | Sí |
| PySerial | ≥3.5 | Comunicación UART | Sí |
| ONNX Runtime | ≥1.24 | Inferencia YOLO vía ONNX | No |
| NCNN | — | Inferencia YOLO vía ARM NEON | No |
| Pytest | ≥9.0 | Framework de pruebas | Dev |

---

## Estructura del Proyecto

```
futbot/
├── main.py              # Punto de entrada — orquesta el bucle principal
├── config.py            # 35 constantes en un dataclass + tabla CRC8
├── camera.py            # Captura de frames — 4 backends con fallback automático
├── vision.py            # Pipeline de detección YOLO + HSV con 3 backends ML
├── pipeline.py          # FSM de navegación: SEARCH → CHASE → RECOVERY
├── motors.py            # Control UART — protocolo binario + CRC8 + servos
├── stubs/               # Mocks de hardware para desarrollo sin RPi
│   ├── camera_stub.py   #   Genera frames sintéticos con pelota detectable
│   └── motors_stub.py   #   Almacena comandos en historial para validación
├── models/              # Modelos de red neuronal
│   ├── onnx/            #   Modelo ONNX exportado
│   ├── ncnn/            #   Modelo NCNN (.param + .bin) para ARM
│   ├── tensorrt/        #   (placeholder) Aceleración GPU/NPU futura
│   └── yoloe26n_v2/     #   Pesos del modelo YOLOE26n v2
├── scripts/             # 12 herramientas de diagnóstico y calibración
├── tests/               # 6 archivos de test con 16 casos
├── pyproject.toml       # Gestión de dependencias con uv
└── .gitignore           # Exclusiones: libcamera builds, pycache, secretos
```

---

## Arquitectura

### Flujo de Datos

```
┌──────────┐   np.ndarray   ┌──────────┐   Detections   ┌──────────┐   MotorCommand   ┌────────┐
│  Camera  │ ──────────────►│  Vision  │ ──────────────►│ Pipeline │ ────────────────►│ Motors │
└──────────┘                └──────────┘                └──────────┘                   └────────┘
                                                                                           │
                                                                                     UART serial
                                                                                           │
                                                                               ┌──────────▼──────────┐
                                                                               │   Driver de motores  │
                                                                               │   /dev/ttyAMA0       │
                                                                               └─────────────────────┘
```

### Máquina de Estados Finita (FSM)

```
           ┌──────────────┐
           │              │
           ▼              │
       ┌────────┐  ball   ┌────────┐
       │ SEARCH │ ───────►│ CHASE  │
       └────────┘         └────────┘
           ▲                  │
           │    timeout       │ ball lost > 0.8s
           └──────────────────┘
           ▲                  │
           │    timeout       ▼
           │            ┌──────────┐
           └────────────│ RECOVERY │
                        └──────────┘
```

| Estado | Comportamiento | Disparador de salida |
|--------|---------------|---------------------|
| **SEARCH** | Barrido rotacional (255 speed, 250 ms/paso, 0.3 s entre pasos) | Pelota detectada → CHASE |
| **CHASE** | Servo visual proporcional (gain=0.8, deadband=16 px) | Pelota perdida >0.8 s → RECOVERY |
| **RECOVERY** | Secuencia: retroceso → giro → avance (max 5 ciclos) | Pelota re-detectada → CHASE; timeout → SEARCH |

### Principios de Diseño

- **Módulos planos** — un archivo `.py` por responsabilidad. Sin anidación de operadores, DTOs ni capas de abstracción.
- **Inyección manual** — `main.py` instancia `Config` y lo pasa por constructor a cada módulo. Sin contenedores DI ni decoradores.
- **Dataclasses compartidos** — `Detections`, `Ball`, `Goal`, `WhiteLine`, `MotorCommand` son los únicos tipos que cruzan fronteras entre módulos.
- **Lazy imports** — dependencias opcionales (serial, onnxruntime, ncnn, picamera2) se importan dentro de métodos, no a nivel de módulo.

---

## Rendimiento

| Métrica | ONNX (CPU) | NCNN (ARM NEON) | Solo HSV |
|---------|-----------|-----------------|----------|
| Inferencia YOLO | ~45 ms | ~22 ms | N/A |
| Pipeline completo | ~55 ms | ~30 ms | ~8 ms |
| FPS efectivo | ~18 | ~33 | ~100+ |
| Uso de CPU | 80-90% | 50-60% | 15-20% |

> Mediciones en Raspberry Pi 5, 320×240, yoloe26n_v2, 4 núcleos. El FPS real del bucle está limitado por `time.sleep(0.01)` en `main.py` (~100 FPS máx).

---

## Tests

```bash
cd futbot
FUTBOT_MODE=stub uv run pytest tests/ -v
```

| Archivo | Casos | Qué valida |
|---------|-------|-----------|
| `test_config.py` | 2 | Constantes por defecto, función CRC8 |
| `test_camera.py` | 1 | Instanciación de cámara sin hardware |
| `test_vision.py` | 4 | Dataclasses, detección HSV con frames sintéticos |
| `test_motors.py` | 4 | MotorCommand, mapeo diferencial, conversión PWM, CRC8 |
| `test_pipeline.py` | 4 | Transiciones FSM, servo visual centrado |
| `test_integration.py` | 1 | Bucle completo con stubs (10 ticks) |
| **Total** | **16** | |

---

## Contribuir

### Reportar Bugs

Abre un issue en GitHub incluyendo:
- Versión de Python (`python --version`)
- Backend YOLO activo (`onnx`, `ncnn`, o `ninguno`)
- Log completo de la sesión (`uv run python main.py 2>&1 | tee futbot.log`)
- Descripción del comportamiento esperado vs observado

### Pull Requests

1. Crea una rama desde `develop`: `git checkout -b feat/mi-mejora`
2. Escribe tests para tu cambio (TDD)
3. Ejecuta la suite completa: `FUTBOT_MODE=stub uv run pytest tests/ -v`
4. Asegura que todos los tests pasan
5. Abre PR contra `develop`

### Convenciones de Código

- Docstrings en español, formato Google-style
- Type hints en todas las funciones públicas (`from __future__ import annotations`)
- Logs con `logging.getLogger("futbot.<modulo>")`
- Lazy imports para dependencias opcionales
- Sin dependencias circulares entre módulos

---

## Licencia

MIT © 2025-2026 Futbot Project

Consulta el archivo [LICENSE](LICENSE) para el texto completo.

---

## Documentación Adicional

| Documento | Audiencia | Contenido |
|-----------|-----------|-----------|
| [Guía de Usuario](docs/GUIDE_USERS.md) | Operadores | Preparación, calibración, troubleshooting |
| [Guía Técnica](docs/GUIDE_TECHNICAL.md) | Desarrolladores | Arquitectura, API, protocolos, extensión |
| [Changelog](Changelog.md) | General | Historial completo v2 → v9 |
