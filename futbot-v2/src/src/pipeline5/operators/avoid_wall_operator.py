import cv2
import numpy as np
import time
from src.pipeline5.utils.pipeline_constants import STOP_DUR_MS

class AvoidWallOperator:
    def __init__(self, black_threshold=30, coverage_ratio=0.35, reverse_duration=0.5, turn_duration=1.0):
        """
        black_threshold: valor máximo en escala de grises para considerar un píxel como "negro".
        coverage_ratio: porcentaje de la pantalla (0.0 a 1.0) que debe ser negra para disparar la evasión.
        reverse_duration: tiempo en segundos para retroceder en línea recta.
        turn_duration: tiempo en segundos para girar sobre su propio eje (~180 grados).
        """
        self.black_threshold = black_threshold
        self.coverage_ratio = coverage_ratio
        self.reverse_duration = reverse_duration
        self.turn_duration = turn_duration
        self._escaping = False
        self._escape_start_ts = 0.0

    def check_and_avoid(self, frame):
        """
        Analiza el frame y retorna (v_left, v_right, dur_ms) si debe evadir la pared, 
        o None si no hay peligro.
        """
        now = time.time()
        
        # Si ya estamos escapando, ejecutamos las fases de la maniobra
        if self._escaping:
            elapsed = now - self._escape_start_ts
            
            # Fase 1: Marcha atrás recta para despegarse de la pared
            if elapsed < self.reverse_duration:
                return -150.0, -150.0, STOP_DUR_MS
                
            # Fase 2: Giro sobre su propio eje (180 grados a mitad de velocidad)
            elif elapsed < (self.reverse_duration + self.turn_duration):
                # v_left positivo y v_right negativo = giro cerrado hacia la derecha (velocidad reducida)
                return 75.0, -75.0, STOP_DUR_MS
                
            # Terminó la maniobra
            else:
                self._escaping = False
        
        if frame is None:
            return None

        # Convertimos a escala de grises para analizar brillo
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Filtramos los píxeles muy oscuros (negros)
        black_mask = cv2.inRange(gray, 0, self.black_threshold)
        
        # Calculamos qué porcentaje de la imagen es negra
        total_pixels = frame.shape[0] * frame.shape[1]
        black_pixels = np.sum(black_mask > 0)
        ratio = black_pixels / total_pixels
        
        if ratio > self.coverage_ratio:
            # Hay mucha pared negra, iniciamos la maniobra de escape
            self._escaping = True
            self._escape_start_ts = now
            return -150.0, -100.0, STOP_DUR_MS
            
        return None
