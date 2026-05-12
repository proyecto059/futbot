"""ApManager — gestiona el Access Point WiFi en runtime.

Solo se usa en robot1 (servidor). Arranca hostapd y dnsmasq antes de
que WsRunner comience a escuchar conexiones WebSocket, y los detiene
al cerrar.

Requiere entrada en sudoers instalada por setup_ap.sh:
    pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd, ...

Flujo normal::

    ap = ApManager()
    ap.start()          # sudo systemctl start hostapd dnsmasq
                        # espera a que wlan0 tenga 192.168.10.1
    # ... WsRunner escuchando ...
    ap.stop()           # sudo systemctl stop hostapd dnsmasq

Modo simulación (sin hardware, p.ej. en laptop):
    ap = ApManager(simulate=True)
    ap.start()          # no hace nada real, solo logea
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import time

log = logging.getLogger("turbopi.communication.ap_manager")

# IP del AP — debe coincidir con netplan-robot1.yaml y dnsmasq-ap.conf
AP_IP            = "192.168.10.1"
AP_IFACE         = "wlan0"
AP_READY_TIMEOUT = 15.0   # segundos máximos esperando a que suba la interfaz
AP_READY_POLL    = 0.5    # intervalo de polling


class ApManager:
    """Arranca y detiene hostapd + dnsmasq via systemctl.

    Args:
        simulate: Si True, no ejecuta comandos reales de sistema.
                  Útil para tests y desarrollo en laptop.
    """

    def __init__(self, simulate: bool = False) -> None:
        self._simulate = simulate
        self._started  = False

        if not simulate:
            self._check_prerequisites()

    # ── API pública ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Arranca hostapd y dnsmasq, espera a que el AP esté listo.

        Raises:
            RuntimeError: Si los servicios no arrancan o el AP no levanta
                          en AP_READY_TIMEOUT segundos.
        """
        if self._started:
            log.warning("event=ap_already_started — ignorando segunda llamada")
            return

        log.info("event=ap_starting iface=%s ip=%s", AP_IFACE, AP_IP)

        if self._simulate:
            log.info("event=ap_simulate_start — modo simulación activo")
            self._started = True
            return

        self._systemctl("start", "hostapd")
        self._systemctl("start", "dnsmasq")

        self._wait_for_ap()
        self._started = True
        log.info("event=ap_ready ip=%s", AP_IP)

    def stop(self) -> None:
        """Detiene hostapd y dnsmasq."""
        if not self._started:
            return

        log.info("event=ap_stopping")

        if self._simulate:
            log.info("event=ap_simulate_stop")
            self._started = False
            return

        self._systemctl("stop", "dnsmasq")
        self._systemctl("stop", "hostapd")
        self._started = False
        log.info("event=ap_stopped")

    @property
    def is_running(self) -> bool:
        return self._started

    # ── Internos ─────────────────────────────────────────────────────────

    def _systemctl(self, action: str, service: str) -> None:
        """Ejecuta `sudo systemctl <action> <service>` y valida el resultado."""
        cmd = ["sudo", "systemctl", action, service]
        log.debug("event=systemctl cmd=%s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"systemctl {action} {service} falló "
                f"(rc={result.returncode}): {result.stderr.strip()}"
            )

    def _wait_for_ap(self) -> None:
        """Espera hasta que wlan0 tenga la IP del AP asignada.

        Hace polling de `ip addr show wlan0` hasta que aparece AP_IP
        o se agota el timeout.
        """
        deadline = time.monotonic() + AP_READY_TIMEOUT
        log.info(
            "event=ap_wait_ready timeout=%.0fs ip=%s",
            AP_READY_TIMEOUT, AP_IP,
        )

        while time.monotonic() < deadline:
            if self._iface_has_ip(AP_IFACE, AP_IP):
                return
            time.sleep(AP_READY_POLL)

        raise RuntimeError(
            f"Timeout esperando AP: {AP_IFACE} no tiene {AP_IP} "
            f"después de {AP_READY_TIMEOUT}s. "
            f"Verifica que setup_ap.sh se ejecutó correctamente."
        )

    @staticmethod
    def _iface_has_ip(iface: str, expected_ip: str) -> bool:
        """Devuelve True si la interfaz tiene la IP esperada asignada."""
        try:
            result = subprocess.run(
                ["ip", "addr", "show", iface],
                capture_output=True, text=True,
            )
            return expected_ip in result.stdout
        except Exception:
            return False

    @staticmethod
    def _check_prerequisites() -> None:
        """Verifica que hostapd y dnsmasq estén instalados."""
        missing = [
            svc for svc in ("hostapd", "dnsmasq")
            if shutil.which(svc) is None
        ]
        if missing:
            raise RuntimeError(
                f"Servicios no encontrados: {missing}. "
                f"Ejecuta primero: sudo bash scripts/setup_ap.sh"
            )

    # ── Context manager (uso opcional) ───────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()