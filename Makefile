# zeClock — Development Makefile
# Usage: make dev-start | make test | make format | make help
#
# Personal/deployment targets can be added in Makefile.local (gitignored).
# See Makefile.local.example for a template.

COLOR ?= auto

.PHONY: help

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Local dev targets
# ==============================================================================

dev-start: ## Start zeclock locally with auto backend (libzedmd → real ZeDMD)
	@scripts/dev-start.sh $(COLOR)

dev-start-virtual: ## Start zeclock in virtual mode (--backend dmdserver, DMD in browser)
	@scripts/dev-start.sh $(COLOR) virtual

dev-stop: ## Stop local zeclock + virtual-dmd
	@scripts/dev-stop.sh

dev-logs: ## Show local zeclock output (just re-run dev-start in foreground)
	@echo "ℹ️  Local dev runs in foreground — use dev-start and watch stdout"

# ==============================================================================
# Build targets
# ==============================================================================

build-libzedmd: ## Build libzedmd from source via Docker → ~/.zeclock/lib/
	@scripts/build-libzedmd.sh

# ==============================================================================
# Quality & CI
# ==============================================================================

test: ## Run tests + linter + type check + format check (same as CI)
	uv run --extra dev pytest tests/ -v --tb=short
	uv run --extra dev flake8 zeclock/ --max-line-length=120 --ignore=E501,W503,E203,F841
	uv run --extra dev mypy zeclock/
	uv run --extra dev black zeclock/ tests/

# ==============================================================================
# Include personal/deployment targets if available
# ==============================================================================

-include Makefile.local
