import asyncio
import json
import websockets

from communication.communication_gateway import CommunicationGateway
from vision.vision_service import VisionService

# ─── Configuración ────────────────────────────────────────────────────────────
# Cambia ROBOT_ID a "robot2" en el segundo robot
ROBOT_ID  = "robot1"       # "robot1" (servidor) | "robot2" (cliente)
PEER_IP   = "192.168.10.12"  # IP del robot opuesto en competencia
#PEER_IP  = "192.168.22.47"  # IP para pruebas con RPi3
PORT      = 8765
IS_SERVER = ROBOT_ID == "robot1"
# ──────────────────────────────────────────────────────────────────────────────

gateway = CommunicationGateway()
vision  = VisionService()


def ejecutar_rol(rol: str):
    """
    Ejecuta la lógica de movimiento según el rol asignado.
    TODO: integrar con controladores de motores / ROS2 cmd_vel
    """
    print(f"  🤖 [{ROBOT_ID}] Ejecutando rol: {rol}")


# ─── Modo Servidor — Robot 1 ──────────────────────────────────────────────────
async def run_server():
    async def handler(websocket):
        print("✅ Robot 2 conectado")
        try:
            async for raw_msg in websocket:
                # Actualizar estado local antes de procesar
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


# ─── Modo Cliente — Robot 2 ───────────────────────────────────────────────────
async def run_client():
    uri = f"ws://{PEER_IP}:{PORT}"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                print(f"✅ [{ROBOT_ID}] Conectado a Robot 1 en {uri}")

                while True:
                    estado = json.dumps({
                        "pos": vision.obtener_posicion(),
                        "ve_pelota": vision.detectar_pelota()
                    })
                    await ws.send(estado)

                    respuesta = json.loads(await ws.recv())

                    if "error" in respuesta:
                        print(f"⚠️  Error del servidor: {respuesta['error']}")
                    else:
                        mi_rol = respuesta.get(ROBOT_ID, "espera")
                        print(f"  📡 Roles recibidos: {respuesta}")
                        ejecutar_rol(mi_rol)

                    await asyncio.sleep(0.1)  # 10 Hz

        except Exception as e:
            print(f"⚠️  Desconectado, reintentando en 2s... ({e})")
            await asyncio.sleep(2)


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 FutbotMX — Iniciando como {'SERVIDOR' if IS_SERVER else 'CLIENTE'}")
    asyncio.run(run_server() if IS_SERVER else run_client())
