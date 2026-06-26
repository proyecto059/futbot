"""Operador de avance — avanza recto hacia la pelota, ajustando curvas en tiempo real.

Misma convención que ChaseOperator de v3:
  - Ambas ruedas positivas = avanzar.
  - Ajusta la velocidad de las ruedas dependiendo del error (distancia de la pelota al centro).
"""

from pipeline02.utils.pipeline_constants import ADVANCE_SPEED

class AdvanceOperator:
    def __init__(self):
        self._last_cx = None
        
    def compute(self, frame_width, ball):
        """Retorna (v_left, v_right, dur_ms) para avanzar ajustando la dirección proporcionalmente."""
        
        # Si vemos la pelota, guardamos su cx para recordarlo
        if ball is not None:
            self._last_cx = ball["cx"]
            radius = ball["r"]
            
            # Si la pelota está muy cerca (radio grande), vamos directo a patearla sin curvar
            if radius >= 45:
                return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100
        
        # Si no la vemos pero la recordamos, usamos la última posición conocida
        cx = self._last_cx
        if cx is None:
            return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100
            
        half_w = frame_width / 2.0
        error = cx - half_w
        
        # Margen "muerto" en el centro donde simplemente va recto (20px)
        if abs(error) <= 20:
            return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100
            
        error_norm = min(abs(error) / half_w, 1.0)
        
        # Diferencia máxima del 80% sobre la velocidad base
        # Se puede ajustar este 0.8 si las curvas son muy cerradas
        diff = ADVANCE_SPEED * error_norm * 0.8
        
        if error > 0:
            # Pelota a la derecha: rueda izquierda empuja más, derecha se frena
            v_left = ADVANCE_SPEED + diff
            v_right = ADVANCE_SPEED - diff
        else:
            # Pelota a la izquierda: rueda derecha empuja más, izquierda se frena
            v_left = ADVANCE_SPEED - diff
            v_right = ADVANCE_SPEED + diff
            
        v_left = max(0.0, v_left)
        v_right = max(0.0, v_right)
        
        # Evitar exceder el PWM máximo típico (255)
        v_left = min(v_left, 255.0)
        v_right = min(v_right, 255.0)
        
        return float(v_left), float(v_right), 100
