# zeClock — NAS deployment & local dev
# Usage: make nas-deploy | make nas-stop | make dev-start | make dev-stop

NAS_HOST     := nas
NAS_DIR      := ~/zeclock
COMPOSE      := /usr/local/bin/docker-compose
NAS_IP       := 192.168.0.50
COLOR        ?= auto

# Files to exclude from sync
EXCLUDES := --exclude='.git' --exclude='.venv' --exclude='.hypothesis' \
            --exclude='.pytest_cache' --exclude='__pycache__' \
            --exclude='*.egg-info' --exclude='build' \
            --exclude='dmd-simulator' --exclude='libdmdutil.src' \
            --exclude='.amazonq' --exclude='.kiro'

.PHONY: help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# NAS targets
# ==============================================================================

nas-sync: ## Sync code + config to NAS
	@echo "📤 Syncing to $(NAS_HOST):$(NAS_DIR)..."
	@cp -r ~/.zeclock/config deploy/nas/zeclock-config 2>/dev/null || true
	@tar czf - $(EXCLUDES) -C . . | ssh $(NAS_HOST) "mkdir -p $(NAS_DIR) && tar xzf - -C $(NAS_DIR)"
	@echo "✅ Synced"

nas-build: nas-sync ## Sync + rebuild zeclock container on NAS
	@echo "🔨 Building zeclock container..."
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) build zeclock"
	@echo "✅ Built"

nas-deploy: nas-build ## Full deploy: sync, build, restart (sequenced)
	@echo "🚀 Restarting dmdserver..."
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) up -d --force-recreate dmdserver"
	@echo "⏳ Waiting for ZeDMD..."
	@ssh $(NAS_HOST) "for i in \$$(seq 1 30); do \
		if $(COMPOSE) -f $(NAS_DIR)/deploy/nas/docker-compose.yml logs dmdserver 2>&1 | grep -q 'ZeDMD.*found'; then \
			echo '✅ ZeDMD connected'; break; \
		fi; \
		sleep 1; \
	done"
	@echo "🚀 Starting zeclock..."
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) up -d --force-recreate zeclock"
	@echo "✅ Deployed and running"

nas-start: ## Start containers on NAS (waits for dmdserver to find ZeDMD)
	@echo "▶️  Starting dmdserver..."
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) up -d dmdserver"
	@echo "⏳ Waiting for dmdserver to find ZeDMD..."
	@ssh $(NAS_HOST) "for i in \$$(seq 1 30); do \
		if $(COMPOSE) -f $(NAS_DIR)/deploy/nas/docker-compose.yml logs dmdserver 2>&1 | grep -q 'ZeDMD.*found'; then \
			echo '✅ ZeDMD connected'; break; \
		fi; \
		sleep 1; \
	done"
	@echo "▶️  Starting zeclock..."
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) up -d zeclock"
	@echo "✅ Running"

nas-stop: ## Stop all containers (releases ZeDMD connection)
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) down"
	@echo "🛑 Stopped"

nas-restart: ## Restart zeclock client only (keeps dmdserver running)
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) restart zeclock"
	@echo "🔄 Restarted"

nas-logs: ## Tail logs from both containers on NAS
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) logs --tail 30 -f"

nas-logs-clock: ## Tail zeclock logs on NAS
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) logs --tail 30 -f zeclock"

nas-logs-server: ## Tail dmdserver logs on NAS
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) logs --tail 30 -f dmdserver"

nas-status: ## Show container status on NAS
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) ps"

nas-config: ## Push local config to NAS and restart zeclock
	@echo "⚙️  Syncing config..."
	@cp -r ~/.zeclock/config deploy/nas/zeclock-config
	@tar czf - -C deploy/nas/zeclock-config . | ssh $(NAS_HOST) "tar xzf - -C $(NAS_DIR)/deploy/nas/zeclock-config"
	@ssh $(NAS_HOST) "cd $(NAS_DIR)/deploy/nas && $(COMPOSE) restart zeclock"
	@echo "✅ Config updated, zeclock restarted"

nas-update-dmdserver: ## Rebuild dmdserver image locally and push to NAS
	@echo "🔧 Building dmdserver image locally..."
	docker build -t zeclock-dmdserver -f deploy/nas/Dockerfile.dmdserver deploy/nas/
	@echo "📤 Pushing image to NAS..."
	docker save zeclock-dmdserver | gzip | ssh $(NAS_HOST) "/usr/local/bin/docker load"
	@echo "✅ dmdserver image updated. Run 'make nas-deploy' to restart."

# ==============================================================================
# Local dev targets (runs dmdserver + zeclock locally)
# ==============================================================================

dev-start: ## Start dmdserver + zeclock locally (real ZeDMD)
	@scripts/dev-start.sh $(COLOR)

dev-start-virtual: ## Start dmdserver (no display) + zeclock locally (for code testing)
	@scripts/dev-start.sh $(COLOR) virtual

dev-stop: ## Stop local dmdserver + zeclock
	@scripts/dev-stop.sh

dev-logs: ## Show local zeclock output (just re-run dev-start in foreground)
	@echo "ℹ️  Local dev runs in foreground — use dev-start and watch stdout"

# ==============================================================================
# Common
# ==============================================================================

test: ## Run tests locally
	uv run --extra dev pytest tests/ -x -q
