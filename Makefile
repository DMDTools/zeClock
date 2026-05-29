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
# Local dev targets (runs dmdserver + zeclock locally)
# ==============================================================================

dev-start: ## Start dmdserver + zeclock locally (real ZeDMD)
	@scripts/dev-start.sh $(COLOR)

dev-start-virtual: ## Start zeclock in virtual mode (DMD rendered in browser, no physical display needed)
	@scripts/dev-start.sh $(COLOR) virtual

dev-stop: ## Stop local dmdserver + zeclock
	@scripts/dev-stop.sh

dev-logs: ## Show local zeclock output (just re-run dev-start in foreground)
	@echo "ℹ️  Local dev runs in foreground — use dev-start and watch stdout"

# ==============================================================================
# Quality & CI
# ==============================================================================

test: ## Run tests + linter + type check + format check (same as CI)
	uv run --extra dev pytest tests/ -v --tb=short
	uv run --extra dev flake8 zeclock/ --max-line-length=120 --ignore=E501,W503,E203,F841
	uv run --extra dev mypy zeclock/ --ignore-missing-imports
	uv run --extra dev black --check zeclock/ tests/

format: ## Auto-format code with black
	uv run --extra dev black zeclock/ tests/

# ==============================================================================
# Include personal/deployment targets if available
# ==============================================================================

-include Makefile.local
