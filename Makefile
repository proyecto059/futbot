# ============================================================
# FutbotMX v2 — Makefile de desarrollo
# ============================================================
# Uso:
#   make install     — instala dependencias con uv
#   make run-r1      — corre como robot1 (servidor)
#   make run-r2      — corre como robot2 (cliente)
#   make run-solo    — corre sin WebSocket (modo solo)
#   make test        — ejecuta los tests
#   make lint        — revisa sintaxis de todos los .py
#   make deploy-r1   — despliega al robot1 por rsync+SSH
#   make deploy-r2   — despliega al robot2 por rsync+SSH
# ============================================================

# ── Configuración de deploy ───────────────────────────────────
ROBOT1_IP  ?= 192.168.22.17
ROBOT2_IP  ?= 192.168.22.47
ROBOT_USER ?= pi
ROBOT_PATH ?= ~/futbot-v2

# ── Instalación ───────────────────────────────────────────────
.PHONY: install
install:
	@echo "📦 Instalando dependencias con uv..."
	uv sync

# ── Ejecución local ───────────────────────────────────────────
.PHONY: run-r1
run-r1:
	ROBOT_ID=robot1 PEER_IP=$(ROBOT2_IP) WS_ENABLED=1 ULTRASONIC=0 \
	  uv run src/main.py

.PHONY: run-r2
run-r2:
	ROBOT_ID=robot2 PEER_IP=$(ROBOT1_IP) WS_ENABLED=1 ULTRASONIC=0 \
	  uv run src/main.py

.PHONY: run-solo
run-solo:
	WS_ENABLED=0 ULTRASONIC=0 uv run src/main.py

# ── Tests ─────────────────────────────────────────────────────
.PHONY: test
test:
	uv run pytest tests/ -v

.PHONY: test-robot-tests
test-robot-tests:
	cd test-robot && uv run pytest tests/ -v

# ── Lint ──────────────────────────────────────────────────────
.PHONY: lint
lint:
	@echo "🔍 Revisando sintaxis..."
	@find src tests -name "*.py" | while read f; do \
	  python3 -m py_compile "$$f" && echo "  ✅ $$f" || echo "  ❌ $$f"; \
	done

# ── Deploy a RPi via rsync ────────────────────────────────────
.PHONY: deploy-r1
deploy-r1:
	@echo "🚀 Desplegando a Robot 1 ($(ROBOT1_IP))..."
	rsync -avz --exclude='.git' --exclude='__pycache__' \
	  --exclude='*.pyc' --exclude='.venv' --exclude='uv.lock' \
	  ./ $(ROBOT_USER)@$(ROBOT1_IP):$(ROBOT_PATH)/
	@echo "✅ Deploy a Robot 1 completado"
	@echo "   Para correr: ssh $(ROBOT_USER)@$(ROBOT1_IP) 'cd $(ROBOT_PATH) && uv sync && ROBOT_ID=robot1 PEER_IP=$(ROBOT2_IP) uv run src/main.py'"

.PHONY: deploy-r2
deploy-r2:
	@echo "🚀 Desplegando a Robot 2 ($(ROBOT2_IP))..."
	rsync -avz --exclude='.git' --exclude='__pycache__' \
	  --exclude='*.pyc' --exclude='.venv' --exclude='uv.lock' \
	  ./ $(ROBOT_USER)@$(ROBOT2_IP):$(ROBOT_PATH)/
	@echo "✅ Deploy a Robot 2 completado"
	@echo "   Para correr: ssh $(ROBOT_USER)@$(ROBOT2_IP) 'cd $(ROBOT_PATH) && uv sync && ROBOT_ID=robot2 PEER_IP=$(ROBOT1_IP) uv run src/main.py'"

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

# ── Limpieza ──────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "🧹 Limpieza completada"
