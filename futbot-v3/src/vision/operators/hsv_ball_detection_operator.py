"""Detección adaptativa de bola naranja en HSV (corre en el hilo del caller).

Algoritmo:
    1. Gamma correction adaptativo según la mediana del canal V (ilumina frames oscuros).
    2. HSV + GaussianBlur, construcción de máscara con dos rangos de hue
       (wrap-around entre 0 y 179) y un rango secundario fijo (HSV_LO2/HI2).
    3. Contornos → filtro por área, radio y circularidad.
    4. Validación final: el patch central del candidato debe tener hue dentro
       del rango naranja esperado.
    5. EMA del hue observado → adapta el centro del rango para el siguiente frame.
    6. Modos: strict → reacquire (ventana más ancha) → relaxed (tras perder bola).

Migrado de `cam.py:AdaptiveOrangeBallDetector` (líneas 518-877).
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from vision.dto.ball_dto import BallDto
from vision.utils.vision_constants import (
    ADAPTIVE_CIRCULARITY_LOW_LIGHT,
    ADAPTIVE_HUE_EMA_ALPHA,
    ADAPTIVE_GAMMA_MAX,
    ADAPTIVE_LOW_LIGHT_MIN_MISS_FRAMES,
    ADAPTIVE_MAX_RADIUS,
    ADAPTIVE_MIN_CIRCULARITY,
    ADAPTIVE_MISS_RESET_FRAMES,
    ADAPTIVE_ORANGE_HUE_MAX,
    ADAPTIVE_ORANGE_HUE_MIN,
    ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES,
    ADAPTIVE_RELAXED_RECENT_SEC,
    ADAPTIVE_SAT_LOW_LIGHT,
    ADAPTIVE_SAT_TIERS,
    ADAPTIVE_STRICT_BASE_MARGIN,
    BALL_MIN_AREA,
    BALL_MIN_RADIUS,
    BORDER_MARGIN,
    EXPOSURE_ADJUST_EVERY,
    EXPOSURE_MAX,
    EXPOSURE_MIN,
    HOT_PIXEL_Y_MAX,
    HSV_HI,
    HSV_HI2,
    HSV_LO,
    HSV_LO2,
)

log = logging.getLogger("turbopi.vision.hsv_ball")


class HsvBallDetectionOperator:
    """Detector adaptativo de bola naranja. Mantiene estado entre frames."""

    # Cache de LUTs de gamma: gamma cuantizado a 0.25 → pocas entradas reales
    _GAMMA_LUT_CACHE: dict = {}

    def __init__(self) -> None:
        self.hue_center: float = float((HSV_LO[0] + HSV_HI[0]) / 2.0)
        self.last_seen_ts: float = 0.0
        self.miss_streak: int = 0
        self.last_mode: str = "strict"

        self._current_gamma: float = 1.0

        # Acceso opcional al VideoCapture para rampa de exposición
        self._cap = None
        self._current_exp: int = 200
        self._exp_frame_count: int = 0

        self._debug_snapshot: dict = {
            "mode": "strict",
            "v_median": 0,
            "v_median_raw": 0,
            "sat_min": int(HSV_LO[1]),
            "val_min": int(HSV_LO[2]),
            "hue_center": float(self.hue_center),
            "hue_half_width": int(max(6, (HSV_HI[0] - HSV_LO[0]) // 2)),
            "gamma": 1.0,
            "exposure": 200,
        }

    # ── API pública ──────────────────────────────────────────────────────

    def set_exposure_cap(self, cap) -> None:
        """Permite que el detector ajuste la exposición del VideoCapture."""
        self._cap = cap
        self._current_exp = 200
        self._exp_frame_count = 0

    def detect(self, frame: np.ndarray, now_ts: float) -> Optional[BallDto]:
        """Busca la bola en el frame. Devuelve BallDto(source='hsv') o None."""
        v_median_raw = int(np.median(frame[::4, ::4, :]))
        corrected = self._apply_gamma(frame, v_median_raw)
        hsv = cv2.cvtColor(cv2.GaussianBlur(corrected, (11, 11), 0), cv2.COLOR_BGR2HSV)
        frame_h, frame_w = frame.shape[:2]

        use_relaxed = (
            self.miss_streak > 0
            and (now_ts - self.last_seen_ts) <= ADAPTIVE_RELAXED_RECENT_SEC
        )
        should_try_reacquire = self.miss_streak >= ADAPTIVE_REACQUIRE_MIN_MISS_FRAMES

        mode = "strict"

        # 1) Intento estricto (ventana de hue angosta)
        primary_mask = self._candidate_mask(hsv, relaxed=False)
        best = self._scan_contours(hsv, primary_mask)
        best = self._reject_if_border(best, frame_w)

        # 2) Intento reacquire (ventana más ancha + sat/val más permisivos)
        if best is None and should_try_reacquire:
            reacquire_mask = self._candidate_mask(
                hsv,
                relaxed=False,
                hue_half_width=16,
                sat_min_override=max(80, int(self._debug_snapshot["sat_min"]) - 10),
                val_min_override=max(50, int(self._debug_snapshot["val_min"]) - 15),
            )
            best = self._scan_contours(hsv, reacquire_mask)
            best = self._reject_if_border(best, frame_w)
            if best is not None:
                mode = "reacquire"

        # 3) Intento relaxed (después de un miss reciente)
        if best is None and use_relaxed:
            relaxed_mask = self._candidate_mask(hsv, relaxed=True)
            best = self._scan_contours(hsv, relaxed_mask)
            best = self._reject_if_border(best, frame_w)
            if best is not None:
                mode = "relaxed"

        # 4) Intento low_light (sat muy baja + circularidad reforzada)
        if best is None and self.miss_streak >= ADAPTIVE_LOW_LIGHT_MIN_MISS_FRAMES:
            low_light_mask = self._candidate_mask(
                hsv,
                relaxed=True,
                sat_min_override=ADAPTIVE_SAT_LOW_LIGHT,
                val_min_override=20,
            )
            best = self._scan_contours(
                hsv,
                low_light_mask,
                min_circularity_override=ADAPTIVE_CIRCULARITY_LOW_LIGHT,
            )
            best = self._reject_if_border(best, frame_w)
            if best is not None:
                mode = "low_light"

        if best is None:
            self.miss_streak += 1
            # Si llevamos demasiados frames sin ver la bola, reseteamos el EMA
            if self.miss_streak > ADAPTIVE_MISS_RESET_FRAMES:
                self.hue_center = float((HSV_LO[0] + HSV_HI[0]) / 2.0)
            self._adjust_exposure()
            return None

        cx, cy, radius, observed_h = best
        self._update_hue_center(observed_h)
        self.last_seen_ts = now_ts
        self.miss_streak = 0
        self.last_mode = mode
        self._debug_snapshot["hue_center"] = float(self.hue_center)
        self._debug_snapshot["mode"] = mode

        return BallDto.from_hsv(cx=cx, cy=cy, r=radius)

    def get_debug_snapshot(self) -> dict:
        return dict(self._debug_snapshot)

    # ── Helpers internos ─────────────────────────────────────────────────

    @staticmethod
    def _circularity(contour) -> float:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if area <= 0.0 or perimeter <= 0.0:
            return 0.0
        return float(4.0 * np.pi * area) / float(perimeter * perimeter)

    @staticmethod
    def _clamp_hue(value: float) -> int:
        return int(max(0, min(179, value)))

    @classmethod
    def _get_gamma_lut(cls, gamma: float) -> np.ndarray:
        """LUT cacheada para la transformación de gamma (evita recomputar)."""
        gamma_key = round(gamma, 2)
        if gamma_key not in cls._GAMMA_LUT_CACHE:
            inv_gamma = 1.0 / gamma
            table = np.array(
                [((i / 255.0) ** inv_gamma) * 255 for i in range(256)],
                dtype=np.uint8,
            )
            cls._GAMMA_LUT_CACHE[gamma_key] = table
        return cls._GAMMA_LUT_CACHE[gamma_key]

    def _apply_gamma(self, frame: np.ndarray, v_median_raw: int) -> np.ndarray:
        """Ilumina el frame si está muy oscuro. Cuantiza gamma a 0.25 para cacheo."""
        target_v = 120
        if v_median_raw <= 0:
            gamma = 2.0
        elif v_median_raw >= target_v:
            gamma = 1.0
        else:
            gamma = max(1.0, min(2.0, float(target_v) / float(v_median_raw)))
        gamma = min(gamma, ADAPTIVE_GAMMA_MAX)
        gamma = round(gamma * 4) / 4
        self._current_gamma = gamma
        self._debug_snapshot["v_median_raw"] = int(v_median_raw)
        return cv2.LUT(frame, self._get_gamma_lut(gamma))

    def _adjust_exposure(self) -> None:
        """Sube la exposición de la cámara tras varios frames sin ver la bola."""
        if self._cap is None:
            return
        self._exp_frame_count += 1
        if self._exp_frame_count < EXPOSURE_ADJUST_EVERY:
            return
        self._exp_frame_count = 0

        old_exp = self._current_exp
        if self.miss_streak >= 10:
            self._current_exp = min(EXPOSURE_MAX, self._current_exp + 40)
        self._current_exp = max(EXPOSURE_MIN, min(EXPOSURE_MAX, self._current_exp))

        if self._current_exp != old_exp:
            try:
                self._cap.set(cv2.CAP_PROP_EXPOSURE, int(self._current_exp))
                log.info(
                    "Exposure: %d->%d (miss=%d)",
                    old_exp,
                    self._current_exp,
                    self.miss_streak,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("no se pudo ajustar exposición: %s", exc)
        self._debug_snapshot["exposure"] = int(self._current_exp)

    def _build_hue_mask(
        self,
        hsv: np.ndarray,
        hue_center: float,
        hue_half_width: int,
        sat_min: int,
        val_min: int,
    ) -> np.ndarray:
        """Construye máscara del rango de hue alrededor de `hue_center`.

        Maneja wrap-around (cuando lo_h > hi_h porque atraviesa el 0 del círculo
        HSV) con un OR de dos máscaras. Siempre agrega el rango secundario
        (HSV_LO2/HI2) para capturar el naranja del lado 168-179 del hue.
        """
        lo_h = self._clamp_hue(hue_center - hue_half_width)
        hi_h = self._clamp_hue(hue_center + hue_half_width)

        if lo_h <= hi_h:
            mask = cv2.inRange(
                hsv,
                np.array((lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((hi_h, 255, 255), dtype=np.uint8),
            )
        else:
            mask_a = cv2.inRange(
                hsv,
                np.array((0, sat_min, val_min), dtype=np.uint8),
                np.array((hi_h, 255, 255), dtype=np.uint8),
            )
            mask_b = cv2.inRange(
                hsv,
                np.array((lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((179, 255, 255), dtype=np.uint8),
            )
            mask = cv2.bitwise_or(mask_a, mask_b)

        mask2 = cv2.inRange(
            hsv,
            np.array((HSV_LO2[0], sat_min, val_min), dtype=np.uint8),
            np.array((HSV_HI2[0], 255, 255), dtype=np.uint8),
        )
        return cv2.bitwise_or(mask, mask2)

    def _update_adaptive_thresholds(self, hsv: np.ndarray, relaxed: bool) -> None:
        v_channel = hsv[::4, ::4, 2]
        v_median = int(np.median(v_channel))

        strict_sat = 220
        relaxed_sat = 200
        for tier_name, (v_threshold, tier_sat) in ADAPTIVE_SAT_TIERS.items():
            if v_median < v_threshold:
                strict_sat = tier_sat
                relaxed_sat = max(60, tier_sat - 20)
                break

        sat_min = relaxed_sat if relaxed else strict_sat
        val_min = 10 if relaxed else 15
        self._debug_snapshot.update(
            {
                "mode": "relaxed" if relaxed else "strict",
                "v_median": v_median,
                "sat_min": sat_min,
                "val_min": val_min,
                "hue_center": float(self.hue_center),
                "gamma": float(self._current_gamma),
            }
        )

    def _candidate_mask(
        self,
        hsv: np.ndarray,
        relaxed: bool,
        hue_half_width: Optional[int] = None,
        sat_min_override: Optional[int] = None,
        val_min_override: Optional[int] = None,
    ) -> np.ndarray:
        """Calcula la máscara candidata para el modo dado (strict/relaxed/reacquire)."""
        self._update_adaptive_thresholds(hsv, relaxed)

        # Ancho de ventana de hue: fijo en relaxed, adaptativo en strict según brillo
        if hue_half_width is None:
            if relaxed:
                hue_half_width = 10
            else:
                vm = self._debug_snapshot.get("v_median", 120)
                if vm < 50 or vm > 200:
                    hue_half_width = 12
                elif vm < 80 or vm > 180:
                    hue_half_width = 9
                else:
                    hue_half_width = 7

        sat_min = (
            int(self._debug_snapshot["sat_min"])
            if sat_min_override is None
            else int(sat_min_override)
        )
        val_min = (
            int(self._debug_snapshot["val_min"])
            if val_min_override is None
            else int(val_min_override)
        )
        self._debug_snapshot["sat_min"] = sat_min
        self._debug_snapshot["val_min"] = val_min
        self._debug_snapshot["hue_half_width"] = hue_half_width

        mask = self._build_hue_mask(
            hsv, self.hue_center, hue_half_width, sat_min, val_min
        )

        # En strict agregamos un rango base fijo alrededor del HSV_LO/HI original
        if not relaxed:
            base_lo_h = self._clamp_hue(HSV_LO[0] - 2)
            base_hi_h = self._clamp_hue(HSV_HI[0] + ADAPTIVE_STRICT_BASE_MARGIN)
            base_mask = cv2.inRange(
                hsv,
                np.array((base_lo_h, sat_min, val_min), dtype=np.uint8),
                np.array((base_hi_h, 255, 255), dtype=np.uint8),
            )
            mask = cv2.bitwise_or(mask, base_mask)

        return mask

    @staticmethod
    def _extract_hue_patch(
        hsv: np.ndarray, cx: int, cy: int, radius: float
    ) -> Optional[np.ndarray]:
        """Recorta un patch central del candidato para validar que el hue es naranja."""
        r = int(max(3, min(12, radius * 0.4)))
        x0 = max(0, int(cx) - r)
        y0 = max(0, int(cy) - r)
        x1 = min(hsv.shape[1], int(cx) + r + 1)
        y1 = min(hsv.shape[0], int(cy) + r + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        return hsv[y0:y1, x0:x1, 0]

    def _scan_contours(
        self,
        hsv: np.ndarray,
        mask: np.ndarray,
        min_circularity_override: Optional[float] = None,
    ) -> Optional[Tuple[int, int, float, int]]:
        """Aplica morfología, extrae contornos y elige el mejor candidato."""
        k = np.ones((3, 3), np.uint8)
        clean = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k), k)
        contours, _ = cv2.findContours(
            clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        candidates = []
        base_min_area = max(100.0, float(BALL_MIN_AREA) * 0.4)
        base_min_circ = ADAPTIVE_MIN_CIRCULARITY
        # Si necesitamos mucha corrección gamma, subimos umbrales (hay más ruido)
        if self._current_gamma > 1.5:
            base_min_area *= 2.0
            base_min_circ = max(base_min_circ, 0.40)
        min_area = base_min_area
        min_radius = max(5.0, float(BALL_MIN_RADIUS) * 0.6)
        effective_min_circ = (
            min_circularity_override
            if min_circularity_override is not None
            else base_min_circ
        )

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if radius < min_radius or radius > ADAPTIVE_MAX_RADIUS:
                continue
            circularity = self._circularity(contour)
            if circularity < effective_min_circ:
                continue
            score = float(radius) * float(circularity)
            candidates.append((score, int(x), int(y), float(radius)))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # Valida los 3 mejores mirando el hue del patch central
        for _score, x, y, radius in candidates[:3]:
            patch_h = self._extract_hue_patch(hsv, x, y, radius)
            if patch_h is None or patch_h.size == 0:
                continue
            patch_median_h = int(np.median(patch_h))
            if (
                patch_median_h < ADAPTIVE_ORANGE_HUE_MIN
                or patch_median_h > ADAPTIVE_ORANGE_HUE_MAX
            ):
                continue
            return x, y, radius, patch_median_h

        return None

    @staticmethod
    def _reject_if_border(
        best: Optional[Tuple[int, int, float, int]],
        frame_w: int,
    ) -> Optional[Tuple[int, int, float, int]]:
        """Descarta candidatos en la franja superior ruidosa o pegados al borde."""
        if best is None:
            return None
        cx, cy, _r, _h = best
        if cy < HOT_PIXEL_Y_MAX or cx < BORDER_MARGIN or cx > frame_w - BORDER_MARGIN:
            return None
        return best

    def _update_hue_center(self, observed_h: float) -> None:
        """EMA del hue para seguir variaciones de iluminación de la bola."""
        observed_h = float(
            max(ADAPTIVE_ORANGE_HUE_MIN, min(ADAPTIVE_ORANGE_HUE_MAX, observed_h))
        )
        self.hue_center = (1.0 - ADAPTIVE_HUE_EMA_ALPHA) * self.hue_center + (
            ADAPTIVE_HUE_EMA_ALPHA * observed_h
        )
