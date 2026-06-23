"""Camara stub: reproduce frames pregrabados o genera frames sinteticos."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import Config


class CameraStub:
    """Camara fake para desarrollo local."""

    def __init__(self, config: Config) -> None:
        self._cfg = config
        self._width = config.camera_width
        self._height = config.camera_height
        self._frame_idx = 0
        self._frames = self._load_test_frames()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Devuelve un frame sintetico o pregrabado."""
        if self._frames:
            frame = self._frames[self._frame_idx % len(self._frames)]
            self._frame_idx += 1
            return frame.copy()

        # Frame sintetico: fondo verde con circulo naranja
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:] = (50, 120, 50)  # BGR verde campo

        # Pelota naranja en posicion aleatoria
        cx = random.randint(self._width // 4, 3 * self._width // 4)
        cy = random.randint(self._height // 4, 3 * self._height // 4)
        cv2.circle(frame, (cx, cy), 25, (0, 140, 255), -1)

        return frame

    def release(self) -> None:
        pass

    def _load_test_frames(self) -> list[np.ndarray]:
        """Carga frames pregrabados desde stubs/test_frames/ si existen."""
        test_dir = Path(__file__).parent / "test_frames"
        if not test_dir.exists():
            return []
        frames = []
        for path in sorted(test_dir.glob("*.png")):
            frame = cv2.imread(str(path))
            if frame is not None:
                frames.append(frame)
        return frames
