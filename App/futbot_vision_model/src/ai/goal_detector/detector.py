import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from .config import GoalDetectorConfig, DEFAULT_CONFIG
from .tracking import CentroidTracker

logger = logging.getLogger(__name__)


class GoalDetector:
    def __init__(self, config: Optional[GoalDetectorConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.frame_count = 0
        
        self.ema_yellow_lower = self.config.yellow_hsv_lower.astype(np.float32)
        self.ema_yellow_upper = self.config.yellow_hsv_upper.astype(np.float32)
        self.ema_blue_lower = self.config.blue_hsv_lower.astype(np.float32)
        self.ema_blue_upper = self.config.blue_hsv_upper.astype(np.float32)
        
        self.yellow_tracker = CentroidTracker(max_disappeared=self.config.max_disappeared)
        self.blue_tracker = CentroidTracker(max_disappeared=self.config.max_disappeared)
        
        self.morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, self.config.morph_kernel
        )
        
        self.clahe = cv2.createCLAHE(
            clipLimit=self.config.clahe_clip,
            tileGridSize=self.config.clahe_grid
        )
    
    def detect(self, frame: np.ndarray) -> Dict[str, List[Dict]]:
        self.frame_count += 1
        original_frame = frame.copy()
        
        if self.config.downscale:
            frame = cv2.resize(frame, self.config.downscale)
        
        frame = self._normalize_illumination(frame)
        
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        if self.frame_count % self.config.calib_interval == 0:
            self._update_calibration(hsv, frame.shape)
        
        yellow_detections = self._detect_color(
            hsv, 
            self.ema_yellow_lower.astype(np.int32),
            self.ema_yellow_upper.astype(np.int32),
            "goal_yellow"
        )
        
        blue_detections = self._detect_color(
            hsv,
            self.ema_blue_lower.astype(np.int32),
            self.ema_blue_upper.astype(np.int32),
            "goal_blue"
        )
        
        scale_x = original_frame.shape[1] / frame.shape[1]
        scale_y = original_frame.shape[0] / frame.shape[0]
        
        yellow_tracked = self.yellow_tracker.update(yellow_detections)
        blue_tracked = self.blue_tracker.update(blue_detections)
        
        yellow_results = self._scale_detections(yellow_tracked, scale_x, scale_y)
        blue_results = self._scale_detections(blue_tracked, scale_x, scale_y)
        
        return {
            "goal_yellow": yellow_results,
            "goal_blue": blue_results,
        }
    
    def _normalize_illumination(self, frame: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = self.clahe.apply(l)
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def _update_calibration(self, hsv: np.ndarray, frame_shape: Tuple[int, int, int]):
        h, w = frame_shape[:2]
        
        roi_left = hsv[:, :int(w * self.config.roi_left_ratio)]
        roi_right = hsv[:, int(w * (1 - self.config.roi_right_ratio)):]
        
        self._update_color_range(roi_left, roi_right, "yellow")
        self._update_color_range(roi_left, roi_right, "blue")
    
    def _update_color_range(self, roi_left: np.ndarray, roi_right: np.ndarray, color: str):
        if color == "yellow":
            lower = self.config.yellow_hsv_lower
            upper = self.config.yellow_hsv_upper
        else:
            lower = self.config.blue_hsv_lower
            upper = self.config.blue_hsv_upper
        
        for roi in [roi_left, roi_right]:
            mask = cv2.inRange(roi, lower, upper)
            if np.sum(mask) > 100:
                pixels = roi[mask > 0]
                if len(pixels) > 10:
                    mean_hsv = np.mean(pixels, axis=0)
                    
                    if color == "yellow":
                        new_lower = np.array([
                            max(0, mean_hsv[0] - 15),
                            max(50, mean_hsv[1] - 50),
                            max(50, mean_hsv[2] - 50)
                        ])
                        new_upper = np.array([
                            min(180, mean_hsv[0] + 15),
                            255,
                            255
                        ])
                        self.ema_yellow_lower = (
                            self.config.ema_alpha * new_lower +
                            (1 - self.config.ema_alpha) * self.ema_yellow_lower
                        )
                        self.ema_yellow_upper = (
                            self.config.ema_alpha * new_upper +
                            (1 - self.config.ema_alpha) * self.ema_yellow_upper
                        )
                    else:
                        new_lower = np.array([
                            max(0, mean_hsv[0] - 15),
                            max(50, mean_hsv[1] - 50),
                            max(30, mean_hsv[2] - 30)
                        ])
                        new_upper = np.array([
                            min(180, mean_hsv[0] + 15),
                            255,
                            255
                        ])
                        self.ema_blue_lower = (
                            self.config.ema_alpha * new_lower +
                            (1 - self.config.ema_alpha) * self.ema_blue_lower
                        )
                        self.ema_blue_upper = (
                            self.config.ema_alpha * new_upper +
                            (1 - self.config.ema_alpha) * self.ema_blue_upper
                        )
    
    def _detect_color(
        self, 
        hsv: np.ndarray, 
        lower: np.ndarray, 
        upper: np.ndarray,
        label: str
    ) -> List[Dict]:
        mask = cv2.inRange(hsv, lower, upper)
        
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.morph_kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.morph_kernel)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        detections = []
        for contour in contours:
            area = cv2.contourArea(contour)
            
            if area < self.config.min_area or area > self.config.max_area:
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            
            if aspect_ratio < self.config.aspect_ratio_min or aspect_ratio > self.config.aspect_ratio_max:
                if aspect_ratio < 1.0 / self.config.aspect_ratio_max or aspect_ratio > 1.0 / self.config.aspect_ratio_min:
                    pass
            
            detections.append({
                "class": label,
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "area": int(area),
                "aspect_ratio": float(aspect_ratio),
            })
        
        return detections
    
    def _scale_detections(
        self, 
        tracked: Dict[int, Dict], 
        scale_x: float, 
        scale_y: float
    ) -> List[Dict]:
        results = []
        for obj_id, obj in tracked.items():
            det = obj["detection"].copy()
            det["id"] = obj_id
            det["x"] = int(det["x"] * scale_x)
            det["y"] = int(det["y"] * scale_y)
            det["w"] = int(det["w"] * scale_x)
            det["h"] = int(det["h"] * scale_y)
            if "centroid" in obj:
                cx, cy = obj["centroid"]
                det["centroid"] = (int(cx * scale_x), int(cy * scale_y))
            results.append(det)
        return results
    
    def reset(self):
        self.frame_count = 0
        self.ema_yellow_lower = self.config.yellow_hsv_lower.astype(np.float32)
        self.ema_yellow_upper = self.config.yellow_hsv_upper.astype(np.float32)
        self.ema_blue_lower = self.config.blue_hsv_lower.astype(np.float32)
        self.ema_blue_upper = self.config.blue_hsv_upper.astype(np.float32)
        self.yellow_tracker = CentroidTracker(max_disappeared=self.config.max_disappeared)
        self.blue_tracker = CentroidTracker(max_disappeared=self.config.max_disappeared)
    
    def visualize(self, frame: np.ndarray, detections: Dict[str, List[Dict]]) -> np.ndarray:
        vis_frame = frame.copy()
        
        colors = {
            "goal_yellow": (0, 255, 255),
            "goal_blue": (255, 0, 0),
        }
        
        for class_name, dets in detections.items():
            color = colors.get(class_name, (0, 255, 0))
            for det in dets:
                x, y, w, h = det["x"], det["y"], det["w"], det["h"]
                cv2.rectangle(vis_frame, (x, y), (x + w, y + h), color, 2)
                
                label = f"{class_name}"
                if "id" in det:
                    label += f" #{det['id']}"
                
                cv2.putText(
                    vis_frame, label, (x, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                )
        
        return vis_frame
