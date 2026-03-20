from pathlib import Path
from typing import Optional
import logging

from .config import PROFILES, DEFAULT_PROFILE
from .hardware_detector import detect_gpu, get_gpu_profile, is_tensorrt_available
from .engine_builder import build_engine

logger = logging.getLogger(__name__)


def optimize_for_tensorrt(
    onnx_path: str | Path,
    output_dir: Optional[str | Path] = None,
    profile_name: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    if not is_tensorrt_available():
        raise ImportError(
            "TensorRT is not available. "
            "Install TensorRT for your platform."
        )
    
    onnx_path = Path(onnx_path)
    
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")
    
    gpu_info = detect_gpu()
    detected_profile = get_gpu_profile(gpu_info)
    
    profile_name = profile_name or detected_profile
    
    if profile_name not in PROFILES:
        logger.warning(f"Unknown profile '{profile_name}', using detected")
        profile_name = detected_profile
    
    profile = PROFILES[profile_name]
    
    if verbose:
        logger.info(f"Detected GPU info: {gpu_info}")
        logger.info(f"Using profile: {profile_name}")
        logger.info(f"Profile config: precision={profile.precision}, "
                   f"workspace={profile.workspace/(1024*1024):.0f}MB")
    
    if output_dir is None:
        output_dir = onnx_path.parent / "tensorrt" / profile_name
    else:
        output_dir = Path(output_dir) / profile_name
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    engine_name = onnx_path.stem + ".engine"
    engine_path = output_dir / engine_name
    
    try:
        result_path = build_engine(onnx_path, engine_path, profile, verbose)
        
        return {
            "engine_path": result_path,
            "profile": profile_name,
            "precision": profile.precision,
            "workspace_mb": profile.workspace // (1024 * 1024),
            "success": True,
        }
        
    except Exception as e:
        logger.error(f"Failed to build engine: {e}")
        return {
            "engine_path": None,
            "profile": profile_name,
            "error": str(e),
            "success": False,
        }


def get_available_profiles() -> list[str]:
    return list(PROFILES.keys())


def get_recommended_profile() -> str:
    return get_gpu_profile()
