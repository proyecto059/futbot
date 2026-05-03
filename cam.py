"""cam.py — script de captura de cámara para pruebas rápidas.

Este archivo era binario en el repositorio original (posiblemente corrompido
o con encoding no estándar). Funcionalidad equivalente:

    python cam.py          # muestra la imagen de la cámara en ventana OpenCV
    python cam.py --save   # guarda frames a disco

Para uso en RPi con libcamera:
    libcamera-still -o test.jpg
    libcamera-vid -t 5000 -o test.h264
"""

import cv2
import sys


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ No se pudo abrir la cámara")
        sys.exit(1)

    print("✅ Cámara abierta. Presiona 'q' para salir, 's' para guardar frame.")
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Error leyendo frame")
            break

        cv2.imshow("cam.py — FutbotMX", frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('s'):
            fname = f"frame_{frame_count:04d}.jpg"
            cv2.imwrite(fname, frame)
            print(f"  💾 Guardado: {fname}")
            frame_count += 1

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
