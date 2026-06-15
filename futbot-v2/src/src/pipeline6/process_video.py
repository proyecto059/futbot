import os
import sys
import time
import argparse
import cv2

# Asegurar que podemos importar desde src/src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.operators.hsv_ball_detection_operator import HsvBallDetectionOperator
from vision.operators.goal_color_detection_operator import GoalColorDetectionOperator
from vision.operators.white_line_detection_operator import WhiteLineDetectionOperator
from vision.operators.yolo_inference_operator import YoloInferenceOperator
from vision.operators.yolo_parser_operator import YoloParserOperator
from vision.utils.onnx_session_factory import OnnxSessionFactory

def main():
    parser = argparse.ArgumentParser(description="Captura de cámara y guarda frames con bounding boxes.")
    parser.add_argument("--camera", type=int, default=0, help="Índice de la cámara (por defecto 0).")
    parser.add_argument("--outdir", default="output_frames", help="Directorio de salida para las capturas.")
    parser.add_argument("--model", default="../../model.onnx", help="Ruta al modelo YOLO onnx.")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Error: no se pudo abrir la cámara {args.camera}")
        return

    # Iniciar operadores
    hsv_ball = HsvBallDetectionOperator()
    goals = GoalColorDetectionOperator()
    line = WhiteLineDetectionOperator()
    
    print(f"Cargando modelo YOLO desde {args.model}...")
    try:
        from pathlib import Path
        session = OnnxSessionFactory.create(Path(args.model))
        yolo = YoloInferenceOperator(session)
    except Exception as e:
        print(f"Error cargando YOLO: {e}")
        return

    parser_op = YoloParserOperator()

    frame_idx = 0
    print("Iniciando procesamiento de video...")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        ts = time.time()
        
        # 1. Detecciones
        ball_hsv = hsv_ball.detect(frame, ts)
        goals_res = goals.detect(frame)
        line_res = line.detect(frame)
        
        # YOLO de forma sincrónica para no perder frames
        yolo._run_once(frame, ts)
        raw_yolo = yolo.get_latest_output()
        ball_yolo, robots = parser_op.parse(raw_yolo)
        
        # 2. Dibujar bounding boxes y anotaciones
        draw_frame = frame.copy()
        
        # Dibujar bola HSV (Círculo amarillo)
        if ball_hsv:
            cv2.circle(draw_frame, (ball_hsv.cx, ball_hsv.cy), int(ball_hsv.r), (0, 255, 255), 2)
            cv2.putText(draw_frame, "HSV Ball", (ball_hsv.cx, ball_hsv.cy - int(ball_hsv.r) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
        # Dibujar bola YOLO (Círculo naranja)
        if ball_yolo:
            cv2.circle(draw_frame, (ball_yolo.cx, ball_yolo.cy), int(ball_yolo.r), (0, 165, 255), 2)
            cv2.putText(draw_frame, f"YOLO Ball {ball_yolo.conf:.2f}", (ball_yolo.cx, ball_yolo.cy - int(ball_yolo.r) - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
            
        # Dibujar Robots (Bounding box rojo)
        for robot in robots:
            x1, y1, x2, y2 = robot.bbox
            cv2.rectangle(draw_frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(draw_frame, f"Robot {robot.conf:.2f}", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
        # Dibujar Porterías
        if goals_res:
            if getattr(goals_res, "blue_cx", None) is not None:
                cx = int(goals_res.blue_cx)
                cv2.line(draw_frame, (cx, 0), (cx, draw_frame.shape[0]), (255, 0, 0), 2)
                cv2.putText(draw_frame, "Blue Goal", (cx + 5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            if getattr(goals_res, "yellow_cx", None) is not None:
                cx = int(goals_res.yellow_cx)
                cv2.line(draw_frame, (cx, 0), (cx, draw_frame.shape[0]), (0, 255, 255), 2)
                cv2.putText(draw_frame, "Yellow Goal", (cx + 5, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        # Guardar captura
        out_path = os.path.join(args.outdir, f"frame_{frame_idx:04d}.jpg")
        cv2.imwrite(out_path, draw_frame)
        
        if frame_idx % 10 == 0:
            print(f"Procesado frame {frame_idx}. Guardado en {out_path}")
            
        frame_idx += 1

    cap.release()
    print(f"Completado. {frame_idx} frames guardados en {args.outdir}/")

    cap.release()

if __name__ == "__main__":
    main()
