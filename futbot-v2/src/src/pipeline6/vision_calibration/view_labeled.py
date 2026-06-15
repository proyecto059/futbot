#!/usr/bin/env python3
"""Muestra las fotos editadas en la carpeta labeled para revisión.

Ejecutar desde la Raspberry Pi:
    cd /home/raspi1/futbot-v2
    python3 -m src.pipeline6.vision_calibration.view_labeled
"""

import sys
import cv2
from pathlib import Path

CALIBRATION_DIR = Path(__file__).parent / "vision_calibration"
LABELED_DIR = CALIBRATION_DIR / "labeled"


def view_labeled_images():
    """Muestra las imágenes en la carpeta labeled."""
    if not LABELED_DIR.exists():
        print(f"⚠️ La carpeta {LABELED_DIR} no existe")
        return

    image_files = sorted(LABELED_DIR.glob("*.jpg")) + sorted(
        LABELED_DIR.glob("*.png")
    )

    if not image_files:
        print(f"⚠️ No hay imágenes en {LABELED_DIR}")
        return

    print(f"📂 Found {len(image_files)} images in {LABELED_DIR}")
    print("Press 'n' for next, 'p' for previous, 'q' to quit\n")

    index = 0
    while True:
        img_path = image_files[index]
        img = cv2.imread(str(img_path))

        if img is None:
            print(f"⚠️ Could not load {img_path}")
            index = (index + 1) % len(image_files)
            continue

        cv2.imshow("Labeled Image", img)

        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("n"):
            index = (index + 1) % len(image_files)
        elif key == ord("p"):
            index = (index - 1) % len(image_files)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    view_labeled_images()