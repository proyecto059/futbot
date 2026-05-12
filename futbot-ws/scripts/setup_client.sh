#!/usr/bin/env bash
# =============================================================
# setup_client.sh — Provisioning de robot2 (cliente WiFi)
#
# Ejecutar UNA SOLA VEZ en robot2 con sudo:
#     sudo bash scripts/setup_client.sh
#
# Qué hace:
#   1. Instala wpasupplicant si no está
#   2. Escribe netplan para que wlan0 se conecte al AP oculto
#   3. Aplica netplan — wlan0 pasa a buscar SSID RPI_INET
#
# Idempotente: se puede correr varias veces sin romper nada.
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$PROJECT_DIR/config"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[setup_client]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup_client]${NC} $*"; }
err()  { echo -e "${RED}[setup_client] ERROR:${NC} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || err "Ejecuta con sudo: sudo bash scripts/setup_client.sh"

log "Iniciando provisioning de robot2 (cliente WiFi)..."

# ── 1. Instalar wpasupplicant ─────────────────────────────────
log "Verificando wpasupplicant..."
apt-get install -y wpasupplicant

# ── 2. Hostname ───────────────────────────────────────────────
# dnsmasq en robot1 asigna IP fija por hostname "robot2"
CURRENT_HOST=$(hostname)
if [[ "$CURRENT_HOST" != "robot2" ]]; then
    warn "Hostname actual: '$CURRENT_HOST'"
    warn "dnsmasq asigna IP fija a hostname 'robot2'."
    read -rp "  ¿Cambiar hostname a 'robot2'? [s/N]: " yn
    if [[ "$yn" =~ ^[Ss]$ ]]; then
        hostnamectl set-hostname robot2
        sed -i "s/127\.0\.1\.1.*/127.0.1.1\trobot2/" /etc/hosts
        log "  Hostname → robot2 ✅ (efectivo tras reinicio)"
    else
        warn "  Hostname no cambiado. La IP asignada será dinámica (no 192.168.10.12)."
    fi
fi

# ── 3. Netplan — wlan0 como cliente WiFi ─────────────────────
log "Aplicando netplan para wlan0 (cliente del AP)..."

if [[ -f /etc/netplan/60-futbot-client.yaml ]]; then
    cp /etc/netplan/60-futbot-client.yaml /etc/netplan/60-futbot-client.yaml.bak
    warn "Backup guardado en /etc/netplan/60-futbot-client.yaml.bak"
fi

cp "$CONFIG_DIR/netplan-robot2.yaml" /etc/netplan/60-futbot-client.yaml
chmod 600 /etc/netplan/60-futbot-client.yaml

netplan apply
log "  netplan apply ✅ — wlan0 buscará SSID RPI_INET (oculto)"

# ── 4. Verificación final ─────────────────────────────────────
log ""
log "=== Provisioning robot2 completado ==="
log ""
log "  wlan0       → cliente DHCP del AP RPI_INET"
log "  IP esperada → 192.168.10.12 (si hostname=robot2)"
log "  Gateway     → 192.168.10.1  (robot1)"
log ""
log "  El AP debe estar activo en robot1 para que wlan0 conecte."
log ""
log "  En producción:"
log "    ROBOT_ID=robot2 PEER_IP=192.168.10.1 uv run src/main.py"
log ""