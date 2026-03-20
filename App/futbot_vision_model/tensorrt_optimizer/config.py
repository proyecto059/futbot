from dataclasses import dataclass


@dataclass
class TensorRTProfile:
    name: str
    precision: str
    workspace: int
    max_batch: int
    dla_enable: bool
    description: str
    min_shape: tuple = (1, 3, 640, 640)
    opt_shape: tuple = (1, 3, 640, 640)
    max_shape: tuple = (1, 3, 640, 640)


PROFILES: dict[str, TensorRTProfile] = {
    "jetson_nano": TensorRTProfile(
        name="jetson_nano",
        precision="fp16",
        workspace=512 * 1024 * 1024,
        max_batch=1,
        dla_enable=False,
        description="Jetson Nano 4GB - FP16, workspace 512MB",
        min_shape=(1, 3, 640, 640),
        opt_shape=(1, 3, 640, 640),
        max_shape=(1, 3, 640, 640),
    ),
    "jetson_orin": TensorRTProfile(
        name="jetson_orin",
        precision="fp16",
        workspace=1024 * 1024 * 1024,
        max_batch=1,
        dla_enable=True,
        description="Jetson Orin/NX - FP16, DLA enabled, workspace 1GB",
        min_shape=(1, 3, 640, 640),
        opt_shape=(1, 3, 640, 640),
        max_shape=(1, 3, 640, 640),
    ),
    "jetson_orin_int8": TensorRTProfile(
        name="jetson_orin_int8",
        precision="int8",
        workspace=1024 * 1024 * 1024,
        max_batch=1,
        dla_enable=True,
        description="Jetson Orin/NX - INT8 con calibración",
        min_shape=(1, 3, 640, 640),
        opt_shape=(1, 3, 640, 640),
        max_shape=(1, 3, 640, 640),
    ),
    "desktop_rtx": TensorRTProfile(
        name="desktop_rtx",
        precision="fp16",
        workspace=2 * 1024 * 1024 * 1024,
        max_batch=4,
        dla_enable=False,
        description="Desktop RTX 20xx/30xx/40xx - FP16, workspace 2GB",
        min_shape=(1, 3, 640, 640),
        opt_shape=(2, 3, 640, 640),
        max_shape=(4, 3, 640, 640),
    ),
    "desktop_rtx_int8": TensorRTProfile(
        name="desktop_rtx_int8",
        precision="int8",
        workspace=2 * 1024 * 1024 * 1024,
        max_batch=4,
        dla_enable=False,
        description="Desktop RTX - INT8 con calibración",
        min_shape=(1, 3, 640, 640),
        opt_shape=(2, 3, 640, 640),
        max_shape=(4, 3, 640, 640),
    ),
    "datacenter": TensorRTProfile(
        name="datacenter",
        precision="fp16",
        workspace=4 * 1024 * 1024 * 1024,
        max_batch=8,
        dla_enable=False,
        description="Datacenter A100/H100 - FP16, workspace 4GB",
        min_shape=(1, 3, 640, 640),
        opt_shape=(4, 3, 640, 640),
        max_shape=(8, 3, 640, 640),
    ),
}

DEFAULT_PROFILE = "desktop_rtx"
