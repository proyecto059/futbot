from pathlib import Path
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)


def capture_images(
    output_dir: str | Path = "dataset/images/raw",
    camera_id: int = 0,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    interval: float = 0.5,
    max_images: Optional[int] = None,
    prefix: str = "capture",
    format: str = "jpg",
    show_preview: bool = True,
) -> list[Path]:
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python is required for capture")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cap = cv2.VideoCapture(camera_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {camera_id}")
    
    captured_paths = []
    count = 0
    last_capture = 0
    
    logger.info(f"Starting capture to {output_dir}")
    logger.info("Press 'c' to capture, 'q' to quit, 'a' for auto-capture mode")
    
    auto_mode = False
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Failed to read frame")
                continue
            
            current_time = time.time()
            
            if auto_mode and (current_time - last_capture) >= interval:
                if max_images is None or count < max_images:
                    timestamp = int(time.time() * 1000)
                    filename = f"{prefix}_{timestamp}.{format}"
                    filepath = output_dir / filename
                    
                    cv2.imwrite(str(filepath), frame)
                    captured_paths.append(filepath)
                    count += 1
                    last_capture = current_time
                    
                    logger.info(f"Captured {count}: {filename}")
                    
                    if max_images and count >= max_images:
                        logger.info(f"Reached max images: {max_images}")
                        break
            
            if show_preview:
                display = frame.copy()
                status = f"Captured: {count}"
                if auto_mode:
                    status += " [AUTO]"
                cv2.putText(display, status, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.imshow("Capture", display)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('c'):
                if max_images is None or count < max_images:
                    timestamp = int(time.time() * 1000)
                    filename = f"{prefix}_{timestamp}.{format}"
                    filepath = output_dir / filename
                    
                    cv2.imwrite(str(filepath), frame)
                    captured_paths.append(filepath)
                    count += 1
                    
                    logger.info(f"Captured {count}: {filename}")
            elif key == ord('a'):
                auto_mode = not auto_mode
                logger.info(f"Auto mode: {'ON' if auto_mode else 'OFF'}")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
    
    logger.info(f"Capture complete. Total images: {len(captured_paths)}")
    return captured_paths


def capture_video(
    output_path: str | Path = "dataset/videos/capture.mp4",
    camera_id: int = 0,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    duration: Optional[float] = None,
    show_preview: bool = True,
) -> Path:
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python is required for capture")
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    cap = cv2.VideoCapture(camera_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {camera_id}")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    logger.info(f"Recording to {output_path}")
    logger.info("Press 'q' to stop recording")
    
    start_time = time.time()
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            out.write(frame)
            frame_count += 1
            
            if show_preview:
                display = frame.copy()
                elapsed = time.time() - start_time
                cv2.putText(display, f"Time: {elapsed:.1f}s", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.imshow("Recording", display)
            
            if duration and (time.time() - start_time) >= duration:
                break
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    finally:
        cap.release()
        out.release()
        cv2.destroyAllWindows()
    
    logger.info(f"Recording saved: {output_path} ({frame_count} frames)")
    return output_path


def extract_frames_from_video(
    video_path: str | Path,
    output_dir: str | Path = "dataset/images/extracted",
    interval: int = 30,
    prefix: str = "frame",
    format: str = "jpg",
) -> list[Path]:
    try:
        import cv2
    except ImportError:
        raise ImportError("opencv-python is required")
    
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    cap = cv2.VideoCapture(str(video_path))
    
    extracted = []
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % interval == 0:
            filename = f"{prefix}_{frame_idx:06d}.{format}"
            filepath = output_dir / filename
            cv2.imwrite(str(filepath), frame)
            extracted.append(filepath)
        
        frame_idx += 1
    
    cap.release()
    
    logger.info(f"Extracted {len(extracted)} frames to {output_dir}")
    return extracted
