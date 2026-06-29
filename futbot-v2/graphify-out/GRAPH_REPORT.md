# Graph Report - .  (2026-06-27)

## Corpus Check
- 171 files · ~114,223 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1019 nodes · 1445 edges · 87 communities detected
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 206 edges (avg confidence: 0.71)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Vision DTOs and Commands|Vision DTOs and Commands]]
- [[_COMMUNITY_Pipeline Operators (Advance, Align, Push)|Pipeline Operators (Advance, Align, Push)]]
- [[_COMMUNITY_Main Controller and Bus Interface|Main Controller and Bus Interface]]
- [[_COMMUNITY_State Machine and Tracking|State Machine and Tracking]]
- [[_COMMUNITY_Vision Pipeline Output and Images|Vision Pipeline Output and Images]]
- [[_COMMUNITY_Vision Service Configuration|Vision Service Configuration]]
- [[_COMMUNITY_Hardware Abstraction (Serial, I2C, Camera)|Hardware Abstraction (Serial, I2C, Camera)]]
- [[_COMMUNITY_Motor Service and Serial Protocol|Motor Service and Serial Protocol]]
- [[_COMMUNITY_Ultrasonic Sensor and DTOs|Ultrasonic Sensor and DTOs]]
- [[_COMMUNITY_Obstacle Avoidance and Evasion|Obstacle Avoidance and Evasion]]
- [[_COMMUNITY_Hardware Shim Compatibility Layer|Hardware Shim Compatibility Layer]]
- [[_COMMUNITY_Avoid Operator and Evasion Plans|Avoid Operator and Evasion Plans]]
- [[_COMMUNITY_Chase Operator and Pursuit Logic|Chase Operator and Pursuit Logic]]
- [[_COMMUNITY_Pipeline02 Advance Operator|Pipeline02 Advance Operator]]
- [[_COMMUNITY_Pipeline4 Push Operator|Pipeline4 Push Operator]]
- [[_COMMUNITY_Differential Operator and Wheel DTO|Differential Operator and Wheel DTO]]
- [[_COMMUNITY_Image Calibration (Exposure)|Image Calibration (Exposure)]]
- [[_COMMUNITY_Pipeline4 Camera Capture Images|Pipeline4 Camera Capture Images]]
- [[_COMMUNITY_Frame Capture and Backend Resolver|Frame Capture and Backend Resolver]]
- [[_COMMUNITY_Search Operator and Scanning|Search Operator and Scanning]]
- [[_COMMUNITY_Image Calibration (Gamma Correction)|Image Calibration (Gamma Correction)]]
- [[_COMMUNITY_Pipeline02 Camera Debug Images|Pipeline02 Camera Debug Images]]
- [[_COMMUNITY_Pipeline5 Advance Operator|Pipeline5 Advance Operator]]
- [[_COMMUNITY_Pipeline5 Obstacle Avoidance|Pipeline5 Obstacle Avoidance]]
- [[_COMMUNITY_Test Robot Deploy Config|Test Robot Deploy Config]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]

## God Nodes (most connected - your core abstractions)
1. `HybridVisionService` - 27 edges
2. `vision/hybrid_vision_service.py` - 20 edges
3. `vision/utils/vision_constants.py` - 20 edges
4. `main()` - 19 edges
5. `test-robot/hardware.py` - 18 edges
6. `HsvBallDetectionOperator` - 16 edges
7. `MotorService` - 15 edges
8. `main()` - 15 edges
9. `MovementOperator` - 13 edges
10. `Pipeline4Service` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test-robot/docs/plans/2026-04-11-yolo-hsv-calibration.md` --documents_calibration--> `vision/operators/hsv_ball_detection_operator.py`  [EXTRACTED]
  test-robot/docs/plans/2026-04-11-yolo-hsv-calibration.md → src/vision/operators/hsv_ball_detection_operator.py
- `Detected Ball Test Image` --captures_output--> `vision/operators/hsv_ball_detection_operator.py`  [EXTRACTED]
  test-robot/images/detected.jpg → src/vision/operators/hsv_ball_detection_operator.py
- `test-robot/docs/plans/2026-04-11-yolo-hsv-calibration.md` --documents_calibration--> `vision/operators/yolo_inference_operator.py`  [EXTRACTED]
  test-robot/docs/plans/2026-04-11-yolo-hsv-calibration.md → src/vision/operators/yolo_inference_operator.py
- `_vision()` --calls--> `HybridVisionService`  [INFERRED]
  cam.py → src\vision\hybrid_vision_service.py
- `test_hybrid_trigger_by_distance()` --calls--> `hybrid_trigger()`  [INFERRED]
  tests\test_main_hybrid_logic.py → main.py

## Hyperedges (group relationships)
- **Pipeline 4 Operator Chain** — pipeline4_operators_advance_operator, pipeline4_operators_align_to_goal_operator, pipeline4_operators_avoid_wall_operator, pipeline4_operators_chase_operator, pipeline4_operators_push_operator, pipeline4_operators_search_operator [EXTRACTED 0.95]
- **Pipeline 5 Operator Chain** — pipeline5_operators_advance_operator, pipeline5_operators_avoid_wall_operator, pipeline5_operators_search_operator [EXTRACTED 0.95]
- **Ultrasonic Operators** — ultrasonic_operators_ultrasonic_read_operator, ultrasonic_operators_ultrasonic_led_operator [EXTRACTED 0.95]
- **Vision Pipeline Operators** — vision_operators_ball_fusion_operator, vision_operators_frame_capture_operator, vision_operators_goal_color_detection_operator, vision_operators_hsv_ball_detection_operator, vision_operators_json_export_operator, vision_operators_white_line_detection_operator, vision_operators_yolo_inference_operator, vision_operators_yolo_parser_operator [EXTRACTED 0.95]
- **Vision DTOs** — vision_dto_ball_dto, vision_dto_frame_dto, vision_dto_goals_dto, vision_dto_line_dto, vision_dto_robot_dto, vision_dto_vision_output_dto [EXTRACTED 0.95]
- **Vision Utilities** — vision_utils_camera_backend_resolver, vision_utils_onnx_session_factory, vision_utils_vision_constants, vision_utils_libcamera_worker [EXTRACTED 0.90]
- **Test Robot Diagnostic Scripts** — testrobot_diag_all_detections, testrobot_diag_center_kick, testrobot_diag_line, testrobot_diag_line2, testrobot_diag_raw_track, testrobot_diag_servo_direction, testrobot_diag_servo_map, testrobot_diag_stationary, testrobot_diag_vision, testrobot_diag_yolo_hsv [EXTRACTED 0.90]
- **Test Robot Tests** — testrobot_tests_test_adaptive_ball_detection, testrobot_tests_test_diag_servos, testrobot_tests_test_main_approach_logic, testrobot_tests_test_play_futbot, testrobot_tests_test_servo_mapping [EXTRACTED 0.90]
- **Source Output Images** — img_src_output_capture, img_src_output_capture_bbox, img_src_output_capture_bigball, img_src_output_capture_bright, img_src_output_capture_smallball, img_src_output_capture_v3, img_src_output_direct_capture, img_src_output_raw_v4l2 [INFERRED 0.85]
- **Test Robot Design Documents** — docs_plan_differential_wheels, docs_plan_servo_tracking_design, docs_plan_servo_tracking_fix, docs_plan_yolo_hsv_calibration, docs_plan_play_futbot [EXTRACTED 0.90]
- **Exposure Calibration Images** — img_v2_exp600, img_v2_exp600_det, img_v2_exp800, img_v2_exp800_det, img_v2_exp1000, img_v2_exp1000_det, img_v4_exp2000 [INFERRED 0.85]
- **Gamma Calibration Images** — img_gamma, img_v3_g3, img_v3_g5, img_v3_g8 [INFERRED 0.85]

## Communities

### Community 0 - "Vision DTOs and Commands"
Cohesion: 0.03
Nodes (57): DetectVisionCommand, Request a `HybridVisionService.tick(command)` (parámetros por invocación)., Request opcional para un tick específico.      En la práctica casi siempre se, ball_to_dict(), BallDto, DTO de una detección de bola unificada (viene de HSV, YOLO o caché)., Posición y confianza de la bola en coordenadas de imagen., Devuelve copia con otro `source` (útil al marcar una detección como `cache`). (+49 more)

### Community 1 - "Pipeline Operators (Advance, Align, Push)"
Cohesion: 0.04
Nodes (37): docs/pipeline5.md, AdvanceOperator, Operador de avance — avanza recto hacia la pelota, ajustando curvas en tiempo re, Retorna (v_left, v_right, dur_ms) para avanzar ajustando la dirección proporcion, AlignToGoalOperator, Operador de alineación a portería — rota lentamente hasta centrar pelota y porte, Retorna (v_left, v_right, dur_ms) para rotar hacia la alineación.          Arg, AvoidWallOperator (+29 more)

### Community 2 - "Main Controller and Bus Interface"
Cohesion: 0.05
Nodes (64): apply_ball_proximity_override(), avoid_map_state_decision(), avoid_map_turn_direction(), build_avoid_map_plan(), _burst_drive(), choose_search_turn(), compute_chase_wheels(), compute_kick_wheels() (+56 more)

### Community 3 - "State Machine and Tracking"
Cohesion: 0.04
Nodes (37): Enum, run_diag_center_kick(), main(), should_hold_approach(), State, run_gol_avance(), run_gol_giro(), run_test_line() (+29 more)

### Community 4 - "Vision Pipeline Output and Images"
Cohesion: 0.06
Nodes (48): Contratos de entrada al pipeline (DTOs inmutables de configuración y request)., docs/plans/2026-04-15-husky-to-cam-hybrid-design.md, docs/plans/2026-04-15-husky-to-cam-hybrid-implementation-plan.md, test-robot/docs/plans/2026-04-11-yolo-hsv-calibration.md, DTO de salida final del pipeline — el JSON que consume el FSM (`main.py`)., Capture Frame Output, Detected Ball Test Image, Fusión de las dos fuentes de detección de bola (HSV + YOLO) con caché.      Re (+40 more)

### Community 5 - "Vision Service Configuration"
Cohesion: 0.04
Nodes (41): default(), Configuración de `HybridVisionService` (inmutable)., Parámetros globales del pipeline.      Valores por defecto replican el comport, VisionConfigCommand, Exception, Excepción: no se pudo abrir ningún backend de cámara., FrameCaptureException, Excepción: falló la lectura de un frame después de abrir la cámara. (+33 more)

### Community 6 - "Hardware Abstraction (Serial, I2C, Camera)"
Cohesion: 0.06
Nodes (19): AdaptiveOrangeBallDetector, _calibrate_exposure(), _circularity(), _clamp_hue(), _clamp_int(), crc8(), detect_ball(), _extract_hue_patch() (+11 more)

### Community 7 - "Motor Service and Serial Protocol"
Cohesion: 0.05
Nodes (21): src/motors/__init__.py, MotorService, Fachada de movimiento — serializa comandos de alto nivel al UART.  No contiene, Fachada única para primitivas de movimiento del robot.      Abre la conexión U, BurstOperator, Envío de paquetes binarios al UART — protocolo propietario del driver.  Respon, Serializa y envía pares servo+motor frames al UART., Envía un burst de dos frames (servo + motor) al UART.          Pasos: (+13 more)

### Community 8 - "Ultrasonic Sensor and DTOs"
Cohesion: 0.05
Nodes (26): Data Transfer Objects: shape estable del pipeline hacia el consumidor (FSM)., DTO de una lectura del sensor ultrasónico., Distancia medida en milímetros con timestamp de la lectura., Serializa el DTO a un ``dict`` JSON-serializable., UltrasonicDto, Operadores atómicos del pipeline.  Cada operador encapsula una responsabilidad, Control del LED RGB integrado en el sensor ultrasónico.  Escribe 7 bytes al re, Envía el color y modo al LED del sensor.          Args:             r, g, b: (+18 more)

### Community 9 - "Obstacle Avoidance and Evasion"
Cohesion: 0.07
Nodes (29): AvoidOperator, Plan de evasión secuencial: primero retroceso, luego alternancia giro/avance., Genera plan de evasión: retroceso + alternancia giro/avance., Retorna True si la distancia ultrasónica está por debajo del umbral., Suprime avoid si la pelota está visible y muy cerca (falso trigger)., ChaseOperator, Operador de persecución — CÓDIGO MUERTO (NO SE USA).  Este archivo NO es impor, pipeline02/dto/pipeline_output_dto.py (+21 more)

### Community 10 - "Hardware Shim Compatibility Layer"
Cohesion: 0.06
Nodes (25): _clamp_int(), crc8(), create_detector(), detect_ball(), detect_white_line(), find_camera(), get_ball_detection_debug(), _LegacyDetectorShim (+17 more)

### Community 11 - "Avoid Operator and Evasion Plans"
Cohesion: 0.12
Nodes (17): _calibrate_v4l2_exposure(), CameraBackendResolver, _enumerate_video_indices(), _LibcameraCap, _Picamera2Camera, Resuelve el backend de cámara probando picamera2 → GStreamer → V4L2.  Migrado, Intenta abrir una cámara probando backends en orden de preferencia.      Uso:, Adapta `picamera2.Picamera2` a la interfaz tipo `cv2.VideoCapture`.      Expon (+9 more)

### Community 12 - "Chase Operator and Pursuit Logic"
Cohesion: 0.08
Nodes (32): test-robot/docs/plans/2026-04-09-differential-wheels.md, test-robot/docs/plans/2026-04-12-play-futbot.md, test-robot/docs/plans/2026-04-10-servo-tracking-direction-bug-design.md, test-robot/docs/plans/2026-04-10-servo-tracking-direction-bugfix-implementation.md, test-robot/docs/serial-map.pdf, Gamma Adjusted Test Image, Raw Camera Test Image, Serial Map Diagram Page 1 (+24 more)

### Community 13 - "Pipeline02 Advance Operator"
Cohesion: 0.11
Nodes (16): _circularity(), _clamp_hue(), _extract_hue_patch(), _get_gamma_lut(), HsvBallDetectionOperator, Detección adaptativa de bola naranja en HSV (corre en el hilo del caller).  Al, Ilumina el frame si está muy oscuro. Cuantiza gamma a 0.25 para cacheo., Sube la exposición de la cámara tras varios frames sin ver la bola. (+8 more)

### Community 14 - "Pipeline4 Push Operator"
Cohesion: 0.09
Nodes (14): PipelineOutputDto, DTO (Data Transfer Object) para la salida de cada tick del pipeline., Snapshot del estado FSM y comandos de motor en un tick., Serializa el DTO a un dict JSON-serializable., Serializa el DTO a un diccionario JSON-serializable., Serializa el DTO a un diccionario JSON-serializable., Snapshot inmutable del estado FSM y comandos de motor en un tick.      Atribut, Snapshot inmutable del estado FSM y comandos de motor en un tick.      Atribut (+6 more)

### Community 15 - "Differential Operator and Wheel DTO"
Cohesion: 0.17
Nodes (11): GoalsDto, DTO del estado de los dos arcos (amarillo y azul) en el frame actual., Presencia y centroide horizontal de cada arco.      - `yellow` / `blue`: True, _centroid_cx(), _clean_mask(), _edge_dark_components_mask(), _edge_only_mask(), GoalColorDetectionOperator (+3 more)

### Community 16 - "Image Calibration (Exposure)"
Cohesion: 0.13
Nodes (7): HILO 2 — Inferencia YOLO en un worker thread (ONNX Runtime).  Patrón productor, Un ciclo de inferencia: blob → session.run → guarda raw output., Corre YOLO ONNX en un hilo dedicado y expone el último resultado., Arranca el worker thread. Idempotente., Deja un frame pendiente para el próximo ciclo del worker.          NON-BLOCKIN, Devuelve el último resultado crudo (copia defensiva)., YoloInferenceOperator

### Community 17 - "Pipeline4 Camera Capture Images"
Cohesion: 0.21
Nodes (11): VisualServoController, scripts/test_chase_dynamic.py, build_controller(), test_ball_left_turns_left_while_advancing(), test_ball_right_turns_right_while_advancing(), test_forward_command_uses_negative_vr_for_centered_ball(), test_forward_speed_reduces_when_ball_is_far_off_center(), test_lateral_tracking_keeps_min_forward_on_both_wheels() (+3 more)

### Community 18 - "Frame Capture and Backend Resolver"
Cohesion: 0.22
Nodes (6): run_play_futbot(), should_kick(), _install_stub_modules(), _load_play_futbot_symbols(), _restore_modules(), ShouldKickTests

### Community 19 - "Search Operator and Scanning"
Cohesion: 0.24
Nodes (8): run_diag_servos(), _collect_axis_moves(), DiagServosTests, _FakeSBus, _install_stub_modules(), _load_diag_symbols(), _restore_modules(), _run_diag_servos_with_flags()

### Community 20 - "Image Calibration (Gamma Correction)"
Cohesion: 0.2
Nodes (4): _install_stub_modules(), _load_hardware_symbols(), _restore_modules(), ServoMappingTests

### Community 21 - "Pipeline02 Camera Debug Images"
Cohesion: 0.27
Nodes (9): forward(), DTO de velocidades de rueda izquierda y derecha., Par de velocidades (v_left, v_right) para las dos ruedas de tracción., Devuelve ``(v_left, v_right)`` como tupla nativa., reverse(), stop(), turn_left(), turn_right() (+1 more)

### Community 22 - "Pipeline5 Advance Operator"
Cohesion: 0.4
Nodes (5): AdaptiveBallDetectionTests, _install_stub_modules(), _load_hardware_module(), _make_frame(), _restore_modules()

### Community 23 - "Pipeline5 Obstacle Avoidance"
Cohesion: 0.33
Nodes (6): V2 Exposure 1000, V2 Exposure 1000 Detected, V2 Exposure 600, V2 Exposure 600 Detected, V2 Exposure 800, V2 Exposure 800 Detected

### Community 24 - "Test Robot Deploy Config"
Cohesion: 0.7
Nodes (4): main(), _process_command(), _read_command(), _send_xrgb()

### Community 25 - "Community 25"
Cohesion: 0.5
Nodes (1): Test motores con nuevo mapeo.

### Community 26 - "Community 26"
Cohesion: 0.5
Nodes (3): crc8(), Constantes del subsistema de motores.  Fuente única de verdad para configuraci, Calcula el CRC8 de *data* usando la tabla de lookup pre-calculada.

### Community 27 - "Community 27"
Cohesion: 0.5
Nodes (1): Constantes de configuración para Pipeline 4 — rutina de disparo a portería.  V

### Community 28 - "Community 28"
Cohesion: 0.5
Nodes (4): Pipeline02 Camera Capture, Pipeline4 Camera Capture, pipeline02/capture_image.py, pipeline4/capture_image.py

### Community 29 - "Community 29"
Cohesion: 0.67
Nodes (1): Diagnostico de direccion de mapeo servo.  Centra servos, espera deteccion, y m

### Community 30 - "Community 30"
Cohesion: 0.67
Nodes (1): Diagnostico rapido de mapeo servo-pelota.  Uso: uv run diag_servo_map.py  Ce

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (2): main(), yolo_detect()

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): Paquete `motors` — control de motores y servos vía UART (/dev/ttyAMA0).  Punto

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): Constantes del sensor ultrasónico.  Fuente única de verdad para dirección I2C

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (2): tests/test_visual_servo_controller.py, src/chase/visual_servo_controller.py

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Ambas ruedas avanzan a la misma velocidad.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Ambas ruedas retroceden a la misma velocidad.

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Giro a la izquierda: rueda izquierda atrás, derecha adelante.

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Giro a la derecha: rueda izquierda adelante, derecha atrás.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Ambas ruedas detenidas.

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Crea un DTO sin lectura válida (``distance_mm=None``).          Se usa como fa

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Ancho real del frame (tras resolver el backend de cámara).

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Construye un BallDto a partir de la salida cruda del operador HSV.          El

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Snapshot vacío (cuando aún no hay frame o todo falla).

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Ancho real del frame (puede diferir del pedido si el backend no respeta size).

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Acceso al VideoCapture crudo (para operadores que necesitan ajustar exposición).

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Centroide X de la máscara si hay suficientes pixeles, si no None.

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): LUT cacheada para la transformación de gamma (evita recomputar).

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Recorta un patch central del candidato para validar que el hue es naranja.

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Descarta candidatos en la franja superior ruidosa o pegados al borde.

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Snapshot vacío con la estructura completa (campos null/[]).

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Entrada: dict devuelto por `YoloInferenceOperator.get_latest_output()`.

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Índices referenciados desde `/dev/v4l/by-id/*` (USB UVC).

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Devuelve índices plausibles de cámara, USB primero, CSI-subdev filtrados.

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Prueba en orden todos los /dev/videoN hasta dar con uno que entregue frames.

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Fija exposición manual para webcams V4L2 (estabiliza el brillo).

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Devuelve `(cap, frame_width_real, exposure)` o `(None, 0, 0)` si falla.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Crea una sesión ONNX Runtime validando que el archivo existe.          Si `mod

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): scripts/cal_motors.py

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): scripts/test_motors_raw.py

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): src/motors/motor_service.py

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): src/motors/dto/wheel_dto.py

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): src/motors/dto/__init__.py

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): src/motors/exceptions/motor_exception.py

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): src/motors/exceptions/__init__.py

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): src/motors/operators/burst_operator.py

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): src/motors/operators/differential_operator.py

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): src/motors/operators/movement_operator.py

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): src/motors/operators/__init__.py

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): src/motors/utils/motor_constants.py

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): src/motors/utils/__init__.py

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): pipeline02/capture_vision_debug.py

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): pipeline02/main.py

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): pipeline4/capture_vision_debug.py

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): pipeline4/main.py

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): ultrasonic/operators/__init__.py

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): ultrasonic/utils/__init__.py

### Community 88 - "Community 88"
Cohesion: 1.0
Nodes (1): test-robot/deploy

### Community 89 - "Community 89"
Cohesion: 1.0
Nodes (1): Capture Frame with Bounding Boxes

### Community 90 - "Community 90"
Cohesion: 1.0
Nodes (1): Capture Frame - Big Ball Detected

### Community 91 - "Community 91"
Cohesion: 1.0
Nodes (1): Capture Frame - Bright/Debug

### Community 92 - "Community 92"
Cohesion: 1.0
Nodes (1): Capture Frame - Small Ball Detected

### Community 93 - "Community 93"
Cohesion: 1.0
Nodes (1): Capture Frame - Pipeline v3

### Community 94 - "Community 94"
Cohesion: 1.0
Nodes (1): Direct Camera Capture

### Community 95 - "Community 95"
Cohesion: 1.0
Nodes (1): Raw V4L2 Camera Capture

### Community 96 - "Community 96"
Cohesion: 1.0
Nodes (1): Pipeline02 Vision Debug

### Community 97 - "Community 97"
Cohesion: 1.0
Nodes (1): Pipeline4 Vision Debug

## Knowledge Gaps
- **255 isolated node(s):** `Hardware + shims de visión del robot Turbopi.  Después de la migración a `visi`, `Clamp and truncate to int (toward zero).`, `Singleton lazy de HybridVisionService para los shims de compatibilidad.`, `Reemplaza al antiguo `HybridBallDetector`.      Expone la misma API que usaban`, `Devuelve (cx, cy, r) como la API vieja. Usa el tick más reciente.` (+250 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 25`** (4 nodes): `drive()`, `test_motors_raw.py`, `Test motores con nuevo mapeo.`, `stop()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (4 nodes): `pipeline_constants.py`, `pipeline_constants.py`, `pipeline_constants.py`, `Constantes de configuración para Pipeline 4 — rutina de disparo a portería.  V`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (3 nodes): `main()`, `diag_servo_direction.py`, `Diagnostico de direccion de mapeo servo.  Centra servos, espera deteccion, y m`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (3 nodes): `main()`, `diag_servo_map.py`, `Diagnostico rapido de mapeo servo-pelota.  Uso: uv run diag_servo_map.py  Ce`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (3 nodes): `main()`, `diag_yolo_hsv.py`, `yolo_detect()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `Paquete `motors` — control de motores y servos vía UART (/dev/ttyAMA0).  Punto`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `ultrasonic_constants.py`, `Constantes del sensor ultrasónico.  Fuente única de verdad para dirección I2C`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `tests/test_visual_servo_controller.py`, `src/chase/visual_servo_controller.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Ambas ruedas avanzan a la misma velocidad.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Ambas ruedas retroceden a la misma velocidad.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Giro a la izquierda: rueda izquierda atrás, derecha adelante.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Giro a la derecha: rueda izquierda adelante, derecha atrás.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Ambas ruedas detenidas.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Crea un DTO sin lectura válida (``distance_mm=None``).          Se usa como fa`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Ancho real del frame (tras resolver el backend de cámara).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Construye un BallDto a partir de la salida cruda del operador HSV.          El`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Snapshot vacío (cuando aún no hay frame o todo falla).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Ancho real del frame (puede diferir del pedido si el backend no respeta size).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Acceso al VideoCapture crudo (para operadores que necesitan ajustar exposición).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Centroide X de la máscara si hay suficientes pixeles, si no None.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `LUT cacheada para la transformación de gamma (evita recomputar).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Recorta un patch central del candidato para validar que el hue es naranja.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Descarta candidatos en la franja superior ruidosa o pegados al borde.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Snapshot vacío con la estructura completa (campos null/[]).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Entrada: dict devuelto por `YoloInferenceOperator.get_latest_output()`.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Índices referenciados desde `/dev/v4l/by-id/*` (USB UVC).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Devuelve índices plausibles de cámara, USB primero, CSI-subdev filtrados.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Prueba en orden todos los /dev/videoN hasta dar con uno que entregue frames.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Fija exposición manual para webcams V4L2 (estabiliza el brillo).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Devuelve `(cap, frame_width_real, exposure)` o `(None, 0, 0)` si falla.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Crea una sesión ONNX Runtime validando que el archivo existe.          Si `mod`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `scripts/cal_motors.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `scripts/test_motors_raw.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `src/motors/motor_service.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `src/motors/dto/wheel_dto.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `src/motors/dto/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `src/motors/exceptions/motor_exception.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `src/motors/exceptions/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `src/motors/operators/burst_operator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `src/motors/operators/differential_operator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `src/motors/operators/movement_operator.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `src/motors/operators/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `src/motors/utils/motor_constants.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `src/motors/utils/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `pipeline02/capture_vision_debug.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `pipeline02/main.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `pipeline4/capture_vision_debug.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `pipeline4/main.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `ultrasonic/operators/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `ultrasonic/utils/__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 88`** (1 nodes): `test-robot/deploy`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 89`** (1 nodes): `Capture Frame with Bounding Boxes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 90`** (1 nodes): `Capture Frame - Big Ball Detected`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 91`** (1 nodes): `Capture Frame - Bright/Debug`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 92`** (1 nodes): `Capture Frame - Small Ball Detected`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 93`** (1 nodes): `Capture Frame - Pipeline v3`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 94`** (1 nodes): `Direct Camera Capture`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 95`** (1 nodes): `Raw V4L2 Camera Capture`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 96`** (1 nodes): `Pipeline02 Vision Debug`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 97`** (1 nodes): `Pipeline4 Vision Debug`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `HybridVisionService` connect `Vision DTOs and Commands` to `Main Controller and Bus Interface`, `Vision Pipeline Output and Images`, `Vision Service Configuration`, `Motor Service and Serial Protocol`, `Hardware Shim Compatibility Layer`, `Pipeline02 Advance Operator`, `Differential Operator and Wheel DTO`, `Image Calibration (Exposure)`?**
  _High betweenness centrality (0.285) - this node is a cross-community bridge._
- **Why does `main()` connect `Motor Service and Serial Protocol` to `Vision DTOs and Commands`, `Pipeline Operators (Advance, Align, Push)`?**
  _High betweenness centrality (0.188) - this node is a cross-community bridge._
- **Why does `Pipeline4Service` connect `Pipeline Operators (Advance, Align, Push)` to `Pipeline4 Push Operator`, `Motor Service and Serial Protocol`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Are the 20 inferred relationships involving `HybridVisionService` (e.g. with `DetectVisionCommand` and `VisionConfigCommand`) actually correct?**
  _`HybridVisionService` has 20 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Hardware + shims de visión del robot Turbopi.  Después de la migración a `visi`, `Clamp and truncate to int (toward zero).`, `Singleton lazy de HybridVisionService para los shims de compatibilidad.` to the rest of the system?**
  _255 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Vision DTOs and Commands` be split into smaller, more focused modules?**
  _Cohesion score 0.03 - nodes in this community are weakly interconnected._
- **Should `Pipeline Operators (Advance, Align, Push)` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._