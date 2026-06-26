"""Operador de evasión de pared — capa de seguridad con máxima prioridad.

Detecta paredes negras en la franja inferior de la imagen (suelo frente al robot)
y ejecuta una maniobra de escape en 2 fases: marcha atrás → giro 180°.

Nota: los parámetros reales usados están hardcodeados en check_and_avoid()
(black_threshold=20, coverage_ratio=0.50), sobrescribiendo los del constructor.
"""

import cv2
import numpy as np
import time
from src.pipeline4.utils.pipeline_constants import STOP_DUR_MS

class AvoidWallOperator:
    def __init__(self, black_threshold=30, coverage_ratio=0.35, reverse_duration=0.5, turn_duration=1.0):
        """
        Args:
            black_threshold: valor máximo en escala de grises (0-255) para considerar
                             un píxel como "negro". NOTA: se sobrescribe a 20 en check_and_avoid().
            coverage_ratio: proporción de la ROI (0.0 a 1.0) que debe ser negra para
                            disparar la evasión. NOTA: se sobrescribe a 0.50 en check_and_avoid().
            reverse_duration: segundos de marcha atrás recta (fase 1).
            turn_duration: segundos de giro sobre el eje (~180°) (fase 2).
        """
        self.black_threshold = black_threshold
        self.coverage_ratio = coverage_ratio
        self.reverse_duration = reverse_duration
        self.turn_duration = turn_duration
        self._escaping = False
        self._escape_start_ts = 0.0

    def check_and_avoid(self, frame):
        """
        Analiza el frame y decide si evadir una pared negra.

        Retorna (v_left, v_right, dur_ms) si debe evadir, o None si no hay peligro.

        Algoritmo:
          1. Si ya está escapando, continúa la maniobra (fase 1 → fase 2 → fin).
          2. Convierte frame a grises y recorta ROI del suelo cercano.
          3. Cuenta píxeles negros (valor < black_threshold).
          4. Si ratio > coverage_ratio, inicia escape.
        """
        now = time.time()

        # Si ya estamos en maniobra de escape, continuar las fases
        if self._escaping:
            elapsed = now - self._escape_start_ts

            # Fase 1: Marcha atrás recta (0.5s) — alejarse de la pared
            if elapsed < self.reverse_duration:
                return -150.0, -150.0, STOP_DUR_MS

            # Fase 2: Giro 180° (1.0s) — media velocidad para no derrapar
            elif elapsed < (self.reverse_duration + self.turn_duration):
                # v_left=+50, v_right=-50 → giro cerrado a la derecha
                return 50.0, -50.0, STOP_DUR_MS

            # Maniobra completada
            else:
                self._escaping = False

        if frame is None:
            return None

        # ── Detección de pared negra ──
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # AJUSTE PARA CÁMARA INVERTIDA:
        # La cámara está físicamente de cabeza → el suelo cercano al robot
        # aparece en la parte SUPERIOR de la imagen (y=0 al 25%).
        # Lo lejano (techo, horizonte) está en la parte inferior.
        h, w = gray.shape
        roi = gray[0:int(h * 0.25), int(w * 0.2):int(w * 0.8)]

        # ⚠️ Hardcode: black_threshold se sobrescribe a 20 (ignora el valor del __init__)
        self.black_threshold = 20
        black_mask = cv2.inRange(roi, 0, self.black_threshold)

        total_pixels = roi.shape[0] * roi.shape[1]
        black_pixels = np.sum(black_mask > 0)
        ratio = black_pixels / total_pixels

        # ⚠️ Hardcode: coverage_ratio se sobrescribe a 0.50
        self.coverage_ratio = 0.50

        if ratio > self.coverage_ratio:
            # Pared detectada → iniciar maniobra de escape
            self._escaping = True
            self._escape_start_ts = now
            return -150.0, -100.0, STOP_DUR_MS

        return None
