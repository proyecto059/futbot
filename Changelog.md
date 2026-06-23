# Changelog

Todos los cambios están rastreados desde el contenido de los archivos, no desde el historial de git.

---

## futbot-v2 (base inicial)

**Archivos y estructura:**
- `main.py` — FSM de 3 estados (SEARCH → CHASE → AVOID_MAP), 559 líneas, orquestación en un solo archivo
- `cam.py` — `SerialBus` (UART serial a driver de motores) + `SharedI2CBus` (sensor ultrasónico + seguidor de línea) + `differential()` + CRC8 + shims de visión, 683 líneas
- `husky.ino` — Firmware legacy para Arduino con HuskyLens AI (no usado en sistema RPi5 actual), 461 líneas
- `huskytest.py` — Test del sensor HuskyLens
- `capture_frame.py` — Captura de frames standalone
- `debug_vision.py` — Diagnóstico de visión
- `src/vision/` — `HybridVisionService` con patrón de operadores (frame capture, YOLO ONNX, HSV ball, ball fusion, goal color, white line, JSON export)
- `src/pipeline/` — `PipelineService` con operadores (search, chase, avoid)
- `src/motors/` — `MotorService` con operadores (movement, differential, burst + CRC8)
- `src/ultrasonic/` — `UltrasonicService` vía I2C (smbus2)
- `src/chase/` — Operadores avanzados de persecución (attack_geometry, ball_goal_controller, visual_servo, search)
- `src/pipeline5/` — Variante anterior de pipeline
- `src/output/` — Datos de prueba
- `models/` — Modelo ONNX
- `test-robot/` — Sub-proyecto legacy de pruebas de hardware (33 entradas)
- `tests/` — Suite de tests con pytest
- `scripts/` — Scripts de calibración y diagnóstico
- `docs/` — Planes de diseño (migración husky-to-cam)
- `pyproject.toml` — Python 3.11-3.14, uv-managed
- `uv.lock` — Lockfile de dependencias

**Dependencias:** `opencv-python-headless`, `numpy`, `pyserial`, `smbus2`, `onnxruntime`

**Arquitectura:** Híbrida FSM + HybridVisionService, un solo robot autónomo, YOLO solo ONNX

---

## futbot-v3

**Cambios vs v2:**
- **Eliminado:** `src/pipeline5/`, `src/output/`, `src/src/` anidado (limpieza de versiones anteriores)
- **Añadido:** `chmod`, `cp` (scripts de sistema)
- **Añadido:** `clean_futbot.sh` (script de limpieza)

**Sin cambios en:** `main.py`, `cam.py`, `husky.ino`, `pyproject.toml`, lógica de visión/motores/pipeline

---

## futbot-v4

**Cambios vs v3:**
- **Añadido:** `output/` — Salida de diagnósticos (`futbot_diagnostics.json`, `futbot_live_diag/`, `fix_vision/`, test runs 1-6)
- **Añadido:** `src/main_pipeline2.py` y `src/pipeline2/` — Variante experimental del pipeline

**Sin cambios en:** `main.py`, `cam.py`, `pyproject.toml`, módulos core

---

## futbot-v5

**Cambios vs v4:**
- **Eliminado:** `src/pipeline2/`, `src/main_pipeline2.py` (variante experimental descartada)
- **Ampliado:** `output/` — Más tests de búsqueda por resolución, diagnósticos en vivo

**Sin cambios en:** `main.py`, `cam.py`, módulos core

---

## futbot-v6

**Cambios vs v5:**
- **Cambio de dependencia:** `opencv-python-headless` → `opencv-python` (soporte GUI)
- **Nuevo backend YOLO:** NCNN (inferencia nativa optimizada para ARM en RPi)
- **Dependencias opcionales:**
  - Grupo `onnx`: `onnxruntime` (movido de obligatorio a opcional)
  - Grupo `model-tools`: `onnxruntime` + `ultralytics` (entrenamiento/conversión de modelos)
  - Grupo `rpi`: `ncnn`
- **Añadido:** `models/onnx/` y `models/ncnn/` — Subdirectorios por backend
- **Añadido:** `vision/` en raíz — Duplicado del módulo de visión (junto a `src/vision/`)
- **Añadido:** `runs/` — Directorio de ejecuciones de entrenamiento/inferencia
- **Añadido:** `yolo26n-384.tar.gz`, `yolo26n-futbot-may24.tar.gz` — Archivos de modelos comprimidos
- **Añadido:** Imágenes de debug (`image.png`, `image_annotated.png`, `image_annotated_debug.png`, `i2mage.png`, `ima2ge.png`)
- **Añadido:** `futbot-v6/` anidado — Copia recursiva del proyecto (probablemente accidental)

**Arquitectura:** Misma FSM + HybridVisionService, ahora con soporte multi-backend YOLO (ONNX + NCNN)

---

## futbot-v7

**Cambios vs v6:**
- **Añadido:** `models.backup/` — Respaldo de modelos
- **Ampliado:** `output/` — 6 test runs extensivos, búsquedas por resolución, snapshots de attack geometry

**Sin cambios en:** `main.py`, `cam.py`, módulos core, `pyproject.toml`

---

## futbot-v8

**Cambios vs v7 (versión más completa standalone):**

### Dependencias y modelos
- **Nuevo backend YOLO:** TensorRT (inferencia acelerada por GPU/NPU)
- **Nuevo modelo:** `models/yoloe26n_v2/` — Variante YOLOE (eficiente)
- **Nuevo subdirectorio:** `models/tensorrt/`
- Misma estructura de dependencias opcionales de v7

### Visión y operadores
- 9 operadores en `src/vision/operators/` plenamente desarrollados:
  - `frame_capture_operator.py` — Captura de frames con backend resolver (libcamera/GStreamer)
  - `yolo_inference_operator.py` — Inferencia YOLO multi-backend
  - `yolo_parser_operator.py` — Parseo de resultados YOLO
  - `hsv_ball_detector_operator.py` — Detección HSV de pelota (fallback)
  - `ball_fusion_operator.py` — Fusión de detecciones YOLO + HSV
  - `goal_color_operator.py` — Detección de color de portería
  - `white_line_operator.py` — Detección de línea blanca
  - `json_export_operator.py` — Exportación JSON para diagnósticos
  - `__init__.py` — Barrel exports

### Scripts de diagnóstico (11 scripts)
- `analyze_image.py` — Análisis de imágenes
- `cal_chase_fading.py` — Calibración de fading en persecución
- `cal_motors.py` — Calibración interactiva de motores
- `capture_attack_geometry.py` — Captura de geometría de ataque
- `capture_image.py` — Captura de imagen standalone
- `capture_vision_debug.py` — Captura con debug de visión
- `copy_husky.py` — Port de lógica FSM del Arduino a Python puro
- `focus_camera.py` — Ajuste de foco de cámara
- `search_ball_resolutions.py` — Búsqueda de resoluciones óptimas
- `test_chase_dynamic.py` — Test dinámico de persecución
- `test_motors_raw.py` — Test crudo de protocolo de motores

### Tests
- 15 archivos de test en `tests/`
- `test-robot/` legacy preservado (33 entradas)

### Documentación
- 27 documentos de diseño en `docs/plans/` (abril-mayo 2026):
  - Cambios de modelo (model switches)
  - Analizadores de visión (vision analyzers)
  - Correcciones de portería azul (blue goal fix)
  - Alineación en arco (align-arc)
  - Ruta detrás del balón (behind-ball route)
  - Geometría de ataque (attack geometry)
  - Búsqueda consciente de líneas (line-aware search)
  - Persecución suave (smooth chase)
  - Controlador balón-portería (ball-goal controller)
  - Migración copy-husky

### Output
- `output/` extenso: test runs, búsquedas por resolución, diagnósticos de cámara (`imx219_*`)

**Arquitectura:** Misma FSM + HybridVisionService de v7, con triple backend YOLO (ONNX + NCNN + TensorRT) y operadores de chase más sofisticados

---

## futbot-ws

**Cambios vs v8 (mayor evolución arquitectónica):**

### Nueva arquitectura: P2P Multi-Robot
- **WebSocket P2P** entre 2 robots (robot1 como servidor/AP, robot2 como cliente)
- **Roles FSM:** `atacante` (SEARCH→CHASE), `defensor` (giros defensivos lentos), `espera` (esperando asignación)
- **WiFi AP:** robot1 crea Access Point (hostapd + dnsmasq); robot2 se conecta como cliente

### Nuevos módulos
- `src/communication/` — WebSocket P2P:
  - `communication_gateway.py` — Gateway de comunicación
  - `communication_service.py` — Servicio de comunicación
  - `role_state.py` — Estado de rol compartido entre robots
  - `ws_runner.py` — WebSocket asyncio en hilo daemon
  - `ap_manager.py` — Gestión de WiFi AP para robot1
  - `dto/robot_state_dto.py` — DTO de estado del robot
- `src/strategy/` — Estrategia por rol:
  - `strategy_service.py` — Selección de estrategia según rol
  - `dto/roles_dto.py` — DTO de roles
- `src/pipes/` — Validación:
  - `validation_pipe.py` — Validación de mensajes entrantes

### Nuevo entry point
- `src/main.py` (271 líneas) — Orquestador modular con soporte para 3 modos:
  - `CONSOLE_MODE` (servidor): Operador humano envía comandos remotos vía WebSocket
  - `REMOTE_CONTROL` (cliente): Recibe y ejecuta comandos del servidor
  - `NORMAL` (autónomo): FSM completo con asignación de roles vía WebSocket
- `main.py` raíz (559 líneas) — Preservado como legacy

### Stubs de hardware
- `stubs/hardware_stubs.py` — Mocks de cámara, motores y sensores para desarrollo local sin hardware físico
- `conftest.py` — Fixture de pytest para stubs

### Deploy
- `Makefile` — Comandos de deploy con rsync a 2 robots RPi
- `config/` — Configuración de red RPi (hostapd, dnsmasq, netplan, sudoers)
- `config.env` — Plantilla de variables de entorno

### Scripts de red
- `scripts/setup_ap.sh` — Configuración de Access Point
- `scripts/setup_client.sh` — Configuración de cliente WiFi

### Dependencias
- **Añadido:** `websockets>=12.0`
- **Eliminado vs v8:** `smbus2` (sin I2C en esta rama), dependencias opcionales simplificadas
- `pyproject.toml` actualizado con nuevos scripts de entry point

### Tests
- `tests/test_communication.py` — Tests del módulo de comunicación
- `tests/test_pipeline_roles.py` — Tests del pipeline con roles

### Documentación
- `README.md` completo (223 líneas) — Setup, arquitectura, variables de entorno, dependencias

### `cam.py` reducido
- `cam.py` (49 líneas) — Solo test simple de OpenCV, sin hardware control (SerialBus/I2C removidos)

### `pipeline.py` modificado
- `src/pipeline/pipeline_service.py` — Ahora role-aware (consulta `RoleState` antes de decidir estado)
- `src/pipeline/operators/` — Adaptados para recibir rol como parámetro

---

## Resumen de evolución

| Versión | YOLO backends | Comunicación | Robot | Complejidad |
|---------|--------------|-------------|-------|-------------|
| v2-v5   | ONNX         | Ninguna     | 1     | Baja (FSM en main.py) |
| v6-v7   | ONNX + NCNN  | Ninguna     | 1     | Media (operadores separados) |
| v8      | ONNX + NCNN + TensorRT | Ninguna | 1 | Media-Alta (9 operadores visión, 11 scripts, 27 docs) |
| ws      | ONNX         | WebSocket P2P | 2 | Alta (capas comm/strategy/pipes/DTOs + roles) |

---

## Refactor v9 (planificado)

Ver `docs/superpowers/specs/2026-06-22-futbot-refactor-design.md` para el diseño completo.

**Objetivos:**
- Unificar v2-v8+ws en una sola codebase plana (8 módulos `.py`)
- Preservar multi-backend YOLO de v8 y stubs de ws
- Eliminar P2P WebSocket, roles, WiFi AP, ultrasónico, HuskyLens/Arduino
- Arquitectura plana sin anidación de operadores
- Inyección de dependencias manual (sin contenedores ni decoradores)
- Modo `FUTBOT_MODE=stub` para desarrollo local
