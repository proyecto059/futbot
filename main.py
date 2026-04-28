import asyncio
import json
import socket
import shutil
import subprocess
import os
import signal
import websockets

from communication.communication_gateway import CommunicationGateway
from vision.vision_service import VisionService

# ─── Configuración ────────────────────────────────────────────────────────────
ROBOT_ID   = "robot1"           # "robot1" (RPI1) | "robot2" (RPI2)
PORT       = 8765
IS_SERVER  = ROBOT_ID == "robot1"
PEER_HOST  = "RPI2.local" if IS_SERVER else "RPI1.local"

NETPLAN_FILE   = "/etc/netplan/50-cloud-init.yaml"
NETPLAN_BACKUP = "/etc/netplan/50-cloud-init.yaml.bak"

# Solo Robot 2 necesita cambiar su red para conectarse al AP de Robot 1
NETPLAN_FUTBOT = """\
network:
  version: 2
  ethernets:
    eth0:
      optional: true
      dhcp4: true
  wifis:
    wlan0:
      optional: true
      dhcp4: true
      regulatory-domain: "MX"
      access-points:
        "RPI_INET":
          hidden: true
          auth:
            key-management: psk
            password: "futbot2025"
"""
# ──────────────────────────────────────────────────────────────────────────────

gateway = CommunicationGateway()
vision  = VisionService()


# ─── Gestión de Netplan — Solo Robot 2 ───────────────────────────────────────
def activar_red_futbot():
    """Guarda el netplan actual y activa la red RPI_INET — solo en cliente"""
    print("🔧 Guardando configuración de red actual...")
    shutil.copy2(NETPLAN_FILE, NETPLAN_BACKUP)

    print("🔧 Aplicando red FutbotMX (RPI_INET)...")
    with open(NETPLAN_FILE, "w") as f:
        f.write(NETPLAN_FUTBOT)

    subprocess.run(["sudo", "netplan", "apply"], check=True)
    print("✅ Red RPI_INET activa — esperando conexión...")
    import time
    time.sleep(5)

def restaurar_red():
    """Restaura el netplan original al terminar — solo en cliente"""
    if os.path.exists(NETPLAN_BACKUP):
        print("\n🔧 Restaurando configuración de red original...")
        shutil.copy2(NETPLAN_BACKUP, NETPLAN_FILE)
        subprocess.run(["sudo", "netplan", "apply"], check=True)
        os.remove(NETPLAN_BACKUP)
        print("✅ Red original restaurada")

def resolver_peer() -> str | None:
    """Resuelve el hostname del robot opuesto a IP"""
    try:
        ip = socket.gethostbyname(PEER_HOST)
        print(f"✅ {PEER_HOST} resuelto → {ip}")
        return ip
    except socket.gaierror:
        print(f"⚠️  No se pudo resolver {PEER_HOST}, reintentando...")
        return None


# ─── Rol del robot ────────────────────────────────────────────────────────────
def ejecutar_rol(rol: str):
    """
    Ejecuta comportamiento según el rol asignado.
    TODO: integrar con controladores de motores / ROS2 cmd_vel
    """
    print(f"  🤖 [{ROBOT_ID}] Ejecutando rol: {rol}")


# ─── Modo Servidor — Robot 1 (RPI1) ──────────────────────────────────────────
async def run_server():
    """
    Robot 1 no modifica netplan — ya tiene el AP configurado
    y su red está lista desde el arranque del sistema.
    """
    async def handler(websocket):
        print("✅ Robot 2 conectado")
        try:
            async for raw_msg in websocket:
                gateway.update_local_state(
                    pos=vision.obtener_posicion(),
                    ve_pelota=vision.detectar_pelota()
                )
                roles = await gateway.on_message(websocket, raw_msg)
                if roles:
                    ejecutar_rol(roles.robot1)
        except websockets.exceptions.ConnectionClosed:
            print("❌ Robot 2 desconectado")

    print(f"🚀 [{ROBOT_ID}] Servidor WebSocket escuchando en :{PORT}")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await asyncio.Future()


# ─── Modo Cliente — Robot 2 (RPI2) ───────────────────────────────────────────
async def run_client():
    """
    Robot 2 cambia su netplan para conectarse a RPI_INET,
    luego resuelve el hostname de Robot 1 y se conecta.
    Al terminar restaura su netplan original.
    """
    while True:
        try:
            ip = resolver_peer()
            if not ip:
                await asyncio.sleep(2)
                continue

            uri = f"ws://{ip}:{PORT}"
            async with websockets.connect(uri) as ws:
                print(f"✅ [{ROBOT_ID}] Conectado a {PEER_HOST}")
                while True:
                    estado = json.dumps({
                        "pos": vision.obtener_posicion(),
                        "ve_pelota": vision.detectar_pelota()
                    })
                    await ws.send(estado)
                    respuesta = json.loads(await ws.recv())
                    if "error" in respuesta:
                        print(f"⚠️  Error: {respuesta['error']}")
                    else:
                        mi_rol = respuesta.get(ROBOT_ID, "espera")
                        print(f"  📡 Roles: {respuesta}")
                        ejecutar_rol(mi_rol)
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"⚠️  Desconectado, reintentando en 2s... ({e})")
            await asyncio.sleep(2)


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    if IS_SERVER:
        # ── Robot 1: no toca netplan, solo levanta el servidor ──
        print(f"🤖 FutbotMX — Iniciando como SERVIDOR")
        try:
            asyncio.run(run_server())
        except KeyboardInterrupt:
            print("\n👋 Servidor detenido")

    else:
        # ── Robot 2: cambia netplan, corre cliente, restaura al salir ──
        def handle_exit(sig, frame):
            restaurar_red()
            exit(0)

        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)

        try:
            activar_red_futbot()
            print(f"🤖 FutbotMX — Iniciando como CLIENTE")
            asyncio.run(run_client())
        finally:
            restaurar_red()


if __name__ == "__main__":
    main()
