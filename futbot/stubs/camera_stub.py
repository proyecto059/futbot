"""Camara stub: reproduce frames pregrabados o genera frames sinteticos.

Usada en modo FUTBOT_MODE=stub para desarrollo y pruebas sin hardware real.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import Config


class CameraStub:
    """Camara fake para desarrollo local sin Raspberry Pi.

    Genera frames sinteticos (campo verde con pelota naranja) que son
    detectables por el pipeline de vision. Si existe el directorio
    stubs/test_frames/ con imagenes PNG, las reproduce en secuencia.

    Atributos:
        width: Ancho del frame (de Config).
        height: Alto del frame (de Config).
        _frame_idx: Indice del frame actual en la secuencia pregrabada.
        _frames: Lista de frames pregrabados (vacia si no hay).
    """

    def __init__(self, config: Config) -> None:
        """Inicializa el stub con las dimensiones de Config.

        Args:
            config: Instancia de Config con camera_width y camera_height.
        """
        self._cfg = config
        self._width = config.camera_width
        self._height = config.camera_height
        self._frame_idx = 0
        self._frames = self._load_test_frames()

    @property
    def width(self) -> int:
        """Ancho del frame sintetico en pixeles."""
        return self._width

    @property
    def height(self) -> int:
        """Alto del frame sintetico en pixeles."""
        return self._height

    def grab(self) -> Optional[np.ndarray]:
        """Genera o devuelve el siguiente frame.

        Si hay frames pregrabados en stubs/test_frames/, los reproduce
        ciclicamente. Si no, genera un frame sintetico con:
          - Fondo verde oscuro (BGR 50,120,50) simulando cesped
          - Circulo naranja (BGR 0,140,255) en posicion aleatoria
            dentro del 50% central del frame, simulando la pelota

        Returns:
            Frame BGR como array numpy, nunca None.
        """
        if self._frames:
            frame = self._frames[self._frame_idx % len(self._frames)]
            self._frame_idx += 1
            return frame.copy()

        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:] = (50, 120, 50)

        cx = random.randint(self._width // 4, 3 * self._width // 4)
        cy = random.randint(self._height // 4, 3 * self._height // 4)
        cv2.circle(frame, (cx, cy), 25, (0, 140, 255), -1)

        return frame

    def release(self) -> None:
        """No-op. No hay recursos que liberar en el stub."""

    def _load_test_frames(self) -> list[np.ndarray]:
        """Carga frames PNG desde stubs/test_frames/ si el directorio existe.

        Utiles para pruebas deterministicas con imagenes reales capturadas
        del robot.

        Returns:
            Lista de frames BGR, vacia si el directorio no existe.
        """
        test_dir = Path(__file__).parent / "test_frames"
        if not test_dir.exists():
            return []
        frames = []
        for path in sorted(test_dir.glob("*.png")):
            frame = cv2.imread(str(path))
            if frame is not None:
                frames.append(frame)
        return frames
