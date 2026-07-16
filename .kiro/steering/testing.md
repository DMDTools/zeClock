---
inclusion: auto
---

# Testing Conventions

## Running Tests

Always run the full CI check before committing:

```bash
make test
```

This runs, in order:
1. **pytest** - unit and integration tests
2. **flake8** - linting
3. **mypy** - type checking
4. **black** - formatting check (--check mode)

## Test Framework

- **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`)
- Tests directory: `tests/`
- Async test functions are detected and run automatically (no `@pytest.mark.asyncio` needed)

## Writing Tests

- Place tests in `tests/` mirroring the source structure
- Use `pytest` fixtures for shared setup
- For async code, just write `async def test_...` - pytest-asyncio handles it
- Use `hypothesis` for property-based testing where appropriate
- Mark slow tests with `@pytest.mark.slow`

## Test Commands

```bash
# Full CI suite (recommended before any commit)
make test

# Just pytest
uv run --extra dev pytest tests/

# Specific test file
uv run --extra dev pytest tests/test_overlay.py

# With verbose output
uv run --extra dev pytest tests/ -v

# Skip slow tests
uv run --extra dev pytest tests/ -m "not slow"
```

## What to Test

- All public API functions and methods
- Plugin `render_frame()` output (correct dimensions, mode)
- Backend protocol serialization
- Binary format parsing (fnt, scn readers)
- Overlay compositing and upscaling algorithms
- Error handling paths (timeouts, connection failures)
