from pathlib import Path
from typing import Optional
import logging
import tempfile
import shutil

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent  # futbot_vision_model/
DATASET_DIR = PROJECT_ROOT / "dataset"
CONFIGS_DIR = PROJECT_ROOT / "configs"


def resolve_data_config(data_config: str | Path) -> Path:
    data_config = Path(data_config)
    
    if not data_config.exists():
        alt_path = Path.cwd() / data_config
        if alt_path.exists():
            data_config = alt_path
        else:
            raise FileNotFoundError(f"Data config not found: {data_config}")
    
    with open(data_config, "r") as f:
        content = f.read()
    
    content = content.replace("path: ../dataset", f"path: {DATASET_DIR}")
    
    temp_config = Path(tempfile.mktemp(suffix=".yaml"))
    with open(temp_config, "w") as f:
        f.write(content)
    
    return temp_config


def train_model(
    data_config: str | Path = "configs/futbot.yaml",
    model: str = "yolo26m.pt",
    epochs: int = 200,
    imgsz: int = 640,
    batch: int = 32,
    device: str | int = 0,
    project: str = "models",
    name: str = "yolo26m_futbot",
    hsv_h: float = 0.02,
    hsv_s: float = 0.8,
    hsv_v: float = 0.5,
    degrees: float = 15.0,
    flipud: float = 0.5,
    fliplr: float = 0.5,
    mosaic: float = 1.0,
    mixup: float = 0.2,
    copy_paste: float = 0.0,
    patience: int = 50,
    save_period: int = 10,
    verbose: bool = True,
    **kwargs,
) -> Path:
    try:
        from ultralytics import YOLO
    except ImportError:
        raise ImportError(
            "ultralytics is required. Install with: pip install ultralytics>=8.4.0"
        )
    
    resolved_config = resolve_data_config(data_config)
    
    output_dir = Path(project) / name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if verbose:
        logger.info(f"Starting training with {model}")
        logger.info(f"Data config: {data_config}")
        logger.info(f"Output: {output_dir}")
        logger.info(f"Epochs: {epochs}, Batch: {batch}, Image size: {imgsz}")
    
    yolo = YOLO(model)
    
    try:
        results = yolo.train(
            data=str(resolved_config),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            project=project,
            name=name,
            hsv_h=hsv_h,
            hsv_s=hsv_s,
            hsv_v=hsv_v,
            degrees=degrees,
            flipud=flipud,
            fliplr=fliplr,
            mosaic=mosaic,
            mixup=mixup,
            copy_paste=copy_paste,
            patience=patience,
            save_period=save_period,
            exist_ok=True,
            **kwargs,
        )
    finally:
        if resolved_config.exists():
            resolved_config.unlink()
    
    best_weights = output_dir / "weights" / "best.pt"
    
    if verbose:
        logger.info(f"Training complete. Best weights: {best_weights}")
    
    return best_weights


def train_quick(
    data_config: str | Path = "configs/futbot.yaml",
    epochs: int = 50,
    **kwargs,
) -> Path:
    return train_model(
        data_config=data_config,
        model="yolo26n.pt",
        epochs=epochs,
        batch=16,
        **kwargs,
    )


def train_production(
    data_config: str | Path = "configs/futbot.yaml",
    epochs: int = 200,
    batch: int = 4,
    imgsz: int = 640,
    **kwargs,
) -> Path:
    return train_model(
        data_config=data_config,
        model="yolo26m.pt",
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        hsv_h=0.02,
        hsv_s=0.8,
        hsv_v=0.5,
        degrees=15.0,
        flipud=0.5,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.2,
        patience=50,
        **kwargs,
    )
