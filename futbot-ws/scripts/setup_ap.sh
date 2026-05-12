#!/usr/bin/env bash
# =============================================================
# setup_ap.sh — Provisioning de robot1 (servidor AP)
#
# Ejecutar UNA SOLA VEZ en robot1 con sudo:
#     sudo bash scripts/setup_ap.sh
#
# Qué hace:
#   1. Instala hostapd y dnsmasq
#   2. Copia configs de FutbotMX a sus rutas del sistema
#   3. Escribe netplan para wlan0 con IP fija 192.168.10.1
#   4. Instala regla sudoers para que 'pi' arranque servicios sin contraseña
#   5. Desenmascara hostapd (Ubuntu lo trae enmascarado por defecto)
#   6. Deja los servicios DETENIDOS — Python los arranca en runtime
#
# Idempotente: se puede correr varias veces sin romper nada.
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[setup_ap]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup_ap]${NC} $*"; }
err()  { echo -e "${RED}[setup_ap] ERROR:${NC} $*" >&2; exit 1; }

# ── 0. Verificar que corre como root ─────────────────────────
[[ $EUID -eq 0 ]] || err "Ejecuta con sudo: sudo bash scripts/setup_ap.sh"

log "Iniciando provisioning de robot1 (AP)..."

# ── 1. Instalar paquetes ──────────────────────────────────────
log "Instalando hostapd y dnsmasq..."
apt-get update -qq
apt-get install -y hostapd dnsmasq

# ── 2. Desactivar dnsmasq del sistema (puede chocar con el nuestro)
log "Deteniendo servicios del sistema..."
systemctl stop dnsmasq   2>/dev/null || true
systemctl stop hostapd   2>/dev/null || true
# No los deshabilitamos — Python los controla en runtime

# ── 3. hostapd — desenmascara y copia config ──────────────────
log "Configurando hostapd..."
systemctl unmask hostapd

# Backup si ya existe una config
if [[ -f /etc/hostapd/hostapd.conf ]]; then
    cp /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.bak
    warn "Backup guardado en /etc/hostapd/hostapd.conf.bak"
fi

cp "$CONFIG_DIR/hostapd.conf" /etc/hostapd/hostapd.conf
chmod 600 /etc/hostapd/hostapd.conf

# Apuntar DAEMON_CONF al archivo de config
sed -i 's|^#\?DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
log "  hostapd.conf → /etc/hostapd/hostapd.conf ✅"

# ── 4. dnsmasq — copia config en drop-in ─────────────────────
log "Configurando dnsmasq..."

# Deshabilitar la config genérica para no interferir
if [[ -f /etc/dnsmasq.conf ]]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.bak
    warn "Backup guardado en /etc/dnsmasq.conf.bak"
fi

cp "$CONFIG_DIR/dnsmasq-ap.conf" /etc/dnsmasq.d/futbot-ap.conf
log "  dnsmasq-ap.conf → /etc/dnsmasq.d/futbot-ap.conf ✅"

# ── 5. Netplan — wlan0 con IP fija ───────────────────────────
log "Aplicando netplan para wlan0 (192.168.10.1)..."

# Backup si ya existe
if [[ -f /etc/netplan/60-futbot-ap.yaml ]]; then
    cp /etc/netplan/60-futbot-ap.yaml /etc/netplan/60-futbot-ap.yaml.bak
    warn "Backup guardado en /etc/netplan/60-futbot-ap.yaml.bak"
fi

cp "$CONFIG_DIR/netplan-robot1.yaml" /etc/netplan/60-futbot-ap.yaml
chmod 600 /etc/netplan/60-futbot-ap.yaml

netplan apply
log "  netplan apply ✅ — wlan0 tiene IP 192.168.10.1"

# ── 6. Sudoers — permisos mínimos para 'pi' ──────────────────
log "Instalando regla sudoers..."
cp "$CONFIG_DIR/sudoers-futbot" /etc/sudoers.d/futbot
chmod 440 /etc/sudoers.d/futbot

# Validar sintaxis antes de que sudo lo cargue
visudo -c -f /etc/sudoers.d/futbot || err "Error de sintaxis en sudoers-futbot"
log "  /etc/sudoers.d/futbot ✅"

# ── 7. Verificación final ─────────────────────────────────────
log ""
log "=== Provisioning robot1 completado ==="
log ""
log "  wlan0       → 192.168.10.1/24  (IP fija, hostapd en runtime)"
log "  SSID        → RPI_INET (oculto, WPA2)"
log "  DHCP range  → 192.168.10.10 - 192.168.10.50"
log "  robot2 IP   → 192.168.10.12 (fija por MAC/hostname)"
log ""
log "  Para arrancar el AP manualmente:"
log "    sudo systemctl start hostapd dnsmasq"
log ""
log "  En producción lo arranca automáticamente:"
log "    ROBOT_ID=robot1 PEER_IP=192.168.10.12 uv run src/main.py"
log ""