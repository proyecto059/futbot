"""
Export pipeline: YOLO26n.pt → ONNX FP32 → simplified → INT8 dynamic

Usage:
    python tools/export_model.py --model yolo26n.pt --out model.onnx [--imgsz 320] [--bench]

Produces:
    yolo26n_fp32.onnx   — FP32 simplified (for debug/comparison)
    model.onnx          — INT8 dynamic quantized, deploy on RPi3

Pipeline:
    1. Export YOLO26n.pt → ONNX FP32 (imgsz=320, no NMS, opset=17)
    2. Simplify with onnxsim (removes redundant nodes, fuses constants)
    3. Dynamic INT8 quantization (no calibration dataset needed)
    4. Verify both models with dummy inference
    5. Optional benchmark
"""
import argparse
import shutil
import numpy as np
from pathlib import Path


def export_fp32(model_path: str, output_dir: Path, imgsz: int = 320) -> Path:
    """Export YOLO26n.pt → ONNX FP32 with reduced imgsz."""
    from ultralytics import YOLO
    model = YOLO(model_path)
    exported = model.export(
        format="onnx",
        imgsz=imgsz,
        simplify=False,   # manual simplification step after
        dynamic=False,    # fixed shape for better RPi3 optimization
        opset=17,
    )
    fp32_path = output_dir / "yolo26n_fp32_raw.onnx"
    shutil.copy(exported, fp32_path)
    print(f"[export] FP32 raw: {fp32_path} ({fp32_path.stat().st_size / 1024:.1f} KB)")
    return fp32_path


def simplify_onnx(input_path: Path, output_path: Path) -> Path:
    """Simplify ONNX graph with onnxsim (removes constant nodes, fuses ops)."""
    import onnx
    from onnxsim import simplify
    model = onnx.load(str(input_path))
    model_simplified, check = simplify(model)
    assert check, "onnxsim simplification failed — verify the model"
    onnx.save(model_simplified, str(output_path))
    print(f"[simplify] → {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def quantize_int8_dynamic(input_path: Path, output_path: Path) -> Path:
    """
    INT8 dynamic quantization: quantizes weights to INT8, no calibration needed.
    Activations quantized at runtime → best for deployment without calibration data.
    """
    from onnxruntime.quantization import quantize_dynamic, QuantType
    quantize_dynamic(
        model_input=str(input_path),
        model_output=str(output_path),
        weight_type=QuantType.QInt8,
        optimize_model=True,   # applies ORT graph optimizations before quantizing
    )
    print(f"[int8] → {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def verify_model(model_path: Path, imgsz: int = 320):
    """Smoke test: dummy inference, verify output shape."""
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=opts)
    input_name = session.get_inputs()[0].name
    dummy = np.zeros((1, 3, imgsz, imgsz), dtype=np.float32)
    outputs = session.run(None, {input_name: dummy})
    print(f"[verify] {model_path.name} — output shapes: {[o.shape for o in outputs]}")
    return outputs


def benchmark(model_path: Path, imgsz: int = 320, runs: int = 50):
    """Measure average inference latency."""
    import time
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=opts)
    input_name = session.get_inputs()[0].name
    dummy = np.zeros((1, 3, imgsz, imgsz), dtype=np.float32)
    for _ in range(5):
        session.run(None, {input_name: dummy})
    t0 = time.perf_counter()
    for _ in range(runs):
        session.run(None, {input_name: dummy})
    avg_ms = (time.perf_counter() - t0) / runs * 1000
    print(f"[bench] {model_path.name}: {avg_ms:.1f}ms avg ({1000/avg_ms:.1f} FPS) over {runs} runs")


def main():
    parser = argparse.ArgumentParser(description="Export YOLO26n to ONNX INT8 for RPi3 deployment")
    parser.add_argument("--model", default="yolo26n.pt", help="Input YOLO26n .pt file")
    parser.add_argument("--out", default="model.onnx", help="Output INT8 model path")
    parser.add_argument("--imgsz", type=int, default=320, help="Input image size (recommended: 320)")
    parser.add_argument("--bench", action="store_true", help="Run benchmark after export")
    args = parser.parse_args()

    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== YOLO26n Export Pipeline ===")
    print(f"  Input:  {args.model}")
    print(f"  Output: {args.out}")
    print(f"  imgsz:  {args.imgsz}x{args.imgsz}")
    print()

    fp32_raw = export_fp32(args.model, out_dir, imgsz=args.imgsz)

    fp32_sim = out_dir / "yolo26n_fp32.onnx"
    simplify_onnx(fp32_raw, fp32_sim)
    fp32_raw.unlink()

    int8_path = Path(args.out)
    quantize_int8_dynamic(fp32_sim, int8_path)

    print("\n--- Verification ---")
    verify_model(fp32_sim, args.imgsz)
    verify_model(int8_path, args.imgsz)

    if args.bench:
        print("\n--- Benchmark ---")
        benchmark(fp32_sim, args.imgsz)
        benchmark(int8_path, args.imgsz)

    print(f"\n✓ Deploy-ready: {int8_path}")
    print(f"  Transfer to RPi3: scp {int8_path} pi@<RPi3-IP>:~/futbot-test/model.onnx")


if __name__ == "__main__":
    main()
