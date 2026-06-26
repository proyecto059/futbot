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
    print("Iniciando servicio de visión para diagnóstico...")
    vision = HybridVisionService()
    
    try:
        print("Calentando cámara (esperando 2 segundos)...")
        # Dejar que la cámara se estabilice y la inteligencia artificial cargue
        for _ in range(20):
            vision.tick()
            time.sleep(0.1)
            
        print("Capturando frame de diagnóstico...")
        snap = vision.tick()
        frame = vision.last_frame()
        ball = snap.get("ball")
        
        if frame is not None:
            # Hacemos una copia para dibujar sin alterar la original
            debug_frame = frame.copy()
            
            # Dibujar una cruz en el centro de la cámara para referencia
            h, w = debug_frame.shape[:2]
            cv2.line(debug_frame, (w//2, 0), (w//2, h), (200, 200, 200), 1)
            cv2.line(debug_frame, (0, h//2), (w, h//2), (200, 200, 200), 1)
            
            if ball is not None:
                cx = int(ball["cx"])
                cy = int(ball["cy"])
                r = int(ball["r"])
                source = ball.get("source", "unknown")
                
                print(f"¡Pelota detectada! cx: {cx}, cy: {cy}, r: {r}, fuente: {source}")
                
                # Dibujar un círculo verde del tamaño del radio detectado
                cv2.circle(debug_frame, (cx, cy), r, (0, 255, 0), 2)
                # Dibujar un punto rojo en el centro exacto
                cv2.circle(debug_frame, (cx, cy), 3, (0, 0, 255), -1)
                
                # Dibujar un pequeño cuadrado azul (es el parche 7x7 que usamos para checar color)
                patch_r = 3
                y0 = max(0, cy - patch_r)
                y1 = min(h, cy + patch_r + 1)
                x0 = max(0, cx - patch_r)
                x1 = min(w, cx + patch_r + 1)
                cv2.rectangle(debug_frame, (x0, y0), (x1, y1), (255, 0, 0), 1)
                
                # Escribir de dónde vino la detección (HSV o YOLO)
                texto = f"Pelota ({source})"
                cv2.putText(debug_frame, texto, (max(0, cx - r), max(15, cy - r - 10)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                            
            else:
                print("No se detectó ninguna pelota en este frame.")
                cv2.putText(debug_frame, "SIN PELOTA", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            
            filename = os.path.join(current_dir, "captura_vision_debug.jpg")
            cv2.imwrite(filename, debug_frame)
            print(f"¡Éxito! Imagen con dibujos de visión guardada en: {filename}")
        else:
            print("Error: No se pudo obtener ningún frame de la cámara.")
            
    except Exception as e:
        print(f"Ocurrió un error: {e}")
    finally:
        print("Cerrando servicio de visión...")
        vision.close()

if __name__ == "__main__":
    main()
