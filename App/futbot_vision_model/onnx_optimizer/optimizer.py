from pathlib import Path
from typing import Optional
import logging

from .config import PROFILES, OnnxProfile
from .hardware_detector import detect_hardware, get_hardware_profile
from .quantizer import quantize_model, is_quantization_supported

logger = logging.getLogger(__name__)

try:
    import onnx
    from onnx import optimizer as onnx_optimizer
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False


def optimize_onnx_graph(
    input_path: Path,
    output_path: Path,
    opt_level: int = 3,
) -> Path:
    if not ONNX_AVAILABLE:
        logger.warning("onnx package not available, skipping graph optimization")
        return input_path
    
    model = onnx.load(str(input_path))
    
    passes = [
        "eliminate_identity",
        "eliminate_nop_transpose",
        "fuse_bn_into_conv",
        "fuse_consecutive_transposes",
    ]
    
    if opt_level >= 2:
        passes.extend([
            "eliminate_unused_initializer",
            "fuse_add_bias_into_conv",
        ])
    
    if opt_level >= 3:
        passes.extend([
            "fuse_consecutive_squeezes",
            "fuse_consecutive_reduces",
            "fuse_transpose_into_gemm",
        ])
    
    optimized = onnx_optimizer.optimize(model, passes)
    onnx.save(optimized, str(output_path))
    
    return output_path


def optimize_for_onnx(
    model_path: str | Path,
    output_dir: Optional[str | Path] = None,
    profile_name: Optional[str] = None,
    verbose: bool = False,
) -> dict[str, Path]:
    model_path = Path(model_path)
    
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    hardware_info = detect_hardware()
    detected_profile = get_hardware_profile(hardware_info)
    profile_name = profile_name or detected_profile
    
    if profile_name not in PROFILES:
        logger.warning(
            f"Unknown profile '{profile_name}', using default"
        )
        profile_name = detected_profile
    
    profile = PROFILES[profile_name]
    
    if verbose:
        logger.info(f"Detected hardware: {hardware_info}")
        logger.info(f"Using profile: {profile_name}")
        logger.info(f"Profile config: {profile}")
    
    if output_dir is None:
        base_name = model_path.stem
        output_dir = model_path.parent / f"{base_name}_optimized" / profile_name
    else:
        output_dir = Path(output_dir) / profile_name
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    optimized_path = output_dir / model_path.name
    optimize_onnx_graph(model_path, optimized_path, profile.opt_level)
    results["base"] = optimized_path
    
    if profile.quantize and is_quantization_supported():
        quant_type = profile.quantize.replace("dynamic_", "")
        quantized_path = output_dir / f"{model_path.stem}_{quant_type}.onnx"
        
        try:
            quantize_model(optimized_path, quantized_path, quant_type)
            results["quantized"] = quantized_path
            if verbose:
                logger.info(f"Quantized model saved: {quantized_path}")
        except Exception as e:
            logger.warning(f"Quantization failed: {e}")
    
    results["profile"] = profile_name
    results["profile_config"] = profile
    
    if verbose:
        logger.info(f"Optimization complete. Outputs: {list(results.keys())}")
    
    return results


def get_available_profiles() -> list[str]:
    return list(PROFILES.keys())
