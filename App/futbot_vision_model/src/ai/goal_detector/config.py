from dataclasses import dataclass, field
from typing import Tuple, Optional
import numpy as np


@dataclass
class GoalDetectorConfig:
    downscale: Optional[Tuple[int, int]] = None
    clahe_clip: float = 2.0
    clahe_grid: Tuple[int, int] = (8, 8)
    
    yellow_hsv_lower: np.ndarray = field(default_factory=lambda: np.array([20, 100, 100]))
    yellow_hsv_upper: np.ndarray = field(default_factory=lambda: np.array([40, 255, 255]))
    blue_hsv_lower: np.ndarray = field(default_factory=lambda: np.array([100, 150, 50]))
    blue_hsv_upper: np.ndarray = field(default_factory=lambda: np.array([130, 255, 255]))
    
    min_area: int = 500
    max_area: int = 50000
    aspect_ratio_min: float = 2.0
    aspect_ratio_max: float = 6.0
    
    calib_interval: int = 30
    ema_alpha: float = 0.1
    
    morph_kernel: Tuple[int, int] = (5, 5)
    
    max_disappeared: int = 30
    
    roi_left_ratio: float = 0.15
    roi_right_ratio: float = 0.15
    
    def __post_init__(self):
        self.yellow_hsv_lower = np.array(self.yellow_hsv_lower)
        self.yellow_hsv_upper = np.array(self.yellow_hsv_upper)
        self.blue_hsv_lower = np.array(self.blue_hsv_lower)
        self.blue_hsv_upper = np.array(self.blue_hsv_upper)


DEFAULT_CONFIG = GoalDetectorConfig()
