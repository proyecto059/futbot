"""Pipeline FSM — maquina de estados del robot.

Estados:
  SEARCH    -> barrido rotacional buscando la pelota.
  CHASE     -> servo visual: avance con giro proporcional al error.
  RECOVERY  -> busqueda en espiral para re-adquirir la pelota.

Transiciones:
  SEARCH -> CHASE    (pelota detectada)
  CHASE  -> RECOVERY (pelota perdida > chase_miss_secs)
  RECOVERY -> CHASE  (pelota re-detectada)
  RECOVERY -> SEARCH (timeout: recovery_max_steps * 2)

La clase Pipeline consume Detections de vision.py y produce MotorCommand
para motors.py. No tiene dependencia de hardware — funciona identico en
modo real y stub.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from config import Config
from motors import MotorCommand
from vision import Ball, Detections

log = logging.getLogger("futbot.pipeline")

# ── Constantes de estado ──────────────────────────────────────────────────────

SEARCH = "SEARCH"
"""Estado de busqueda: el robot gira sobre si mismo escaneando el entorno."""

CHASE = "CHASE"
"""Estado de persecucion: servo visual hacia la pelota con avance."""

RECOVERY = "RECOVERY"
"""Estado de recuperacion: maniobras para reencontrar la pelota perdida."""


class Pipeline:
    """Controlador FSM que convierte detecciones en comandos de motores.

    Mantiene el estado interno de la maquina y los timers para transiciones.
    El metodo tick() se llama una vez por frame desde el bucle principal.

    Atributos:
        _state: Estado actual ("SEARCH", "CHASE" o "RECOVERY").
        _last_cx: Ultima posicion x conocida de la pelota en pixeles.
        _miss_start: Timestamp cuando se perdio la pelota por primera vez.
        _last_ball_time: Timestamp de la ultima deteccion exitosa.
        _last_search_time: Timestamp del ultimo paso de busqueda.
        _last_chase_time: Timestamp del ultimo paso de escaneo ciego.
        _recovery_step: Contador de pasos en la secuencia de recuperacion.
        _recovery_dir: Direccion de giro en recuperacion ("left"/"right").
        _frame_width: Ancho del frame en pixeles para calculos de centro.
    """

    def __init__(self, config: Config) -> None:
        """Inicializa el pipeline en estado SEARCH.

        Args:
            config: Instancia de Config con parametros de velocidad, tiempos
                y umbrales para cada estado del FSM.
        """
        self._cfg = config
        self._state: str = SEARCH
        self._last_cx: Optional[float] = None
        self._miss_start: Optional[float] = None
        self._last_ball_time: float = 0.0
        self._last_search_time: float = 0.0
        self._last_chase_time: float = 0.0
        self._recovery_step: int = 0
        self._recovery_dir: str = "left"
        self._frame_width: int = config.camera_width

    @property
    def state(self) -> str:
        """Estado actual del FSM: "SEARCH", "CHASE" o "RECOVERY"."""
        return self._state

    def set_frame_width(self, w: int) -> None:
        """Actualiza el ancho del frame para calculos de centro x.

        Se llama desde main.py despues de inicializar la camara, ya que
        algunos backends pueden entregar frames con dimensiones diferentes
        a las configuradas.

        Args:
            w: Ancho real del frame en pixeles.
        """
        self._frame_width = w

    def tick(self, dets: Detections) -> MotorCommand:
        """Ejecuta un paso de la maquina de estados.

        Evalua el estado actual, verifica condiciones de transicion,
        aplica la logica del estado activo y retorna el comando de motores.

        Args:
            dets: Detecciones del frame actual (ball, goal, white_line).

        Returns:
            MotorCommand con velocidades, duracion y angulos de servo.
        """
        now = time.time()
        ball: Optional[Ball] = dets.ball
        ball_visible = ball is not None
        line = dets.white_line
        frame_center = self._frame_width / 2

        cx = None
        if ball_visible:
            cx = ball.x * self._frame_width
        if ball_visible:
            self._last_cx = cx
            self._miss_start = None
        elif self._miss_start is None:
            self._miss_start = now

        miss_secs = (now - self._miss_start) if self._miss_start is not None else 0.0

        prev = self._state

        if self._state == CHASE:
            if not ball_visible and miss_secs >= self._cfg.chase_miss_secs:
                self._state = RECOVERY

        elif self._state == RECOVERY:
            if ball_visible:
                self._state = CHASE
            elif self._recovery_step >= self._cfg.recovery_max_steps * 2:
                self._state = SEARCH

        elif self._state == SEARCH:
            if ball_visible:
                self._state = CHASE

        if self._state != prev:
            log.info("fsm: %s -> %s", prev, self._state)
            if self._state == SEARCH:
                self._last_search_time = 0.0
                self._last_cx = None
            elif self._state == CHASE:
                self._last_chase_time = 0.0
            elif self._state == RECOVERY:
                self._recovery_step = 0
                self._recovery_dir = (
                    "left" if self._last_cx is None or self._last_cx < frame_center
                    else "right"
                )

        if self._state == SEARCH:
            cmd = self._tick_search(now)
        elif self._state == CHASE:
            cmd = self._tick_chase(now, ball, ball_visible, frame_center)
        elif self._state == RECOVERY:
            cmd = self._tick_recovery(now, ball_visible, line)
        else:
            cmd = MotorCommand(0.0, 0.0, 100)

        return cmd

    def _tick_search(self, now: float) -> MotorCommand:
        """Logica del estado SEARCH: barrido rotacional con pausas.

        Gira en una direccion, espera search_scan_secs, y vuelve a girar.
        La direccion se determina por la ultima posicion conocida de la
        pelota. Si no hay referencia, gira a la izquierda por defecto.

        Args:
            now: Timestamp actual.

        Returns:
            MotorCommand con giro o pausa.
        """
        if now - self._last_search_time >= self._cfg.search_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < self._frame_width / 2
            ) else "right"
            speed = self._cfg.search_turn_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_search_time = now
            return MotorCommand(v_left, v_right, self._cfg.search_turn_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_chase(
        self, now: float, ball: Optional[Ball], ball_visible: bool, frame_center: float
    ) -> MotorCommand:
        """Logica del estado CHASE: servo visual proporcional.

        Con pelota visible:
          - Si el radio >= kick_radius_px: patada directa (avance recto rapido)
          - Si el error horizontal <= deadband: avance recto
          - Si no: giro proporcional — la rueda externa acelera, la interna
            desacelera (nunca negativa, siempre avanza)

        Sin pelota:
          - Ventana de inercia (chase_miss_secs): avance recto lento
          - Escaneo ciego: giros direccionales periodicos

        Args:
            now: Timestamp actual.
            ball: Deteccion de pelota (None si no visible).
            ball_visible: Si la pelota esta en el frame actual.
            frame_center: Centro x del frame en pixeles.

        Returns:
            MotorCommand con velocidades de persecucion.
        """
        if ball_visible and ball is not None:
            self._last_ball_time = now
            cx = ball.x * self._frame_width
            radius = ball.radius * max(self._frame_width, self._cfg.camera_height)

            if radius >= self._cfg.kick_radius_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error = cx - frame_center
            if abs(error) <= self._cfg.chase_deadband_px:
                base = self._cfg.chase_speed_base
                return MotorCommand(base, base, 100)

            error_norm = min(abs(error) / frame_center, 1.0)
            diff = self._cfg.chase_speed_base * error_norm * self._cfg.chase_rot_gain
            base = self._cfg.chase_speed_base

            if error > 0:
                v_left = base + diff
                v_right = max(0.0, base - diff)
            else:
                v_left = max(0.0, base - diff)
                v_right = base + diff
            return MotorCommand(v_left, v_right, 100)

        if now - self._last_ball_time < self._cfg.chase_miss_secs:
            return MotorCommand(self._cfg.chase_blind_speed,
                                self._cfg.chase_blind_speed, 100)

        if now - self._last_chase_time >= self._cfg.chase_blind_scan_secs:
            direction = "left" if (
                self._last_cx is None or self._last_cx < frame_center
            ) else "right"
            speed = self._cfg.chase_blind_speed
            if direction == "left":
                v_left, v_right = -speed, speed
            else:
                v_left, v_right = speed, -speed
            self._last_chase_time = now
            return MotorCommand(v_left, v_right, self._cfg.chase_blind_ms)
        return MotorCommand(0.0, 0.0, 100)

    def _tick_recovery(
        self, now: float, ball_visible: bool, line
    ) -> MotorCommand:
        """Logica del estado RECOVERY: secuencia de maniobras de busqueda.

        Secuencia: retroceso → giro → avance → giro → ...
        Si detecta linea blanca, retrocede inmediatamente para no salir
        del campo. Tras recovery_max_steps * 2 pasos, vuelve a SEARCH.

        Args:
            now: Timestamp actual.
            ball_visible: Si la pelota es visible (provoca transicion a CHASE).
            line: Deteccion de linea blanca (WhiteLine o None).

        Returns:
            MotorCommand con maniobra de recuperacion.
        """
        if line is not None and line.detected:
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)

        step = self._recovery_step
        self._recovery_step += 1

        if step == 0:
            return MotorCommand(-self._cfg.recovery_reverse_speed,
                                -self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
        elif step % 2 == 1:
            speed = self._cfg.recovery_turn_speed
            if self._recovery_dir == "left":
                return MotorCommand(-speed, speed, self._cfg.recovery_turn_ms)
            else:
                return MotorCommand(speed, -speed, self._cfg.recovery_turn_ms)
        else:
            return MotorCommand(self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_speed,
                                self._cfg.recovery_reverse_ms)
