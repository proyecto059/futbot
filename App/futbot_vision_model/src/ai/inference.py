from pathlib import Path
from typing import Optional, Literal
import logging

logger = logging.getLogger(__name__)


def resolve_model_path(model_path: str | Path) -> Path:
    model_path = Path(model_path)
    
    if model_path.exists():
        return model_path
    
    alt_paths = [
        Path("runs/detect") / model_path,
        Path("runs/detect/models") / model_path,
        Path("runs/detect/models") / model_path.name,
        Path.cwd() / model_path,
    ]
    
    for alt in alt_paths:
        if alt.exists():
            logger.info(f"Model found at alternative path: {alt}")
            return alt
    
    raise FileNotFoundError(f"Model not found: {model_path}. Searched in: {[str(model_path)] + [str(p) for p in alt_paths]}")


def load_model(
    model_path: str | Path,
    backend: Literal["pytorch", "onnx", "tensorrt"] = "auto",
):
    model_path = resolve_model_path(model_path)
    
    suffix = model_path.suffix.lower()
    
    if backend == "auto":
        if suffix == ".engine":
            backend = "tensorrt"
        elif suffix == ".onnx":
            backend = "onnx"
        else:
            backend = "pytorch"
    
    if backend == "pytorch":
        try:
            from ultralytics import YOLO
            return YOLO(str(model_path))
        except ImportError:
            raise ImportError("ultralytics is required for PyTorch backend")
    
    elif backend == "onnx":
        try:
            import onnxruntime as ort
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            session = ort.InferenceSession(str(model_path), providers=providers)
            return {"session": session, "path": model_path}
        except ImportError:
            raise ImportError("onnxruntime is required for ONNX backend")
    
    elif backend == "tensorrt":
        try:
            import tensorrt as trt
            import pycuda.driver as cuda
            import pycuda.autoinit
            
            logger = trt.Logger(trt.Logger.WARNING)
            
            with open(model_path, "rb") as f:
                runtime = trt.Runtime(logger)
                engine = runtime.deserialize_cuda_engine(f.read())
            
            context = engine.create_execution_context()
            return {
                "engine": engine,
                "context": context,
                "path": model_path,
            }
        except ImportError as e:
            raise ImportError(f"TensorRT dependencies required: {e}")
    
    raise ValueError(f"Unknown backend: {backend}")


def run_inference(
    model_path: str | Path,
    source: str | Path,
    output_dir: Optional[str | Path] = None,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 640,
    save: bool = True,
    show: bool = False,
    backend: Literal["pytorch", "onnx", "tensorrt", "auto"] = "auto",
    verbose: bool = True,
) -> dict:
    model_path = Path(model_path)
    source = Path(source) if isinstance(source, (str, Path)) else source
    
    model = load_model(model_path, backend)
    
    suffix = model_path.suffix.lower()
    
    if suffix in [".pt", ".pth"]:
        results = model(
            source=source,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            save=save,
            show=show,
            verbose=verbose,
        )
        
        return {
            "backend": "pytorch",
            "results": results,
            "model_path": model_path,
        }
    
    elif suffix == ".onnx":
        import cv2
        import numpy as np
        
        session = model["session"]
        
        if isinstance(source, Path):
            image = cv2.imread(str(source))
        else:
            image = source
        
        if image is None:
            raise ValueError(f"Could not load image: {source}")
        
        input_name = session.get_inputs()[0].name
        
        blob = cv2.dnn.blobFromImage(image, 1/255.0, (imgsz, imgsz), swapRB=True)
        
        outputs = session.run(None, {input_name: blob})
        
        return {
            "backend": "onnx",
            "outputs": outputs,
            "model_path": model_path,
        }
    
    elif suffix == ".engine":
        import cv2
        import numpy as np
        
        engine = model["engine"]
        context = model["context"]
        
        if isinstance(source, Path):
            image = cv2.imread(str(source))
        else:
            image = source
        
        if image is None:
            raise ValueError(f"Could not load image: {source}")
        
        blob = cv2.dnn.blobFromImage(image, 1/255.0, (imgsz, imgsz), swapRB=True)
        
        input_name = engine.get_binding_name(0)
        output_name = engine.get_binding_name(1)
        
        return {
            "backend": "tensorrt",
            "model_path": model_path,
            "note": "Full TensorRT inference requires additional setup",
        }
    
    raise ValueError(f"Unsupported model format: {suffix}")


def benchmark_model(
    model_path: str | Path,
    warmup: int = 10,
    iterations: int = 100,
    imgsz: int = 640,
    backend: Literal["pytorch", "onnx", "tensorrt", "auto"] = "auto",
) -> dict:
    import time
    import numpy as np
    
    model_path = Path(model_path)
    model = load_model(model_path, backend)
    
    dummy_input = np.random.randn(1, 3, imgsz, imgsz).astype(np.float32)
    
    suffix = model_path.suffix.lower()
    
    if suffix in [".pt", ".pth"]:
        for _ in range(warmup):
            model(dummy_input, verbose=False)
        
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            model(dummy_input, verbose=False)
            times.append(time.perf_counter() - start)
    
    elif suffix == ".onnx":
        session = model["session"]
        input_name = session.get_inputs()[0].name
        
        for _ in range(warmup):
            session.run(None, {input_name: dummy_input})
        
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            session.run(None, {input_name: dummy_input})
            times.append(time.perf_counter() - start)
    
    elif suffix == ".engine":
        return {
            "backend": "tensorrt",
            "model_path": model_path,
            "note": "TensorRT benchmark requires additional setup",
        }
    
    times = np.array(times)
    
    return {
        "backend": backend,
        "model_path": model_path,
        "warmup": warmup,
        "iterations": iterations,
        "mean_ms": float(np.mean(times) * 1000),
        "std_ms": float(np.std(times) * 1000),
        "min_ms": float(np.min(times) * 1000),
        "max_ms": float(np.max(times) * 1000),
        "fps": float(1.0 / np.mean(times)),
    }


def run_inference_combined(
    model_path: str | Path,
    source: str | Path,
    output_dir: Optional[str | Path] = None,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 640,
    save: bool = True,
    show: bool = False,
    backend: Literal["pytorch", "onnx", "tensorrt", "auto"] = "auto",
    verbose: bool = True,
) -> dict:
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python is required for combined inference")
    
    from .goal_detector import GoalDetector
    
    model_path = resolve_model_path(model_path)
    source = Path(source) if isinstance(source, (str, Path)) else source
    
    goal_detector = GoalDetector()
    
    yolo_results = run_inference(
        model_path=model_path,
        source=source,
        output_dir=output_dir,
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        save=save,
        show=show,
        backend=backend,
        verbose=verbose,
    )
    
    if isinstance(source, Path):
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Could not load image: {source}")
    else:
        image = source
    
    goal_results = goal_detector.detect(image)
    
    if save and output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        vis_frame = image.copy()
        
        yolo_color = (0, 255, 0)
        for det in yolo_results.get("results", []):
            if hasattr(det, 'boxes'):
                for box in det.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cls = int(box.cls[0])
                    cv2.rectangle(vis_frame, (x1, y1), (x2, y2), yolo_color, 2)
        
        vis_frame = goal_detector.visualize(vis_frame, goal_results)
        
        output_path = output_dir / f"combined_{source.name}" if isinstance(source, Path) else output_dir / "combined_output.jpg"
        cv2.imwrite(str(output_path), vis_frame)
        
        if verbose:
            logger.info(f"Combined visualization saved: {output_path}")
    
    combined_results = {
        "model_path": model_path,
        "source": str(source),
        "yolo": {
            "ball": [],
            "robot": [],
        },
        "hsv": goal_results,
    }
    
    if hasattr(yolo_results.get("results", [None])[0], 'boxes'):
        for det in yolo_results.get("results", []):
            for box in det.boxes:
                cls = int(box.cls[0])
                conf_val = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detection = {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf_val,
                }
                if cls == 0:
                    combined_results["yolo"]["ball"].append(detection)
                elif cls == 1:
                    combined_results["yolo"]["robot"].append(detection)
    
    if verbose:
        logger.info(f"YOLO detections: {len(combined_results['yolo']['ball'])} balls, {len(combined_results['yolo']['robot'])} robots")
        logger.info(f"HSV detections: {len(goal_results['goal_yellow'])} yellow goals, {len(goal_results['goal_blue'])} blue goals")
    
    return combined_results

