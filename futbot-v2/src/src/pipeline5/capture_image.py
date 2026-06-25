"""Script de diagnóstico: captura un frame de la cámara y lo guarda como JPG.

Útil para verificar que la cámara IMX219 funciona y ver qué está viendo el robot
sin overlays ni procesamiento de visión.

Uso:
    python capture_image.py

Salida:
    captura_camara.jpg (en el mismo directorio)
"""

import sys
import os
import time
import cv2

# Añadir el directorio 'src' principal al PYTHONPATH para importar 'vision'
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from vision import HybridVisionService

def main():
    print("Iniciando servicio de visión para capturar imagen...")
    vision = HybridVisionService()
    
    try:
        # Hacemos un 'tick' inicial o esperamos para dar tiempo a la cámara de arrancar
        frame = None
        for _ in range(30):
            vision.tick() # Obliga al pipeline a trabajar
            frame = vision.last_frame()
            if frame is not None:
                break
            time.sleep(0.1)
        
        if frame is not None:
            filename = os.path.join(current_dir, "captura_camara.jpg")
            cv2.imwrite(filename, frame)
            print(f"¡Éxito! Imagen capturada y guardada en: {filename}")
        else:
            print("Error: No se pudo obtener ningún frame de la cámara después de 3 segundos.")
            
    except Exception as e:
        print(f"Ocurrió un error al intentar capturar la imagen: {e}")
    finally:
        print("Cerrando servicio de visión...")
        vision.close()

if __name__ == "__main__":
    main()
