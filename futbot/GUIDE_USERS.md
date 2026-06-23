# Guía de Usuario — Futbot v9

Guía práctica para operadores del robot físico. Cubre preparación, ejecución, calibración y solución de problemas.

---

## Tabla de Contenidos

1. [Preparación del Robot](#preparación-del-robot)
2. [Ejecución](#ejecución)
3. [Modos de Operación](#modos-de-operación)
4. [Calibración](#calibración)
5. [Scripts de Diagnóstico](#scripts-de-diagnóstico)
6. [Monitoreo en Tiempo Real](#monitoreo-en-tiempo-real)
7. [Solución de Problemas](#solución-de-problemas)
8. [Mantenimiento](#mantenimiento)

---

## Preparación del Robot

### Conexiones Físicas

Antes de encender, verifica:

| Conexión | Puerto / Cable | Verificación |
|----------|---------------|-------------|
| Cámara CSI | Ribbon cable IMX219 → conector CSI de RPi5 | Asegurar que el clip esté firme |
| Driver de motores | UART → pines GPIO 14/15 (TX/RX) | LEDs del driver encendidos al alimentar |
| Batería | Conector de alimentación del driver | Voltaje suficiente (≥11.1V para LiPo 3S) |
| Servos | Conectores PWM en el driver | Sin obstrucciones mecánicas |

### Encendido

1. Conecta la batería al driver de motores
2. Espera a que la Raspberry Pi 5 inicie (~30 segundos)
3. Verifica que el LED de actividad de la RPi parpadee normalmente
4. Conéctate por SSH: `ssh usuario@<ip-de-la-rpi>`

### Verificación Pre-vuelo

```bash
# Verificar que la cámara CSI es detectada
libcamera-hello --list-cameras

# Verificar que el puerto UART existe
ls -la /dev/ttyAMA0

# Verificar que Python y dependencias están instaladas
cd ~/futbot/futbot
uv run python -c "import cv2; print('OpenCV', cv2.__version__)"
```

---

## Ejecución

### Inicio Normal (Modo Autónomo)

```bash
cd ~/futbot/futbot
uv run python main.py
```

El robot comenzará inmediatamente el bucle FSM:
1. **BUSCAR:** Girará sobre sí mismo escaneando el entorno con la cámara
2. **PERSEGUIR:** Al detectar la pelota naranja, avanzará hacia ella corrigiendo la dirección
3. **RECUPERAR:** Si pierde la pelota, hará maniobras de retroceso y giro para reencontrarla

### Apagado

Presiona `Ctrl+C` **una sola vez**. El robot:
1. Detendrá todos los motores
2. Cerrará la conexión UART
3. Liberará la cámara

El proceso tarda ~1 segundo. No desconectes la batería durante el apagado.

### Parada de Emergencia

Si `Ctrl+C` no responde:
1. Desconecta físicamente la batería del driver de motores
2. Espera 5 segundos
3. Reconecta y reinicia normalmente

---

## Modos de Operación

### Modo Real (Hardware)

```bash
# Por defecto — no requiere variable de entorno
uv run python main.py

# Explícito
FUTBOT_MODE=real uv run python main.py
```

La cámara CSI IMX219 captura frames reales. Los comandos se envían al driver de motores vía UART.

### Modo Stub (Pruebas sin Robot)

```bash
FUTBOT_MODE=stub uv run python main.py
```

- La cámara genera frames sintéticos (campo verde con círculo naranja)
- Los comandos de motores se imprimen en la terminal en lugar de enviarse por UART
- Útil para desarrollo, depuración y pruebas en una laptop

---

## Calibración

### Calibración de Motores

```bash
cd ~/futbot/futbot
uv run python scripts/cal_motors.py
```

Este script interactivo te permite probar cada dirección de movimiento:
- Avance / retroceso
- Giro izquierda / derecha
- Stop

Ajusta los valores en `config.py` si es necesario:
```python
# Velocidades base (0-255)
chase_speed_base: float = 80.0
search_turn_speed: float = 255.0
recovery_reverse_speed: float = 110.0

# Ganancia proporcional del servo visual
chase_rot_gain: float = 0.8
```

### Calibración de Cámara

```bash
# Enfocar la cámara
uv run python scripts/focus_camera.py

# Capturar una imagen de prueba
uv run python scripts/capture_image.py
```

Revisa la imagen capturada para verificar:
- La pelota naranja se ve con colores correctos (no sobreexpuesta ni subexpuesta)
- El campo de visión cubre adecuadamente el área de juego

Ajusta en `config.py`:
```python
camera_exposure_default: int = 200  # Aumentar si la imagen es oscura
camera_width: int = 320            # Resolución de captura
camera_height: int = 240
```

### Calibración de Persecución

```bash
# Prueba dinámica de persecución
uv run python scripts/test_chase_dynamic.py

# Calibración de fading (transición suave de velocidades)
uv run python scripts/cal_chase_fading.py
```

---

## Scripts de Diagnóstico

Todos los scripts están en `scripts/`:

| Script | Propósito |
|--------|----------|
| `cal_motors.py` | Calibración interactiva de motores |
| `cal_chase_fading.py` | Calibración de transiciones suaves en persecución |
| `focus_camera.py` | Ajuste de foco de la cámara CSI |
| `capture_image.py` | Captura una imagen de prueba |
| `capture_vision_debug.py` | Captura con overlay de detecciones |
| `capture_attack_geometry.py` | Captura para análisis de geometría de ataque |
| `test_motors_raw.py` | Prueba cruda del protocolo UART de motores |
| `test_chase_dynamic.py` | Prueba dinámica de persecución |
| `search_ball_resolutions.py` | Búsqueda de resolución óptima de cámara |
| `analyze_image.py` | Análisis de imagen guardada |
| `copy_husky.py` | Implementación de referencia del FSM original |

Uso general:
```bash
cd ~/futbot/futbot
uv run python scripts/<script>.py
```

---

## Monitoreo en Tiempo Real

### Logs

El robot emite logs formateados con timestamp. Para verlos en tiempo real:

```bash
uv run python main.py 2>&1 | tee futbot.log
```

Ejemplo de salida:
```
12:34:56 [INFO] futbot: futbot iniciando en modo real
12:34:57 [INFO] futbot.camera: picamera2: 320x240 OK
12:34:57 [INFO] futbot.motors: UART conectado: /dev/ttyAMA0 @ 1000000 baud
12:34:57 [INFO] futbot: Servicios inicializados. Ancho de frame: 320
12:34:58 [INFO] futbot.pipeline: fsm: SEARCH -> CHASE
```

### Interpretación de Logs

| Mensaje | Significado |
|---------|------------|
| `fsm: SEARCH -> CHASE` | El robot detectó la pelota |
| `fsm: CHASE -> RECOVERY` | Perdió la pelota, inicia recuperación |
| `fsm: RECOVERY -> SEARCH` | No pudo reencontrar la pelota |
| `YOLO backend onnx no disponible` | ONNX Runtime no instalado, usando solo HSV |
| `picamera2 no disponible` | Cámara CSI no detectada, probando otros backends |

---

## Solución de Problemas

### El robot no se mueve

1. Verifica que la batería esté cargada y conectada
2. Revisa que el puerto UART exista: `ls -la /dev/ttyAMA0`
3. Prueba los motores individualmente: `uv run python scripts/test_motors_raw.py`
4. Verifica que `pyserial` esté instalado: `uv run python -c "import serial"`

### La cámara no funciona

1. Verifica el cable ribbon CSI (desconecta y reconecta)
2. Comprueba que la cámara esté habilitada: `sudo raspi-config` → Interfaces → Camera
3. Prueba con libcamera: `libcamera-hello -t 3000`
4. Si libcamera funciona pero el script no, revisa los backends en el log
5. El script prueba automáticamente: picamera2 → libcamera subprocess → GStreamer → V4L2

### La pelota no se detecta

1. Verifica la iluminación del campo (la detección HSV es sensible a cambios de luz)
2. Captura una imagen de debug: `uv run python scripts/capture_vision_debug.py`
3. Ajusta los umbrales HSV en `config.py`:
   ```python
   ball_hsv_lower: Tuple[int, int, int] = (0, 80, 80)    # H min, S min, V min
   ball_hsv_upper: Tuple[int, int, int] = (65, 255, 255)  # H max, S max, V max
   ```
4. Si usas YOLO, verifica que el modelo exista en `models/yoloe26n_v2/onnx/`

### El robot gira sin control

1. Verifica el mapeo diferencial — las ruedas podrían estar conectadas en orden incorrecto
2. Prueba cada dirección con `scripts/cal_motors.py`
3. Revisa la ganancia proporcional `chase_rot_gain` (reducir si oscila)

### Error "UART conectado" pero no hay respuesta

1. Verifica que el driver de motores esté alimentado (LEDs encendidos)
2. Comprueba la velocidad de baudios: debe ser 1,000,000 en ambos lados
3. Prueba con `scripts/test_motors_raw.py` que envía comandos crudos

---

## Mantenimiento

### Batería

- Carga la batería LiPo con un cargador balanceado
- No descargues por debajo de 3.3V por celda
- Almacena a ~3.8V por celda si no se usa por períodos largos

### Cámara

- Limpia el lente con un paño de microfibra
- Verifica que el cable ribbon no esté doblado o dañado
- Re-enfoca si es necesario con `scripts/focus_camera.py`

### Motores y Servos

- Verifica que los servos no estén forzados mecánicamente al inicio
- Los ángulos centrales por defecto son pan=70°, tilt=45°
- Lubrica los engranajes si presentan ruido excesivo

### Software

```bash
# Actualizar dependencias
uv sync --upgrade

# Verificar que los tests pasan después de cambios
FUTBOT_MODE=stub uv run pytest tests/ -v
```
