#!/usr/bin/env python3
"""Captura 5 segundos de frames para calibración de visión.

Guarda las fotos originales en: /home/raspi1/futbot-v2/src/src/pipeline6/vision_calibration/raw/
Pon las fotos editadas con la pelota identificada en: /home/raspi1/futbot-v2/src/src/pipeline6/vision_calibration/labeled/

Ejecutar desde la Raspberry Pi:
    cd /home/raspi1/futbot-v2
    python3 -m src.pipeline6.vision_calibration.capture
"""

import os
import sys
import time
import cv2
import numpy as np
from pathlib import Path

# Agregar el path del proyecto
PROJECT_ROOT = Path(__file__).parent.parent / "futbot-v2"
sys.path.insert(0, str(PROJECT_ROOT))

from src.vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from src.vision.utils.vision_constants import CAMERA_WIDTH, CAMERA_HEIGHT


CALIBRATION_DIR = Path(__file__).parent / "vision_calibration"
RAW_DIR = CALIBRATION_DIR / "raw"
LABELED_DIR = CALIBRATION_DIR / "labeled"

RAW_DIR.mkdir(exist_ok=True)
LABELED_DIR.mkdir(exist_ok=True)

print(f"📁 Carpeta RAW: {RAW_DIR}")
print(f"📁 Carpeta LABELED: {LABELED_DIR}")
print("=" * 50)


def create_camera():
    """Inicializa la cámara."""
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_EXPOSURE, 200)
    cap.set(cv2.CAP_PROP_BRIGHTNESS, 0)
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir la cámara")
    return cap


def capture_frames(duration_sec=5, fps=10):
    """Captura frames durante la duración especificada."""
    detector = HsvBallDetectionOperator()
    cap = create_camera()

    total_frames = duration_sec * fps
    frame_interval = 1.0 / fps
    captured = []

    print(f"🎥 Capturando {duration_sec} segundos ({total_frames} frames)...")
    print("Presiona 'q' para salir antes de tiempo\n")

    start_time = time.time()
    frame_count = 0

    while frame_count < total_frames:
        loop_start = time.time()

        ret, frame = cap.read()
        if not ret:
            print(f"⚠️ Frame {frame_count} no disponible")
            continue

        now = time.time()
        ball = detector.detect(frame, now)

        display = frame.copy()

        if ball:
            cv2.circle(display, (ball.cx, ball.cy), int(ball.r), (0, 255, 0), 2)
            cv2.putText(
                display,
                f"OK: cx={ball.cx} cy={ball.cy} r={ball.r:.1f}",
                (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
        else:
            cv2.putText(
                display,
                "Sin pelota",
                (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 255),
                1,
            )

        cv2.putText(
            display,
            f"Frame {frame_count + 1}/{total_frames}",
            (10, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )

        cv2.imshow("Captura - Presiona 'q' para salir", display)

        captured.append((frame.copy(), ball))
        frame_count += 1

        elapsed = time.time() - start_time
        remaining = duration_sec - elapsed
        print(
            f"\r  Progreso: {frame_count}/{total_frames} | "
            f"Tiempo: {elapsed:.1f}s / {duration_sec}s",
            end="",
            flush=True,
        )

        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("\n⚠️ Captura cancelada por el usuario")
            break

        loop_time = time.time() - loop_start
        if loop_time < frame_interval:
            time.sleep(frame_interval - loop_time)

    cap.release()
    cv2.destroyAllWindows()

    print(f"\n\n✅ Captura completada: {len(captured)} frames")

    return captured


def save_frames(frames):
    """Guarda los frames capturados en la carpeta raw."""
    print(f"\n💾 Guardando {len(frames)} frames en {RAW_DIR}...")

    for i, (frame, ball) in enumerate(frames):
        filename = f"frame_{i:04d}.jpg"
        filepath = RAW_DIR / filename
        cv2.imwrite(str(filepath), frame)

        if ball:
            print(f"  ✓ {filename} - pelota detectada (cx={ball.cx}, cy={ball.cy}, r={ball.r:.1f})")
        else:
            print(f"  ○ {filename} - sin pelota")

    print(f"\n📂 Frames guardados en: {RAW_DIR}")
    print(f"📂 Pon las fotos editadas en: {LABELED_DIR}")


def main():
    print("=" * 50)
    print("  CAPTURA DE VISION PARA CALIBRACIÓN")
    print("=" * 50)
    print()
    print("Este script:")
    print("  1. Captura 5 segundos de video de la cámara")
    print("  2. Muestra los frames con detección en tiempo real")
    print("  3. Guarda las fotos originales en la carpeta 'raw'")
    print()
    print("Después:")
    print("  - Revisa las fotos en la carpeta 'raw'")
    print("  - Copia las que quieras editar a la carpeta 'labeled'")
    print("  - Marca la pelota en las fotos (círculo verde)")
    print("  - Los cambios en LABELED se usarán para refinar la visión")
    print()
    print("=" * 50)
    input("Presiona ENTER para comenzar la captura...")

    frames = capture_frames(duration_sec=5, fps=10)

    if frames:
        save_frames(frames)
    else:
        print("⚠️ No se capturaron frames")

    print("\n🎉 Proceso completado!")


if __name__ == "__main__":
    main()