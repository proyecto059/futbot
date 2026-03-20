import platform
import subprocess
from typing import Optional

from .config import PROFILES, DEFAULT_PROFILE


def is_jetson() -> bool:
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().lower()
            return "jetson" in model
    except (FileNotFoundError, PermissionError):
        return False


def is_raspberry_pi() -> bool:
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read().lower()
            return "raspberry pi" in model
    except (FileNotFoundError, PermissionError):
        return False


def has_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_cpu_features() -> list[str]:
    features = []
    
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read().lower()
            if "avx512" in cpuinfo:
                features.append("avx512")
            elif "avx2" in cpuinfo:
                features.append("avx2")
            elif "sse4" in cpuinfo:
                features.append("sse4")
    except (FileNotFoundError, PermissionError):
        pass
    
    return features


def detect_hardware() -> dict:
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine().lower(),
        "is_jetson": is_jetson(),
        "is_raspberry_pi": is_raspberry_pi(),
        "has_cuda": has_cuda(),
        "cpu_features": get_cpu_features(),
    }


def get_hardware_profile(hardware_info: Optional[dict] = None) -> str:
    if hardware_info is None:
        hardware_info = detect_hardware()
    
    if hardware_info["has_cuda"]:
        return "gpu_cuda"
    
    if hardware_info["is_jetson"]:
        return "cpu_arm_jetson"
    
    if hardware_info["is_raspberry_pi"]:
        return "cpu_arm_rpi"
    
    cpu_features = hardware_info.get("cpu_features", [])
    if "avx512" in cpu_features:
        return "cpu_x86_avx512"
    if "avx2" in cpu_features:
        return "cpu_x86_avx2"
    
    return DEFAULT_PROFILE


def get_profile(profile_name: Optional[str] = None) -> str:
    if profile_name and profile_name in PROFILES:
        return profile_name
    return get_hardware_profile()
