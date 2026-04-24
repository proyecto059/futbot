class VisionService:
    """
    Servicio de visión artificial.
    Por ahora retorna stubs para pruebas de conectividad.
    Se integrará con OpenCV + ROS2 en la siguiente etapa.
    """

    def detectar_pelota(self) -> bool:
        """
        Retorna True si el robot detecta la pelota en su cámara.
        TODO: integrar con OpenCV
        """
        return False

    def obtener_posicion(self) -> list:
        """
        Retorna la posición estimada del robot en el campo [x, y].
        TODO: integrar con odometría ROS2
        """
        return [0.0, 0.0]
