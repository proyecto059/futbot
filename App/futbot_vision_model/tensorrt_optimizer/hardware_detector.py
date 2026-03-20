import subprocess
from typing import Optional
from dataclasses import dataclass

from .config import PROFILES, DEFAULT_PROFILE


@dataclass
class GPUInfo:
    name: str
    vram_mb: int
    compute_capability: tuple[int, int]
    is_jetson: bool
    jetson_model: Optional[str] = None


def is_jetson() -> bool:
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().lower()
            return "jetson" in model
    except (FileNotFoundError, PermissionError):
        return False


def get_jetson_model() -> Optional[str]:
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().strip().lower()
            if "nano" in model:
                return "jetson_nano"
            elif "orin" in model:
                return "jetson_orin"
            elif "xavier" in model:
                return "jetson_xavier"
            elif "tx2" in model:
                return "jetson_tx2"
    except (FileNotFoundError, PermissionError):
        pass
    return None


def get_nvidia_gpus() -> list[dict]:
    gpus = []
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        compute_str = parts[2]
                        try:
                            major, minor = map(int, compute_str.split("."))
                            compute_cap = (major, minor)
                        except ValueError:
                            compute_cap = (0, 0)
                        
                        gpus.append({
                            "name": parts[0],
                            "vram_mb": int(float(parts[1])),
                            "compute_capability": compute_cap,
                        })
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return gpus


def detect_gpu() -> dict:
    jetson = is_jetson()
    jetson_model = get_jetson_model() if jetson else None
    
    gpus = get_nvidia_gpus() if not jetson else []
    
    if jetson and jetson_model:
        vram_mb = 4096 if "nano" in jetson_model else 8192
        compute_cap = (5, 3) if "nano" in jetson_model else (7, 2)
        gpus = [{
            "name": f"NVIDIA {jetson_model.replace('_', ' ').title()}",
            "vram_mb": vram_mb,
            "compute_capability": compute_cap,
        }]
    
    return {
        "is_jetson": jetson,
        "jetson_model": jetson_model,
        "gpus": gpus,
        "has_cuda": len(gpus) > 0,
    }


def get_gpu_profile(gpu_info: Optional[dict] = None) -> str:
    if gpu_info is None:
        gpu_info = detect_gpu()
    
    if gpu_info["is_jetson"]:
        model = gpu_info.get("jetson_model", "")
        if "nano" in model:
            return "jetson_nano"
        elif "orin" in model:
            return "jetson_orin"
        elif "xavier" in model:
            return "jetson_orin"
        return "jetson_nano"
    
    gpus = gpu_info.get("gpus", [])
    if not gpus:
        return DEFAULT_PROFILE
    
    gpu = gpus[0]
    vram = gpu.get("vram_mb", 0)
    
    if vram >= 32000:
        return "datacenter"
    elif vram >= 8000:
        return "desktop_rtx"
    else:
        return "desktop_rtx"


def get_profile(profile_name: Optional[str] = None) -> str:
    if profile_name and profile_name in PROFILES:
        return profile_name
    return get_gpu_profile()


def is_tensorrt_available() -> bool:
    try:
        import tensorrt
        return True
    except ImportError:
        return False
