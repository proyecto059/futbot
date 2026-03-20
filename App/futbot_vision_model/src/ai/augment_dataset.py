from pathlib import Path
from typing import Optional
import logging
import random

logger = logging.getLogger(__name__)


def augment_dataset(
    input_dir: str | Path = "dataset/images/train",
    output_dir: Optional[str | Path] = None,
    augmentations: int = 3,
    hsv_h: float = 0.02,
    hsv_s: float = 0.8,
    hsv_v: float = 0.5,
    degrees: float = 15.0,
    flipud: float = 0.5,
    fliplr: float = 0.5,
    scale: float = 0.5,
    shear: float = 0.0,
    perspective: float = 0.0,
    mosaic: bool = False,
    mixup: bool = False,
    copy_paste: bool = False,
    verbose: bool = True,
) -> list[Path]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise ImportError("opencv-python and numpy are required")
    
    input_dir = Path(input_dir)
    
    if output_dir is None:
        output_dir = input_dir.parent / f"{input_dir.name}_augmented"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    images = [f for f in input_dir.iterdir() 
              if f.suffix.lower() in image_extensions]
    
    if not images:
        raise ValueError(f"No images found in {input_dir}")
    
    augmented_paths = []
    
    if verbose:
        logger.info(f"Found {len(images)} images")
        logger.info(f"Generating {augmentations} augmentations per image")
    
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning(f"Could not load: {img_path}")
            continue
        
        for i in range(augmentations):
            aug_img = img.copy()
            
            if random.random() < flipud:
                aug_img = cv2.flip(aug_img, 0)
            
            if random.random() < fliplr:
                aug_img = cv2.flip(aug_img, 1)
            
            if degrees > 0:
                angle = random.uniform(-degrees, degrees)
                h, w = aug_img.shape[:2]
                matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
                aug_img = cv2.warpAffine(aug_img, matrix, (w, h))
            
            if hsv_h > 0 or hsv_s > 0 or hsv_v > 0:
                hsv = cv2.cvtColor(aug_img, cv2.COLOR_BGR2HSV).astype(np.float32)
                
                if hsv_h > 0:
                    hsv[:,:,0] += random.uniform(-hsv_h * 180, hsv_h * 180)
                if hsv_s > 0:
                    hsv[:,:,1] *= random.uniform(1 - hsv_s, 1 + hsv_s)
                if hsv_v > 0:
                    hsv[:,:,2] *= random.uniform(1 - hsv_v, 1 + hsv_v)
                
                hsv = np.clip(hsv, 0, 255).astype(np.uint8)
                aug_img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            
            if scale > 0:
                scale_factor = random.uniform(1 - scale, 1 + scale)
                h, w = aug_img.shape[:2]
                new_w, new_h = int(w * scale_factor), int(h * scale_factor)
                aug_img = cv2.resize(aug_img, (new_w, new_h))
                
                if new_w < w or new_h < h:
                    pad_w = (w - new_w) // 2
                    pad_h = (h - new_h) // 2
                    aug_img = cv2.copyMakeBorder(aug_img, pad_h, pad_h, pad_w, pad_w,
                                                  cv2.BORDER_CONSTANT, value=(0, 0, 0))
                else:
                    start_x = (new_w - w) // 2
                    start_y = (new_h - h) // 2
                    aug_img = aug_img[start_y:start_y+h, start_x:start_x+w]
            
            output_name = f"{img_path.stem}_aug{i}{img_path.suffix}"
            output_path = output_dir / output_name
            cv2.imwrite(str(output_path), aug_img)
            augmented_paths.append(output_path)
    
    if verbose:
        logger.info(f"Augmented {len(images)} images -> {len(augmented_paths)} total")
    
    return augmented_paths


def augment_with_labels(
    images_dir: str | Path = "dataset/images/train",
    labels_dir: str | Path = "dataset/labels/train",
    output_images_dir: Optional[str | Path] = None,
    output_labels_dir: Optional[str | Path] = None,
    augmentations: int = 2,
    **kwargs,
) -> dict:
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    
    if output_images_dir is None:
        output_images_dir = images_dir
    else:
        output_images_dir = Path(output_images_dir)
        output_images_dir.mkdir(parents=True, exist_ok=True)
    
    if output_labels_dir is None:
        output_labels_dir = labels_dir
    else:
        output_labels_dir = Path(output_labels_dir)
        output_labels_dir.mkdir(parents=True, exist_ok=True)
    
    augmented_images = augment_dataset(
        input_dir=images_dir,
        output_dir=output_images_dir,
        augmentations=augmentations,
        **kwargs,
    )
    
    label_files = list(labels_dir.glob("*.txt"))
    copied_labels = []
    
    for label_path in label_files:
        for i in range(augmentations):
            new_label_name = f"{label_path.stem}_aug{i}{label_path.suffix}"
            new_label_path = output_labels_dir / new_label_name
            
            import shutil
            shutil.copy(str(label_path), str(new_label_path))
            copied_labels.append(new_label_path)
    
    logger.info(f"Copied {len(copied_labels)} label files")
    
    return {
        "images": augmented_images,
        "labels": copied_labels,
    }


def create_mosaic(
    images_dir: str | Path,
    output_dir: str | Path,
    mosaic_size: int = 4,
    count: int = 10,
    imgsz: int = 640,
) -> list[Path]:
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise ImportError("opencv-python and numpy are required")
    
    images_dir = Path(images_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    image_extensions = {".jpg", ".jpeg", ".png"}
    images = [f for f in images_dir.iterdir() 
              if f.suffix.lower() in image_extensions]
    
    if len(images) < mosaic_size:
        raise ValueError(f"Need at least {mosaic_size} images for mosaic")
    
    mosaics = []
    
    for i in range(count):
        selected = random.sample(images, mosaic_size)
        
        mosaic = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
        
        positions = [
            (0, 0),
            (imgsz // 2, 0),
            (0, imgsz // 2),
            (imgsz // 2, imgsz // 2),
        ]
        
        for img_path, (x, y) in zip(selected, positions):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            
            half_size = imgsz // 2
            img = cv2.resize(img, (half_size, half_size))
            mosaic[y:y+half_size, x:x+half_size] = img
        
        output_path = output_dir / f"mosaic_{i:04d}.jpg"
        cv2.imwrite(str(output_path), mosaic)
        mosaics.append(output_path)
    
    logger.info(f"Created {len(mosaics)} mosaics")
    return mosaics
