from pathlib import Path
from typing import Optional, Literal
import logging

logger = logging.getLogger(__name__)


def export_to_onnx(
    weights_path: str | Path,
    output_dir: Optional[str | Path] = None,
    simplify: bool = True,
    opset: int = 12,
    imgsz: int = 640,
) -> Path:
    try:
        from ultralytics import YOLO
    except ImportError:
        raise ImportError("ultralytics is required")
    
    weights_path = Path(weights_path)
    if not weights_path.exists():
        raise FileNotFoundError(f"Weights not found: {weights_path}")
    
    if output_dir is None:
        output_dir = weights_path.parent.parent / "onnx"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    model = YOLO(str(weights_path))
    
    onnx_path = model.export(
        format="onnx",
        simplify=simplify,
        opset=opset,
        imgsz=imgsz,
    )
    
    onnx_path = Path(onnx_path)
    
    final_path = output_dir / onnx_path.name
    if onnx_path != final_path:
        import shutil
        shutil.move(str(onnx_path), str(final_path))
    
    logger.info(f"ONNX exported to: {final_path}")
    return final_path


def export_model(
    weights_path: str | Path,
    output_dir: Optional[str | Path] = None,
    target: Literal["onnx", "tensorrt", "all"] = "all",
    optimize: bool = True,
    profile_name: Optional[str] = None,
    verbose: bool = True,
    imgsz: int = 640,
) -> dict:
    weights_path = Path(weights_path)

    if not weights_path.exists():
        raise FileNotFoundError(f"Weights not found: {weights_path}")

    if output_dir is None:
        output_dir = Path("models")
    else:
        output_dir = Path(output_dir)

    results = {
        "weights": weights_path,
        "onnx": None,
        "onnx_optimized": None,
        "tensorrt": None,
    }

    if target in ["onnx", "all"]:
        onnx_base_dir = output_dir / "onnx"
        onnx_path = export_to_onnx(weights_path, onnx_base_dir, imgsz=imgsz)
        results["onnx"] = onnx_path
        
        if optimize:
            try:
                from onnx_optimizer import optimize_for_onnx
                
                opt_results = optimize_for_onnx(
                    onnx_path,
                    output_dir=onnx_base_dir,
                    profile_name=profile_name,
                    verbose=verbose,
                )
                results["onnx_optimized"] = opt_results
                
                if verbose:
                    logger.info(f"ONNX optimized: {opt_results}")
                    
            except ImportError:
                logger.warning("onnx_optimizer not available, skipping ONNX optimization")
    
    if target in ["tensorrt", "all"]:
        onnx_path = results["onnx"]
        if onnx_path is None:
            onnx_path = export_to_onnx(weights_path, output_dir / "onnx")
        
        try:
            from tensorrt_optimizer import optimize_for_tensorrt
            
            trt_results = optimize_for_tensorrt(
                onnx_path,
                output_dir=output_dir / "tensorrt",
                profile_name=profile_name,
                verbose=verbose,
            )
            results["tensorrt"] = trt_results
            
            if verbose:
                if trt_results.get("success"):
                    logger.info(f"TensorRT engine: {trt_results['engine_path']}")
                else:
                    logger.warning(f"TensorRT failed: {trt_results.get('error')}")
                    
        except ImportError:
            logger.warning("tensorrt_optimizer not available, skipping TensorRT")
    
    return results


def export_for_jetson_nano(
    weights_path: str | Path,
    output_dir: Optional[str | Path] = None,
) -> dict:
    return export_model(
        weights_path=weights_path,
        output_dir=output_dir,
        target="all",
        optimize=True,
        profile_name="jetson_nano",
    )


def export_for_jetson_orin(
    weights_path: str | Path,
    output_dir: Optional[str | Path] = None,
) -> dict:
    return export_model(
        weights_path=weights_path,
        output_dir=output_dir,
        target="all",
        optimize=True,
        profile_name="jetson_orin",
    )


def export_for_desktop(
    weights_path: str | Path,
    output_dir: Optional[str | Path] = None,
) -> dict:
    return export_model(
        weights_path=weights_path,
        output_dir=output_dir,
        target="all",
        optimize=True,
        profile_name="desktop_rtx",
    )
