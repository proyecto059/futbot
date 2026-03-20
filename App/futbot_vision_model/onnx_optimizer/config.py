from dataclasses import dataclass
from typing import Optional


@dataclass
class OnnxProfile:
    name: str
    opt_level: int
    fp16: bool
    quantize: Optional[str] = None
    provider: str = "CPUExecutionProvider"
    description: str = ""


PROFILES: dict[str, OnnxProfile] = {
    "cpu_arm_jetson": OnnxProfile(
        name="cpu_arm_jetson",
        opt_level=3,
        fp16=True,
        provider="CPUExecutionProvider",
        description="Jetson ARM CPU con soporte NEON",
    ),
    "cpu_arm_rpi": OnnxProfile(
        name="cpu_arm_rpi",
        opt_level=2,
        fp16=False,
        quantize="dynamic_int8",
        provider="CPUExecutionProvider",
        description="Raspberry Pi ARM con INT8 dinámico",
    ),
    "cpu_x86_avx2": OnnxProfile(
        name="cpu_x86_avx2",
        opt_level=3,
        fp16=False,
        quantize="dynamic_int8",
        provider="CPUExecutionProvider",
        description="CPU x86 con AVX2, quantización INT8",
    ),
    "cpu_x86_avx512": OnnxProfile(
        name="cpu_x86_avx512",
        opt_level=3,
        fp16=False,
        quantize="dynamic_int8",
        provider="CPUExecutionProvider",
        description="CPU x86 con AVX512, quantización INT8",
    ),
    "gpu_cuda": OnnxProfile(
        name="gpu_cuda",
        opt_level=3,
        fp16=True,
        provider="CUDAExecutionProvider",
        description="NVIDIA GPU con CUDA",
    ),
}

DEFAULT_PROFILE = "cpu_x86_avx2"
