---
inclusion: auto
---

# Pre-commit Hooks

## Rule

Before committing **and pushing** any changes, **always run pre-commit hooks** and ensure they pass. This is **mandatory** — never push code that hasn't passed all checks.

## How to Run

```bash
# Run on all modified files (MANDATORY before committing)
pre-commit run --all-files

# Or equivalently (if pre-commit is not installed, use the tools directly):
python -m black zeclock/ --check
python -m flake8 zeclock/ --max-line-length=120 --ignore=E501,W503,E203,F841
python -m mypy zeclock/ --ignore-missing-imports
```

## What the hooks check

1. **Black** — Code formatting (target: py312). Auto-fixes with `python -m black zeclock/`
2. **Flake8** — Linting on `zeclock/` (max-line-length=120, ignores: E501, W503, E203, F841)
3. **Mypy** — Type checking on `zeclock/` (ignore-missing-imports)

## Workflow

1. Make your code changes
2. Run `python -m black zeclock/` to auto-format
3. Run `python -m flake8 zeclock/ --max-line-length=120 --ignore=E501,W503,E203,F841` — fix any errors
4. Run `python -m mypy zeclock/ --ignore-missing-imports` — fix any type errors
5. Stage files with `git add`
6. Commit only once **all three checks pass with zero errors**
7. Optionally run `pytest tests/ -v --tb=short` to ensure no regressions

## Common Fixes

- **Black reformats**: just run `python -m black zeclock/` and re-stage
- **Flake8 unused import**: remove the import
- **Mypy missing return type**: add `-> None` or appropriate type annotation
- **Mypy Optional issues**: use `Optional[X]` or `X | None` syntax

## Configuration

Pre-commit config is at `#[[file:.pre-commit-config.yaml]]`
