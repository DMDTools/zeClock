---
inclusion: auto
---

# Project Overview

**zeClock** is a smart DMD clock for ZeDMD hardware (ESP32/Teensy RGB LED panels) with an extensible plugin system. Inspired by the DotClk project, it renders time and animations on 128x32 or 256x64 pixel displays.

## Key Facts

- **Language**: Python 3.9+
- **Package manager**: pip / uv, setuptools build backend
- **Entry point**: `zeclock.clock:main` (exposed as `zeclock` CLI command)
- **License**: MIT

## Essential Commands

| Command | Description |
|---------|-------------|
| `make test` | Full CI suite: pytest + flake8 + mypy + black |
| `make dev-start-virtual` | Start virtual DMD (128x32, browser preview) |
| `make dev-start-virtual-hd` | Start virtual DMD in HD (256x64) |
| `make dev-stop` | Stop the virtual DMD |

## Dev Setup

```bash
pip install -e ".[dev]"
# Or with uv:
uv pip install -e ".[dev]"
```

## Project Structure (key directories)

```
zeclock/           # Main package
  clock.py         # Main async loop and CLI entry point
  overlay.py       # Bitmap blending, masking, pixel-art upscaling
  backends/        # DMDBackend ABC + ZeDMD/dmdserver implementations
  plugins/         # Plugin system (ClockPlugin ABC + built-in plugins)
  readers/         # Binary .fnt/.scn format parsers
  resources/       # Bundled fonts
  remote/          # MQTT + REST API remote control
tests/             # pytest test suite
scripts/           # Dev utilities (virtual-dmd, font generators)
docs/              # Architecture and plugin authoring docs
```

## Configuration

- Runtime config: `~/.zeclock/config/zeclock.ini` (INI format)
- Plugin config: `~/.zeclock/config/plugins.yaml` (YAML)
- CLI arguments always override config file values

## Documentation

- `CONTRIBUTING.md` - Development setup and code conventions
- `docs/architecture.md` - Full architecture documentation
- `docs/tech.md` - Technical stack details
- `docs/plugin_authoring.md` - Plugin development guide
