# FutBot Vision Model

Sistema de vision y decision para FutBotMX usando YOLO26.

## Estructura

```
futbot_vision_model/
├── src/ai/                    # Modulo principal
│   ├── train.py               # Entrenamiento YOLO26
│   ├── export.py              # Exportar a ONNX/TensorRT
│   ├── inference.py           # Inferencia
│   ├── capture_samples.py     # Captura de imagenes
│   └── augment_dataset.py     # Data augmentation
├── onnx_optimizer/            # Optimizacion ONNX Runtime
│   ├── optimizer.py           # Optimizador principal
│   ├── hardware_detector.py   # Deteccion de hardware
│   ├── quantizer.py           # Cuantizacion INT8
│   └── config.py              # Perfiles de hardware
├── tensorrt_optimizer/        # Optimizacion TensorRT
│   ├── optimizer.py           # Optimizador principal
│   ├── engine_builder.py      # Builder de engines
│   ├── hardware_detector.py   # Deteccion de GPU NVIDIA
│   └── config.py              # Perfiles (Jetson, RTX)
├── configs/
│   └── futbot.yaml            # Configuracion de clases
├── dataset/                   # Dataset YOLO format
└── models/                    # Modelos entrenados
    ├── onnx/{cpu,cuda}/
    └── tensorrt/{jetson_nano,jetson_orin,desktop_rtx}/
```

## Instalacion

Desde la raiz del workspace (`futbot/`):

```bash
# Solo CPU (laptop sin GPU)
uv sync --extra cpu --package futbot-vision

# Con CUDA (Jetson/Desktop NVIDIA)
uv sync --extra cuda --package futbot-vision
```

## TensorRT

TensorRT no se instala via pip (no soporta Python 3.14 aún). Instalar via sistema:

### Jetson Nano/Orin

```bash
# Incluido en JetPack, o instalar manualmente:
sudo apt update
sudo apt install tensorrt python3-libnvinfer-dev
```

### Desktop RTX (requiere Python 3.12)

```bash
# Crear entorno con Python 3.12 para TensorRT
uv venv --python 3.12 .venv-tensorrt
source .venv-tensorrt/bin/activate
pip install tensorrt --extra-index-url https://pypi.nvidia.com
```

El modulo `tensorrt_optimizer` usa la instalacion de TensorRT del sistema.

## Uso

Desde la raiz del workspace (`futbot/`):

### Entrenar modelo

```bash
# Entrenamiento produccion (200 epochs, yolo26m)
uv run --package futbot-vision main.py train --production

# Entrenamiento rapido (50 epochs, yolo26n)
uv run --package futbot-vision main.py train --quick

# Personalizado
uv run --package futbot-vision main.py train --model yolo26m.pt --epochs 200 --batch 32
```

### Exportar modelo

```bash
# Exportar para Jetson Nano
uv run --package futbot-vision main.py export models/yolo26m_futbot/weights/best.pt --target jetson_nano

# Exportar para Desktop RTX
uv run --package futbot-vision main.py export models/yolo26m_futbot/weights/best.pt --target desktop

# Exportar todo (ONNX + TensorRT)
uv run --package futbot-vision main.py export models/yolo26m_futbot/weights/best.pt --format all
```

### Inferencia

```bash
# Probar modelo
uv run --package futbot-vision main.py infer models/onnx/cpu/yolo26m_futbot.onnx --source test.jpg

# Benchmark
uv run --package futbot-vision main.py infer models/tensorrt/jetson_nano/yolo26m_futbot.engine --benchmark
```

### Capturar imagenes

```bash
# Capturar imagenes manualmente (c) o auto (a)
uv run --package futbot-vision main.py capture --output dataset/images/raw

# Capturar video
uv run --package futbot-vision main.py capture --video --duration 60
```

### Augmentar dataset

```bash
# Augmentar imagenes
uv run --package futbot-vision main.py augment dataset/images/train --output dataset/images/augmented --count 3

# Con labels YOLO
uv run --package futbot-vision main.py augment dataset/images/train --labels-dir dataset/labels/train --count 2
```

### Detectar hardware

```bash
# Detectar perfil ONNX
uv run --package futbot-vision main.py detect onnx

# Detectar perfil TensorRT
uv run --package futbot-vision main.py detect tensorrt
```

## Clases

Editar `configs/futbot.yaml`:

```yaml
nc: 4  # numero de clases
names:
  0: ball
  1: goal_yellow
  2: goal_blue
  3: robot
```

Para agregar clases, incrementar `nc` y agregar nombres.

## Perfiles de optimizacion

### ONNX Runtime

| Perfil | Hardware | Precision |
|--------|----------|-----------|
| cpu_arm_jetson | Jetson CPU | FP16 |
| cpu_arm_rpi | Raspberry Pi | FP32 |
| cpu_x86_avx2 | Desktop x86 | INT8 dynamic |
| gpu_cuda | NVIDIA GPU | FP16 |

### TensorRT

| Perfil | Hardware | Precision | Workspace |
|--------|----------|-----------|-----------|
| jetson_nano | Jetson Nano 4GB | FP16 | 512MB |
| jetson_orin | Jetson Orin/NX | FP16 | 1GB |
| desktop_rtx | RTX 20xx/30xx/40xx | FP16 | 2GB |
