"""Helpers puros: constantes, backend de cámara y fábricas YOLO."""

__all__ = ["CameraBackendResolver", "OnnxSessionFactory", "YoloBackendFactory"]


def __getattr__(name: str):
    if name == "CameraBackendResolver":
        from vision.utils.camera_backend_resolver import CameraBackendResolver

        return CameraBackendResolver
    if name == "OnnxSessionFactory":
        from vision.utils.onnx_session_factory import OnnxSessionFactory

        return OnnxSessionFactory
    if name == "YoloBackendFactory":
        from vision.utils.yolo_backend_factory import YoloBackendFactory

        return YoloBackendFactory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
