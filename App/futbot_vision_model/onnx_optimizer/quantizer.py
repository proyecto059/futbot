from pathlib import Path
from typing import Optional

try:
    from onnxruntime.quantization import quantize_dynamic, QuantType
    ONNX_RUNTIME_AVAILABLE = True
except ImportError:
    ONNX_RUNTIME_AVAILABLE = False


def quantize_model(
    input_path: str | Path,
    output_path: str | Path,
    quant_type: str = "int8",
) -> Path:
    if not ONNX_RUNTIME_AVAILABLE:
        raise ImportError(
            "onnxruntime is required for quantization. "
            "Install with: pip install onnxruntime"
        )
    
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input model not found: {input_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    quant_type_map = {
        "int8": QuantType.QInt8,
        "uint8": QuantType.QUInt8,
        "qdq": QuantType.QInt8,
    }
    
    op_types_to_quantize = ["MatMul", "Add", "Mul", "Conv"]
    
    if quant_type == "qdq":
        from onnxruntime.quantization import quantize_qat
        quantize_qat(
            model_input=str(input_path),
            model_output=str(output_path),
            op_types_to_quantize=op_types_to_quantize,
        )
    else:
        quantize_dynamic(
            model_input=str(input_path),
            model_output=str(output_path),
            weight_type=quant_type_map.get(quant_type, QuantType.QInt8),
            op_types_to_quantize=op_types_to_quantize,
        )
    
    return output_path


def is_quantization_supported() -> bool:
    return ONNX_RUNTIME_AVAILABLE
