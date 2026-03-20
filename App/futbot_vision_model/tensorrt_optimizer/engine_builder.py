import logging
from pathlib import Path
from typing import Optional

from .config import PROFILES, TensorRTProfile
from .hardware_detector import is_tensorrt_available

logger = logging.getLogger(__name__)


def build_engine(
    onnx_path: Path,
    output_path: Path,
    profile: TensorRTProfile,
    verbose: bool = False,
) -> Path:
    if not is_tensorrt_available():
        raise ImportError(
            "TensorRT is not available. "
            "Install TensorRT for your platform."
        )
    
    import tensorrt as trt
    
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger_level = trt.Logger.VERBOSE if verbose else trt.Logger.WARNING
    trt_logger = trt.Logger(logger_level)
    
    builder = trt.Builder(trt_logger)
    network = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )
    parser = trt.OnnxParser(network, trt_logger)
    
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            errors = []
            for i in range(parser.num_errors):
                errors.append(str(parser.get_error(i)))
            raise RuntimeError(f"Failed to parse ONNX: {errors}")
    
    config = builder.create_builder_config()
    
    config.set_memory_pool_limit(
        trt.MemoryPoolType.WORKSPACE,
        profile.workspace
    )
    
    if profile.precision == "fp16":
        if builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
            logger.info("FP16 precision enabled")
        else:
            logger.warning("FP16 not supported, falling back to FP32")
    
    if profile.max_batch > 1:
        profile_obj = builder.create_optimization_profile()
        profile_obj.set_shape(
            "images",
            min=profile.min_shape,
            opt=profile.opt_shape,
            max=profile.max_shape,
        )
        config.add_optimization_profile(profile_obj)
    
    if profile.dla_enable:
        try:
            dla_core = 0
            config.set_flag(trt.BuilderFlag.INT8)
            config.default_device_type = trt.DeviceType.DLA
            config.DLA_core = dla_core
            config.set_flag(trt.BuilderFlag.STRICT_TYPES)
            logger.info(f"DLA core {dla_core} enabled")
        except Exception as e:
            logger.warning(f"DLA not available: {e}")
    
    logger.info(f"Building TensorRT engine for {profile.name}...")
    logger.info(f"Workspace: {profile.workspace / (1024*1024):.0f} MB")
    logger.info(f"Precision: {profile.precision}")
    
    serialized_engine = builder.build_serialized_network(network, config)
    
    if serialized_engine is None:
        raise RuntimeError("Failed to build TensorRT engine")
    
    with open(output_path, "wb") as f:
        f.write(serialized_engine)
    
    logger.info(f"Engine saved to: {output_path}")
    
    return output_path


def build_engine_cli(
    onnx_path: str,
    output_path: str,
    precision: str = "fp16",
    workspace_mb: int = 512,
    max_batch: int = 1,
) -> str:
    onnx_path = Path(onnx_path)
    output_path = Path(output_path)
    
    profile = TensorRTProfile(
        name="custom",
        precision=precision,
        workspace=workspace_mb * 1024 * 1024,
        max_batch=max_batch,
        dla_enable=False,
        description="Custom profile",
    )
    
    result = build_engine(onnx_path, output_path, profile, verbose=True)
    return str(result)
