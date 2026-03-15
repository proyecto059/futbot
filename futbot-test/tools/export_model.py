"""
Export YOLO model for RPi3 deployment using the futbot_vision_model pipeline.

Usage:
    python tools/export_model.py --weights best.pt [--output .] [--imgsz 320] [--bench]

Delegates to futbot_vision_model with the cpu_arm_rpi profile:
  - ONNX graph optimization (opt_level=2)
  - INT8 dynamic quantization (no calibration data needed)

Produces a deploy-ready model.onnx to transfer to RPi3.
"""
import sys
import argparse
import numpy as np
from pathlib import Path

# Allow import from sibling repo without installing
_VISION_MODEL_PATH = Path(__file__).parents[2] / "futbot-1v1-2v2/App/python"
sys.path.insert(0, str(_VISION_MODEL_PATH))


def run_export(weights: str, output_dir: Path, imgsz: int) -> Path:
    from futbot_vision_model.src.ai.export import export_model
    results = export_model(
        weights_path=Path(weights).resolve(),
        output_dir=output_dir,
        target="onnx",
        optimize=True,
        profile_name="cpu_arm_rpi",
        verbose=True,
        imgsz=imgsz,
    )
    opt = results.get("onnx_optimized", {})
    if isinstance(opt, dict) and "quantized" in opt:
        return opt["quantized"]
    if isinstance(opt, dict) and "base" in opt:
        return opt["base"]
    return results["onnx"]


def benchmark(model_path: Path, imgsz: int = 320, runs: int = 50):
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
    parser = argparse.ArgumentParser(description="Export YOLO model for RPi3 deployment")
    parser.add_argument("--weights", default="best.pt", help="Input YOLO .pt file")
    parser.add_argument("--output", default=".", help="Output directory")
    parser.add_argument("--imgsz", type=int, default=320, help="Input image size (recommended: 320)")
    parser.add_argument("--bench", action="store_true", help="Run benchmark after export")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Export for RPi3 (cpu_arm_rpi + INT8) ===")
    print(f"  Weights: {args.weights}  imgsz: {args.imgsz}x{args.imgsz}\n")

    model_path = run_export(args.weights, out_dir, args.imgsz)
    print(f"\n✓ Deploy-ready: {model_path}")
    print(f"  Transfer: scp {model_path} pi@<RPi3-IP>:~/futbot-test/model.onnx")

    if args.bench:
        print("\n--- Benchmark ---")
        benchmark(model_path, args.imgsz)


if __name__ == "__main__":
    main()
