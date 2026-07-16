---
inclusion: auto
---

# Coding Style and Conventions

## Formatting and Linting

- **Black** for code formatting (default settings)
- **Flake8** for linting: `max-line-length=120`, ignore `E501,W503,E203,F841`
- **Mypy** for type checking (strict on `zeclock/` package)
- All code quality checks run together via `make test`

## Language

- All code, comments, docstrings, and documentation must be written in **English**

## Docstrings

- Use **Google-style** docstrings:

```python
def send_frame(self, image: Image.Image, buffered: bool = False) -> bool:
    """Send a frame to the display.

    Args:
        image: PIL RGB image to render.
        buffered: Whether to use buffered mode.

    Returns:
        True if the frame was sent successfully.
    """
```

## Import Ordering

1. Standard library (`import os`, `import asyncio`)
2. Third-party packages (`from PIL import Image`, `import aiohttp`)
3. Local imports (`from zeclock.overlay import upscale_2x`)

Alphabetical within each group. Separate groups with a blank line.

## Type Hints

- Use type hints for all function signatures
- Mypy runs in strict mode on the `zeclock/` package
- Use `from __future__ import annotations` when needed for forward references

## Naming Conventions

- Classes: `PascalCase` (e.g., `ClockPlugin`, `DMDBackend`)
- Functions/methods: `snake_case` (e.g., `render_frame`, `send_frame`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_WIDTH`, `FRAME_DELAY_MS`)
- Private methods: prefix with `_` (e.g., `_precompute_animation`)

## Async Patterns

- Use `async`/`await` for I/O operations
- Use `asyncio.create_task()` for background work
- Use `await asyncio.sleep(0)` for cooperative yielding in tight loops
- Use `threading.Lock` when sharing state between asyncio and background threads

## Dependencies

- **No NumPy** - all pixel operations use pure Python + Pillow for Raspberry Pi portability
- Keep production dependencies minimal (Pillow, PyYAML, aiohttp, colorama)
