# Hybrid Camera Controller (main.py)

`main.py` runs a 2-wheel finite-state controller with three states:

- `SEARCH`: sweeps with in-place turns until the ball is detected.
- `CHASE`: drives with differential wheel speeds to center and approach the ball.
- `AVOID_MAP`: executes bounded reverse/turn/forward recovery micro-steps to avoid close obstacles or close-shot collisions; it may exit early to `CHASE` when hybrid risk clears and the ball is visible again.

## Hybrid trigger

`AVOID_MAP` is triggered when **either** condition is true:

- ultrasonic distance is below `DIST_TRIGGER_MM`
- detected ball radius is above `RADIUS_TRIGGER_PX`

This is an OR trigger (`distance OR radius`), and both are checked every loop (`distance` sampled every `ULTRA_EVERY_N_FRAMES`).

## Prerequisites

- Python dependencies installed from `pyproject.toml`.
- Módulo IMX219 CSI conectado al Raspberry Pi 5 (cable flexible CSI Pi5). `cam.py:find_camera()` lo detecta automáticamente probando, en orden: `picamera2` → GStreamer `libcamerasrc` → V4L2 `/dev/video0`.
- Setup en **Ubuntu Server 24.04 para Raspberry Pi 5**:
  1. Habilitar el sensor IMX219 en el firmware. Editar `/boot/firmware/config.txt` y asegurarse de tener bajo `[all]` (o el bloque del Pi 5):
     ```
     camera_auto_detect=0
     dtoverlay=imx219
     ```
     Guardar y `sudo reboot`.
  2. Instalar libcamera + GStreamer. Ubuntu Server 24 para Pi **no tiene** `rpicam-apps`, `libcamera-apps` ni `python3-picamera2` en los repos — solo los paquetes bajo el namespace `libcamera`:
     ```bash
     sudo apt update
     sudo apt install -y libcamera-tools libcamera-v4l2 python3-libcamera \
                         libcamera-ipa libcamera0.2 \
                         gstreamer1.0-libcamera gstreamer1.0-plugins-base \
                         gstreamer1.0-plugins-good gstreamer1.0-tools
     ```
  3. Verificar que la cámara se enumera (no existe `rpicam-hello`, se usa `cam` y GStreamer):
     ```bash
     cam -l                                                  # debe listar la IMX219
     gst-launch-1.0 libcamerasrc num-buffers=5 ! fakesink -v # no debe dar error
     dmesg | grep -i imx219                                  # kernel ve el sensor
     ls /dev/video*                                          # con libcamera-v4l2 aparecen devices
     ```
     Si `cam -l` no lista la IMX219, revisar cable CSI y `/boot/firmware/config.txt`.
  4. En este setup el camino utilizado por `find_camera()` es GStreamer `libcamerasrc` (segundo fallback). `picamera2` no está disponible vía apt y no se necesita. Con `libcamera-v4l2` la cámara también aparece como `/dev/video0`, así que el tercer fallback V4L2 funciona como respaldo.
- Robot hardware connected for runtime control (`SerialBus` + `SharedI2CBus`).

## Run

```bash
python main.py
```

## Tuning constants

Adjust controller behavior in the constants block near the top of `main.py` (search/chase/avoid speeds, durations, and thresholds), especially:

- `DIST_TRIGGER_MM`, `RADIUS_TRIGGER_PX`, `ULTRA_EVERY_N_FRAMES`
- `CHASE_SPEED_BASE`, `CHASE_ROT_GAIN`, `CHASE_DEADBAND_PX`
- `SEARCH_TURN_SPEED`, `SEARCH_TURN_MS`
- `AVOID_*` values (`AVOID_REVERSE_*`, `AVOID_TURN_*`, `AVOID_FORWARD_*`, `AVOID_MAX_STEPS`)

## Runtime behavior

- `main.py` currently runs for `DURATION = 60.0` seconds, then stops and releases hardware in `finally`.

## Hardware dependencies

`main.py` expects runtime dependencies provided by `cam.py`:

- `SerialBus` for motor/servo burst commands
- `SharedI2CBus` for ultrasonic reads
- cámara CSI IMX219 detectada automáticamente por `find_camera()` (picamera2 / libcamerasrc / V4L2)
