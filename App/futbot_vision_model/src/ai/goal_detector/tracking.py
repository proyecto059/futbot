from collections import OrderedDict
from typing import Dict, List, Tuple, Optional
import numpy as np
import math


class CentroidTracker:
    def __init__(self, max_disappeared: int = 30):
        self.next_object_id = 0
        self.objects: Dict[int, Dict] = OrderedDict()
        self.disappeared: Dict[int, int] = OrderedDict()
        self.max_disappeared = max_disappeared
    
    def register(self, centroid: Tuple[int, int], detection: Dict):
        self.objects[self.next_object_id] = {
            "centroid": centroid,
            "detection": detection,
        }
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1
    
    def deregister(self, object_id: int):
        del self.objects[object_id]
        del self.disappeared[object_id]
    
    def update(self, detections: List[Dict]) -> Dict[int, Dict]:
        if len(detections) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects
        
        input_centroids = np.zeros((len(detections), 2), dtype="int")
        for i, det in enumerate(detections):
            input_centroids[i] = (det["x"] + det["w"] // 2, det["y"] + det["h"] // 2)
        
        if len(self.objects) == 0:
            for i, det in enumerate(detections):
                self.register(tuple(input_centroids[i]), det)
        else:
            object_ids = list(self.objects.keys())
            object_centroids = np.array([obj["centroid"] for obj in self.objects.values()])
            
            distances = self._compute_distances(object_centroids, input_centroids)
            
            rows, cols = self._hungarian_assignment(distances)
            
            used_rows = set()
            used_cols = set()
            
            for (row, col) in zip(rows, cols):
                if row in used_rows or col in used_cols:
                    continue
                
                if distances[row, col] > 100:
                    continue
                
                object_id = object_ids[row]
                self.objects[object_id]["centroid"] = tuple(input_centroids[col])
                self.objects[object_id]["detection"] = detections[col]
                self.disappeared[object_id] = 0
                
                used_rows.add(row)
                used_cols.add(col)
            
            unused_rows = set(range(0, len(object_centroids))) - used_rows
            unused_cols = set(range(0, len(input_centroids))) - used_cols
            
            for row in unused_rows:
                object_id = object_ids[row]
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            
            for col in unused_cols:
                self.register(tuple(input_centroids[col]), detections[col])
        
        return self.objects
    
    def _compute_distances(self, centroids_a: np.ndarray, centroids_b: np.ndarray) -> np.ndarray:
        distances = np.zeros((len(centroids_a), len(centroids_b)))
        for i, ca in enumerate(centroids_a):
            for j, cb in enumerate(centroids_b):
                distances[i, j] = math.sqrt((ca[0] - cb[0])**2 + (ca[1] - cb[1])**2)
        return distances
    
    def _hungarian_assignment(self, distances: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        try:
            from scipy.optimize import linear_sum_assignment
            return linear_sum_assignment(distances)
        except ImportError:
            rows = np.arange(len(distances))
            cols = np.argmin(distances, axis=1)
            return rows, cols
    
    def get_active_objects(self) -> List[Dict]:
        return [
            {"id": obj_id, **obj["detection"], "centroid": obj["centroid"]}
            for obj_id, obj in self.objects.items()
        ]
