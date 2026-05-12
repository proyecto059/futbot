"""Fábrica para crear `ort.InferenceSession` con la configuración del robot.

Centralizar la creación evita duplicar las opciones (grafo optimizado, threads,
ejecución secuencial, provider CPU) en cada sitio que necesite el modelo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import onnxruntime as ort

from vision.exceptions.yolo_model_not_found_exception import (
    YoloModelNotFoundException,
)
from vision.utils.vision_constants import (
    YOLO_INTER_OP_THREADS,
    YOLO_INTRA_OP_THREADS,
    resolve_yolo_model_path,
)


class OnnxSessionFactory:
    """Construye `ort.InferenceSession` listo para consumir por YoloInferenceOperator."""

    @staticmethod
    def create(model_path: Optional[Path] = None) -> ort.InferenceSession:
        """Crea una sesión ONNX Runtime validando que el archivo existe.

        Si `model_path` es None, se resuelve vía `resolve_yolo_model_path()`.
        Lanza `YoloModelNotFoundException` si el archivo no existe: mejor fallar
        temprano en __init__ del servicio que dentro del worker thread.
        """
        path = model_path or resolve_yolo_model_path()
        if not path.exists():
            raise YoloModelNotFoundException(
                f"YOLO model no encontrado. Se buscó en: {path}. "
                "Copia `model.onnx` a la raíz del proyecto o a `test-robot/`."
            )

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = YOLO_INTRA_OP_THREADS
        opts.inter_op_num_threads = YOLO_INTER_OP_THREADS
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        return ort.InferenceSession(
            str(path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )