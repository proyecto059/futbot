#!/usr/bin/env python3
"""
FutBot Vision Model CLI
Training, export and optimization for YOLO26 models
"""

import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def cmd_train(args):
    from src.ai import train_model, train_quick, train_production
    
    if args.quick:
        weights = train_quick(
            data_config=args.data,
            epochs=args.epochs,
        )
    elif args.production:
        weights = train_production(
            data_config=args.data,
            epochs=args.epochs,
        )
    else:
        weights = train_model(
            data_config=args.data,
            model=args.model,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
        )
    
    logger.info(f"Training complete: {weights}")


def cmd_export(args):
    from src.ai import export_model, export_for_jetson_nano, export_for_jetson_orin, export_for_desktop
    
    if args.target == "jetson_nano":
        result = export_for_jetson_nano(args.weights, args.output)
    elif args.target == "jetson_orin":
        result = export_for_jetson_orin(args.weights, args.output)
    elif args.target == "desktop":
        result = export_for_desktop(args.weights, args.output)
    else:
        result = export_model(
            weights_path=args.weights,
            output_dir=args.output,
            target=args.format,
            optimize=not args.no_optimize,
            profile_name=args.profile,
        )
    
    logger.info(f"Export result: {result}")


def cmd_infer(args):
    from src.ai import run_inference, benchmark_model
    
    if args.benchmark:
        result = benchmark_model(
            model_path=args.model,
            warmup=args.warmup,
            iterations=args.iterations,
            backend=args.backend,
        )
        logger.info(f"Benchmark: {result['mean_ms']:.2f}ms ({result['fps']:.1f} FPS)")
    else:
        result = run_inference(
            model_path=args.model,
            source=args.source,
            output_dir=args.output,
            conf=args.conf,
            backend=args.backend,
        )
        logger.info(f"Inference complete: {result.get('model_path')}")


def cmd_capture(args):
    from src.ai import capture_images, capture_video
    
    if args.video:
        path = capture_video(
            output_path=args.output,
            camera_id=args.camera,
            duration=args.duration,
        )
    else:
        paths = capture_images(
            output_dir=args.output,
            camera_id=args.camera,
            interval=args.interval,
            max_images=args.max_images,
        )
        logger.info(f"Captured {len(paths)} images")


def cmd_augment(args):
    from src.ai import augment_dataset, augment_with_labels
    
    if args.labels_dir:
        result = augment_with_labels(
            images_dir=args.input,
            labels_dir=args.labels_dir,
            output_images_dir=args.output,
            augmentations=args.count,
        )
        logger.info(f"Augmented {len(result['images'])} images, {len(result['labels'])} labels")
    else:
        paths = augment_dataset(
            input_dir=args.input,
            output_dir=args.output,
            augmentations=args.count,
        )
        logger.info(f"Augmented {len(paths)} images")


def cmd_detect(args):
    if args.target == "onnx":
        from onnx_optimizer import detect_hardware, get_hardware_profile
        info = detect_hardware()
        profile = get_hardware_profile(info)
        logger.info(f"Hardware: {info}")
        logger.info(f"Recommended ONNX profile: {profile}")
    elif args.target == "tensorrt":
        from tensorrt_optimizer import detect_gpu, get_gpu_profile
        info = detect_gpu()
        profile = get_gpu_profile(info)
        logger.info(f"GPU: {info}")
        logger.info(f"Recommended TensorRT profile: {profile}")


def cmd_detect_goals(args):
    import cv2
    from src.ai.goal_detector import GoalDetector, GoalDetectorConfig
    
    config = GoalDetectorConfig()
    if args.downscale:
        config.downscale = tuple(args.downscale)
    if args.calib_interval:
        config.calib_interval = args.calib_interval
    
    detector = GoalDetector(config)
    
    if args.source.isdigit():
        source = int(args.source)
    else:
        source = args.source
    
    if args.source.isdigit() or args.live:
        cap = cv2.VideoCapture(source if isinstance(source, int) else 0)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            results = detector.detect(frame)
            vis = detector.visualize(frame, results)
            
            cv2.imshow("Goal Detection (HSV)", vis)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
    else:
        frame = cv2.imread(str(source))
        if frame is None:
            logger.error(f"Could not read image: {source}")
            return
        
        results = detector.detect(frame)
        vis = detector.visualize(frame, results)
        
        output_path = args.output or "goals_output.jpg"
        cv2.imwrite(output_path, vis)
        
        logger.info(f"Results: {results}")
        logger.info(f"Output saved to: {output_path}")


def cmd_detect_all(args):
    import cv2
    from src.ai import run_inference_combined
    
    result = run_inference_combined(
        model_path=args.model,
        source=args.source,
        output_dir=args.output,
        conf=args.conf,
        show=args.show,
    )
    
    logger.info(f"Detection results: {result}")


def main():
    parser = argparse.ArgumentParser(
        description="FutBot Vision Model CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Train command
    train_parser = subparsers.add_parser("train", help="Train YOLO26 model")
    train_parser.add_argument("--data", default="configs/futbot.yaml", help="Dataset config")
    train_parser.add_argument("--model", default="yolo26m.pt", help="Base model")
    train_parser.add_argument("--epochs", type=int, default=200)
    train_parser.add_argument("--batch", type=int, default=32)
    train_parser.add_argument("--imgsz", type=int, default=640)
    train_parser.add_argument("--device", default=0)
    train_parser.add_argument("--quick", action="store_true", help="Quick training (yolo26n)")
    train_parser.add_argument("--production", action="store_true", help="Production settings")
    train_parser.set_defaults(func=cmd_train)
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export and optimize model")
    export_parser.add_argument("weights", help="Path to weights file")
    export_parser.add_argument("--output", "-o", help="Output directory")
    export_parser.add_argument("--format", choices=["onnx", "tensorrt", "all"], default="all")
    export_parser.add_argument("--target", choices=["jetson_nano", "jetson_orin", "desktop", "auto"], default="auto")
    export_parser.add_argument("--profile", help="Specific optimization profile")
    export_parser.add_argument("--no-optimize", action="store_true")
    export_parser.set_defaults(func=cmd_export)
    
    # Inference command
    infer_parser = subparsers.add_parser("infer", help="Run inference")
    infer_parser.add_argument("model", help="Model path")
    infer_parser.add_argument("--source", "-s", help="Image/video source")
    infer_parser.add_argument("--output", "-o", help="Output directory")
    infer_parser.add_argument("--conf", type=float, default=0.25)
    infer_parser.add_argument("--backend", choices=["pytorch", "onnx", "tensorrt", "auto"], default="auto")
    infer_parser.add_argument("--benchmark", action="store_true")
    infer_parser.add_argument("--warmup", type=int, default=10)
    infer_parser.add_argument("--iterations", type=int, default=100)
    infer_parser.set_defaults(func=cmd_infer)
    
    # Capture command
    capture_parser = subparsers.add_parser("capture", help="Capture images/video")
    capture_parser.add_argument("--output", "-o", default="dataset/images/raw")
    capture_parser.add_argument("--camera", type=int, default=0)
    capture_parser.add_argument("--video", action="store_true")
    capture_parser.add_argument("--interval", type=float, default=0.5)
    capture_parser.add_argument("--max-images", type=int)
    capture_parser.add_argument("--duration", type=float)
    capture_parser.set_defaults(func=cmd_capture)
    
    # Augment command
    augment_parser = subparsers.add_parser("augment", help="Augment dataset")
    augment_parser.add_argument("input", help="Input images directory")
    augment_parser.add_argument("--output", "-o", help="Output directory")
    augment_parser.add_argument("--labels-dir", help="Labels directory (for YOLO format)")
    augment_parser.add_argument("--count", type=int, default=3, help="Augmentations per image")
    augment_parser.set_defaults(func=cmd_augment)
    
    # Detect hardware command
    detect_parser = subparsers.add_parser("detect", help="Detect hardware capabilities")
    detect_parser.add_argument("target", choices=["onnx", "tensorrt"], help="Detection target")
    detect_parser.set_defaults(func=cmd_detect)
    
    # Detect goals command (HSV only)
    detect_goals_parser = subparsers.add_parser("detect-goals", help="Detect goals using HSV color detection")
    detect_goals_parser.add_argument("--source", "-s", default="0", help="Image path or camera ID")
    detect_goals_parser.add_argument("--output", "-o", help="Output image path")
    detect_goals_parser.add_argument("--downscale", nargs=2, type=int, help="Downscale resolution (width height)")
    detect_goals_parser.add_argument("--calib-interval", type=int, default=30, help="Calibration interval (frames)")
    detect_goals_parser.add_argument("--live", action="store_true", help="Live camera mode")
    detect_goals_parser.set_defaults(func=cmd_detect_goals)
    
    # Detect all command (YOLO + HSV combined)
    detect_all_parser = subparsers.add_parser("detect-all", help="Detect all objects (YOLO + HSV)")
    detect_all_parser.add_argument("model", help="YOLO model path")
    detect_all_parser.add_argument("--source", "-s", required=True, help="Image/video source")
    detect_all_parser.add_argument("--output", "-o", help="Output directory")
    detect_all_parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    detect_all_parser.add_argument("--show", action="store_true", help="Show visualization")
    detect_all_parser.set_defaults(func=cmd_detect_all)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
