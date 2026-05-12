"""tests/test_ap_manager.py — Tests de ApManager en modo simulación.

Verifica el ciclo de vida completo (start/stop, context manager, idempotencia)
sin tocar hardware ni systemctl reales.
"""

import pytest
from communication.ap_manager import ApManager


class TestApManagerSimulate:

    def test_start_stop_basico(self):
        ap = ApManager(simulate=True)
        assert not ap.is_running
        ap.start()
        assert ap.is_running
        ap.stop()
        assert not ap.is_running

    def test_start_idempotente(self):
        """Llamar start() dos veces no debe fallar."""
        ap = ApManager(simulate=True)
        ap.start()
        ap.start()   # segunda llamada — debe ser ignorada sin error
        assert ap.is_running
        ap.stop()

    def test_stop_sin_start_no_falla(self):
        """stop() antes de start() no debe lanzar excepción."""
        ap = ApManager(simulate=True)
        ap.stop()    # no debe explotar
        assert not ap.is_running

    def test_context_manager(self):
        """Usar ApManager como context manager arranca y detiene."""
        with ApManager(simulate=True) as ap:
            assert ap.is_running
        assert not ap.is_running

    def test_context_manager_stop_en_excepcion(self):
        """El context manager llama stop() incluso si hay excepción."""
        ap = ApManager(simulate=True)
        try:
            with ap:
                assert ap.is_running
                raise ValueError("error de prueba")
        except ValueError:
            pass
        assert not ap.is_running

    def test_multiples_ciclos(self):
        """start/stop repetido funciona correctamente."""
        ap = ApManager(simulate=True)
        for _ in range(3):
            ap.start()
            assert ap.is_running
            ap.stop()
            assert not ap.is_running


class TestApManagerPrerequisitos:

    def test_simulate_salta_prerequisites(self):
        """En modo simulate no verifica si hostapd está instalado."""
        ap = ApManager(simulate=True)
        # Si llegamos aquí sin error en un entorno sin hostapd, el test pasa
        assert ap is not None

    def test_iface_has_ip_formato(self):
        """_iface_has_ip maneja interfaces inexistentes sin explotar."""
        result = ApManager._iface_has_ip("wlan99_no_existe", "192.168.10.1")
        assert result is False

    def test_iface_in_subnet_formato(self):
        """_iface_in_subnet con interfaz inexistente devuelve False."""
        from communication.ws_runner import WsRunner
        result = WsRunner._iface_in_subnet("wlan99_no_existe", "192.168.10.")
        assert result is False