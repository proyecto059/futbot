# ============================================================
# FutbotMX v2 — Makefile de desarrollo y deploy
# ============================================================

ROBOT1_IP  ?= 192.168.22.17
ROBOT2_IP  ?= 192.168.22.47
ROBOT_USER ?= pi
ROBOT_PATH ?= ~/futbot-v2

# IPs de la red del partido (AP)
AP_ROBOT1_IP = 192.168.10.1
AP_ROBOT2_IP = 192.168.10.12

# ── Instalación ───────────────────────────────────────────────
.PHONY: install
install:
	@echo "📦 Instalando dependencias Python con uv..."
	uv sync

# ── Ejecución local (sin AP, sin hardware) ────────────────────
.PHONY: run-solo
run-solo:
	WS_ENABLED=0 ULTRASONIC=0 uv run src/main.py

# ── Ejecución con AP simulado (2 terminales en laptop) ────────
.PHONY: run-r1-sim
run-r1-sim:
	ROBOT_ID=robot1 PEER_IP=$(AP_ROBOT2_IP) WS_ENABLED=1 \
	  ULTRASONIC=0 SIMULATE_AP=1 uv run src/main.py

.PHONY: run-r2-sim
run-r2-sim:
	ROBOT_ID=robot2 PEER_IP=$(AP_ROBOT1_IP) WS_ENABLED=1 \
	  ULTRASONIC=0 SIMULATE_AP=1 uv run src/main.py

# ── Ejecución en producción (RPi con AP real) ─────────────────
.PHONY: run-r1
run-r1:
	ROBOT_ID=robot1 PEER_IP=$(AP_ROBOT2_IP) WS_ENABLED=1 \
	  uv run src/main.py

.PHONY: run-r2
run-r2:
	ROBOT_ID=robot2 PEER_IP=$(AP_ROBOT1_IP) WS_ENABLED=1 \
	  uv run src/main.py

# ── Tests ─────────────────────────────────────────────────────
.PHONY: test
test:
	uv run pytest tests/ -v

.PHONY: lint
lint:
	@echo "🔍 Revisando sintaxis..."
	@find src tests -name "*.py" | while read f; do \
	  python3 -m py_compile "$$f" && echo "  ✅ $$f" || echo "  ❌ $$f"; \
	done

# ── Provisioning en las RPi (primera vez) ─────────────────────
.PHONY: provision-r1
provision-r1: deploy-r1
	@echo "🔧 Provisionando robot1 (AP)..."
	ssh $(ROBOT_USER)@$(ROBOT1_IP) \
	  'cd $(ROBOT_PATH) && sudo bash scripts/setup_ap.sh'

.PHONY: provision-r2
provision-r2: deploy-r2
	@echo "🔧 Provisionando robot2 (cliente WiFi)..."
	ssh $(ROBOT_USER)@$(ROBOT2_IP) \
	  'cd $(ROBOT_PATH) && sudo bash scripts/setup_client.sh'

# ── Deploy via rsync ──────────────────────────────────────────
.PHONY: deploy-r1
deploy-r1:
	@echo "🚀 Desplegando a Robot 1 ($(ROBOT1_IP))..."
	rsync -avz --exclude='.git' --exclude='__pycache__' \
	  --exclude='*.pyc' --exclude='.venv' --exclude='uv.lock' \
	  ./ $(ROBOT_USER)@$(ROBOT1_IP):$(ROBOT_PATH)/
	@echo "✅ Robot 1 — para correr:"
	@echo "   ssh $(ROBOT_USER)@$(ROBOT1_IP)"
	@echo "   cd $(ROBOT_PATH) && uv sync"
	@echo "   ROBOT_ID=robot1 PEER_IP=$(AP_ROBOT2_IP) uv run src/main.py"

.PHONY: deploy-r2
deploy-r2:
	@echo "🚀 Desplegando a Robot 2 ($(ROBOT2_IP))..."
	rsync -avz --exclude='.git' --exclude='__pycache__' \
	  --exclude='*.pyc' --exclude='.venv' --exclude='uv.lock' \
	  ./ $(ROBOT_USER)@$(ROBOT2_IP):$(ROBOT_PATH)/
	@echo "✅ Robot 2 — para correr:"
	@echo "   ssh $(ROBOT_USER)@$(ROBOT2_IP)"
	@echo "   cd $(ROBOT_PATH) && uv sync"
	@echo "   ROBOT_ID=robot2 PEER_IP=$(AP_ROBOT1_IP) uv run src/main.py"

.PHONY: deploy-all
deploy-all: deploy-r1 deploy-r2
	@echo "✅ Desplegado en ambos robots"

# ── SSH shortcuts ─────────────────────────────────────────────
.PHONY: ssh-r1
ssh-r1:
	ssh $(ROBOT_USER)@$(ROBOT1_IP)

.PHONY: ssh-r2
ssh-r2:
	ssh $(ROBOT_USER)@$(ROBOT2_IP)

# ── Estado del AP en robot1 ───────────────────────────────────
.PHONY: ap-status
ap-status:
	@echo "📡 Estado del AP en robot1 ($(ROBOT1_IP))..."
	ssh $(ROBOT_USER)@$(ROBOT1_IP) \
	  'systemctl is-active hostapd dnsmasq && ip addr show wlan0'

# ── Limpieza ──────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "🧹 Limpieza completada"