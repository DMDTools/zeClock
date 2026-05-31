# Contributing to zeClock

## Development Setup

```bash
git clone https://github.com/DMDTools/zeClock.git
cd zeClock
pip install -e ".[dev]"
```

## Running Tests

```bash
# Full test suite + linting + type checking (same as CI)
make test

# Or individually:
pytest tests/
flake8 zeclock/ --max-line-length=120 --ignore=E501,W503,E203,F841
mypy zeclock/
black zeclock/ tests/
```

## Development Mode (Virtual DMD)

For development without physical hardware:

```bash
# Standard resolution (128x32)
make dev-start-virtual

# HD resolution (256x64)
make dev-start-virtual-hd

# Stop
make dev-stop
```

This starts `scripts/virtual-dmd.py` which renders frames to a browser at http://localhost:8080 via WebSocket.

## Project Structure

```
zeClock/
├── zeclock/
│   ├── clock.py                 # Main asynchronous clock loop
│   ├── installer.py             # Runtime bootstrap (libzedmd & resources)
│   ├── backend_config.py        # BackendConfig dataclass and config file parsing
│   ├── overlay.py               # Bitmap blending, masking, and pixel-art upscaling
│   ├── backends/
│   │   ├── base.py              # DMDBackend abstract base class
│   │   ├── zedmd.py             # ZeDMDBackend (ctypes/libzedmd)
│   │   ├── dmdserver.py         # DMDServerBackend (TCP socket)
│   │   └── factory.py           # create_backend() factory function
│   ├── plugins/
│   │   ├── base.py              # ClockPlugin / PagedPlugin ABCs
│   │   ├── helpers.py           # PluginHelpers, ConfettiAnimation
│   │   ├── pinball_plugin.py    # Retro .scn animations
│   │   ├── pong_plugin.py       # Pong game with AI
│   │   ├── weather_plugin.py    # Open-Meteo weather
│   │   ├── stock_plugin.py      # Yahoo Finance stocks
│   │   ├── eyes_plugin.py       # Animated robot eyes
│   │   ├── gif_plugin.py        # Animated GIF player
│   │   └── weather_icons.py     # Pre-rendered emoji icons (SD + HD)
│   ├── readers/
│   │   ├── fnt_reader.py        # Binary .fnt bitmap font loader
│   │   └── scn_reader.py        # Binary .scn scene loader
│   └── resources/
│       ├── Fonts/               # Bundled bitmap fonts (SD + HD)
│       └── paths.py             # Resource path resolution
├── scripts/
│   ├── virtual-dmd.py           # Virtual DMD browser preview
│   ├── dev-start.sh             # Dev launcher
│   ├── generate_hd_fonts.py     # EPX font generator
│   └── gen_weather_icons.py     # Emoji icon generator
├── tests/                       # 489 tests
├── docs/
│   └── plugin_authoring.md      # Plugin development guide
├── config/
│   └── zeclock.ini              # Example configuration
└── pyproject.toml               # Package configuration
```

## Key Architecture Decisions

- **Backend abstraction**: `DMDBackend` ABC with factory pattern for ZeDMD (ctypes) and dmdserver (TCP)
- **Plugin system**: State machine (CLOCK_ONLY → PLUGIN_SELECT → PLUGIN_ACTIVE) with weighted random selection
- **HD support**: Auto-detection from hardware, pixel-art upscaling (EPX/hq2x/Scale3x) in `overlay.py`
- **Fonts**: Bundled in package, HD variants pre-generated with EPX, auto-selected based on display resolution
- **Background pre-computation**: Pinball and GIF plugins upscale frames in a daemon thread, serving them progressively

## Adding a New Upscaling Algorithm

All pixel-art upscaling lives in `zeclock/overlay.py`. To add a new algorithm:

1. Implement `def my_algo(img: Image.Image) -> Image.Image` in `overlay.py`
2. Add it to `upscale_2x()` dispatcher and `upscale_nx()` if applicable
3. Add the choice to `BackendConfig.upscale_mode` validation in `backend_config.py`
4. Add to CLI choices in `clock.py` (`--upscale`)
5. Export from `zeclock/plugins/__init__.py`

## Regenerating HD Fonts

After modifying the EPX algorithm or adding new SD fonts:

```bash
python scripts/generate_hd_fonts.py
```

This reads from `~/.zeclock/resources/Fonts/*.fnt` and writes `*_HD.fnt` variants.

## Regenerating Weather Icons

Requires `fonts-noto-color-emoji` installed:

```bash
sudo apt install fonts-noto-color-emoji
python scripts/gen_weather_icons.py
```

Generates both 16×16 (SD) and 32×32 (HD) icons into `zeclock/plugins/weather_icons.py`.

## Code Style

- **Black** for formatting (line length managed by black defaults)
- **Flake8** for linting (max-line-length=120, ignoring E501/W503/E203/F841)
- **Mypy** for type checking (strict on zeclock/ package)
- Docstrings: Google style
- Imports: stdlib → third-party → local, alphabetical within groups

## Writing Plugins

The complete plugin authoring guide lives at **[docs/plugin_authoring.md](docs/plugin_authoring.md)**. It covers everything from a minimal hello-world to advanced topics:

| Topic | What you'll learn |
|-------|-------------------|
| Getting Started | Minimal plugin in 20 lines |
| Plugin Interface | `ClockPlugin`, `PagedPlugin` ABCs |
| PluginHelpers API | Text rendering, icons, compositing, fonts |
| ConfettiAnimation | Reusable particle effects |
| Upscaling API | `upscale_2x`, `upscale_nx`, `hq2x`, `scale3x` |
| Configuration | `plugins.yaml`, frequency, settings |
| Lifecycle | Discovery → init → render → cleanup |
| Persistent State | Class-level state across activations |
| Cooperative Yielding | Clean break points (games, simulations) |
| Background Loading | Thread-based pre-computation pattern |
| Error Handling | Timeouts, retries, graceful degradation |
| Testing | Isolated test scripts, pytest patterns |
| Installation | User plugins directory, CLI activation |

### Quick reference

```bash
# Create your plugin
vim ~/.zeclock/plugins/my_plugin.py

# Test it
zeclock --plugins my-plugin

# List discovered plugins
zeclock --list-plugins
```

### Plugin directory

User plugins go in `~/.zeclock/plugins/`. Any `.py` file containing a `ClockPlugin` subclass is auto-discovered.
