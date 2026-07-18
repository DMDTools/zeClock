---
inclusion: auto
---

# Pre-commit Hooks

## Rule

Before committing any changes, **always run pre-commit hooks** on the staged files to catch formatting, linting, and type errors early.

## How to Run

```bash
# Run on all modified files (recommended before committing)
pre-commit run --all-files

# Or run only on staged files
pre-commit run
```

## What the hooks check

1. **Black** — Code formatting (target: py312)
2. **Flake8** — Linting on `zeclock/` (max-line-length=120, ignores: E501, W503, E203, F841)
3. **Mypy** — Type checking on `zeclock/` (ignore-missing-imports)

## Workflow

1. Make your code changes
2. Stage files with `git add`
3. Run `pre-commit run --all-files`
4. If any hook fails, fix the issues (Black will auto-fix formatting), re-stage, and re-run
5. Only commit once all hooks pass

## Configuration

Pre-commit config is at `#[[file:.pre-commit-config.yaml]]`
