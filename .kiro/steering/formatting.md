# Code Formatting Rules

This project enforces code formatting with [black](https://black.readthedocs.io/).
CI will reject any pull request where `black --check` fails.

## Before Every Commit

Always run the formatter before committing changes:

```bash
uv run --extra dev black zeclock/ tests/
```

## Before Pushing

Double-check that formatting passes in check mode (this mirrors what CI runs):

```bash
uv run --extra dev black --check zeclock/ tests/
```

If this command exits with a non-zero status, run the formatter (without `--check`) and amend your commit.

## Notes

- Black is configured as a dev dependency in `pyproject.toml` (installed via `uv sync --extra dev`).
- The formatter targets both `zeclock/` (source) and `tests/` (test files).
- Do not add `# fmt: off` / `# fmt: on` markers unless absolutely necessary (e.g., alignment-sensitive lookup tables).
- If you add new top-level Python directories, include them in the black command above and in the CI workflow.
