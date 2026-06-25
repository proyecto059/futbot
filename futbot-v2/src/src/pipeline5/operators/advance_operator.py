"""Operador de avance — avanza recto hacia la pelota, ajustando curvas en tiempo real.

Misma convención que ChaseOperator de v3:
  - Ambas ruedas positivas = avanzar.
  - Ajusta la velocidad de las ruedas dependiendo del error (distancia de la pelota al centro).
"""

from src.pipeline5.utils.pipeline_constants import ADVANCE_SPEED

class AdvanceOperator:
    def __init__(self):
        self._last_cx = None
        
    def compute(self, frame_width, ball):
        """Retorna (v_left, v_right, dur_ms) para avanzar ajustando la dirección.

        Algoritmo de control proporcional:
          1. Calcular error = cx - centro_de_la_imagen (en píxeles)
          2. Normalizar error a [0, 1]
          3. Calcular diff = velocidad_base * error_norm * ganancia
          4. Rueda del lado de la pelota va más rápido, la otra más lento

        Casos especiales:
          - Pelota muy cerca (radio >= 45px): avanza recto a máxima velocidad
          - Pelota centrada (|error| <= 20px): avanza recto sin corregir
          - Sin pelota visible: usa la última posición conocida (self._last_cx)
        """

        # Si vemos la pelota, guardamos su cx como referencia para frames futuros
        if ball is not None:
            self._last_cx = ball["cx"]
            radius = ball["r"]

            # Pelota muy cerca → avanzar recto a máxima velocidad (patear)
            if radius >= 45:
                return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100

        # Si no hay pelota visible, usar última posición conocida
        cx = self._last_cx
        if cx is None:
            return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100

        half_w = frame_width / 2.0
        error = cx - half_w  # Positivo = pelota a la derecha, Negativo = izquierda

        # Deadband: margen muerto de 20px donde no se corrige
        if abs(error) <= 20:
            return float(ADVANCE_SPEED), float(ADVANCE_SPEED), 100

        error_norm = min(abs(error) / half_w, 1.0)

        # Diferencia de velocidad entre ruedas.
        # Ganancia 0.8: máximo 80% de diferencia sobre la velocidad base.
        # Valores >0.8 producen curvas más cerradas; <0.8 más suaves.
        diff = ADVANCE_SPEED * error_norm * 0.8

        if error > 0:
            # Pelota a la derecha → rueda izquierda acelera, derecha frena
            v_left = ADVANCE_SPEED + diff
            v_right = ADVANCE_SPEED - diff
        else:
            # Pelota a la izquierda → rueda derecha acelera, izquierda frena
            v_left = ADVANCE_SPEED - diff
            v_right = ADVANCE_SPEED + diff

        # Clamp a rango válido de PWM [0, 255]
        v_left = max(0.0, v_left)
        v_right = max(0.0, v_right)
        v_left = min(v_left, 255.0)
        v_right = min(v_right, 255.0)

        return float(v_left), float(v_right), 100
