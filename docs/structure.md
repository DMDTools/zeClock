# zeClock Project Structure

This document describes the file and folder organization of the **zeClock** project.

---

## 📂 General File Organization

```text
zeClock/
├── zeclock/                    # Main Python package (source code)
│   ├── __init__.py             # Package initialization, version
│   ├── clock.py                # Main async loop + CLI (entry point)
│   ├── dmdserver_client.py     # TCP Socket client (DMDStream RGB565 protocol)
│   ├── overlay.py              # Image composition via DotBlt masking
│   ├── installer.py            # Automatic bootstrap (downloads dmdserver + resources)
│   ├── readers/                # Binary format parsers for DotClk files
│   │   ├── __init__.py         # Exports load_font, load_scene, BitmapFont, Scene
│   │   ├── fnt_reader.py       # Bitmap font .fnt loader (4-bit per pixel)
│   │   └── scn_reader.py       # Animation .scn loader (storyboard + dotmaps)
│   ├── plugin_registry.py      # Plugin registry: stores plugins with state, frequency, override logic
│   ├── plugin_config.py        # Plugin YAML configuration loader and validator
│   ├── plugin_manager.py       # Plugin manager: discovery, loading, scheduling, lifecycle orchestration
│   └── plugins/                # Plugin system for extensible display content
│       ├── __init__.py         # Exports ClockPlugin ABC and validation utilities
│       ├── base.py             # ClockPlugin abstract base class (plugin interface contract)
│       ├── helpers.py          # PluginHelpers shared rendering utilities (fonts, icons, compositing)
│       ├── pinball_plugin.py   # Built-in plugin: retro pinball .scn animation playback with DotBlt overlay
│       ├── pong_plugin.py      # Built-in plugin: Pong game where the score displays the current time
│       ├── gif_plugin.py       # Built-in plugin: plays random animated GIFs from a directory
│       ├── stock_plugin.py     # Built-in plugin: stock prices, daily change, and extended hours data
│       ├── weather_plugin.py   # Built-in plugin: weather conditions and forecast from Open-Meteo API
│       └── weather_icons.py    # Weather condition code to pixel-art icon mapping
├── deploy/                     # Deployment configurations
│   └── nas/                    # NAS Docker deployment
│       ├── docker-compose.yml  # Orchestrates dmdserver + zeclock containers
│       ├── Dockerfile.dmdserver # Builds dmdserver image (python:3.11-slim + libdmdutil binary)
│       ├── Dockerfile.zeclock  # Builds zeclock image with resources
│       ├── entrypoint.sh       # Container entrypoint (waits for dmdserver, starts zeclock)
│       ├── config/             # dmdserver.ini for NAS deployment
│       └── zeclock-config/     # Synced ~/.zeclock/config (plugins.yaml, etc.)
├── scripts/                    # Development and utility scripts
│   ├── dev-start.sh            # Start dmdserver + zeclock locally (real or virtual mode)
│   ├── dev-stop.sh             # Stop local dmdserver + zeclock
│   └── fake-dmdserver.py       # Virtual DMD server with WebGL browser preview
├── examples/                   # Example and quick-test scripts
│   ├── run_clock.py            # Minimal clock launcher
│   ├── demo.py                 # Frame loading and sending demo
│   └── test_readers.py         # Quick validation of .fnt and .scn readers
├── config/                     # Default configuration
│   ├── dmdserver.ini           # Reference ini file for dmdserver (real ZeDMD)
│   └── dmdserver-virtual.ini   # Config for virtual mode (no physical display)
├── docs/                       # Technical documentation
│   ├── architecture.md         # Architecture and rendering pipeline
│   ├── structure.md            # This file (project organization)
│   ├── tech.md                 # Detailed technical stack
│   └── plugin_authoring.md     # Plugin development guide
├── tests/                      # Test suite (pytest + hypothesis)
├── DotClk/                     # Git submodule - Original C++ DotClk project (Teensy)
├── dmd-simulator/              # Git submodule - Graphical DMD simulator (Python/SDL2)
├── libdmdutil.src/             # Git submodule - C++ source for libdmdutil/dmdserver
├── Makefile                    # Dev workflow: make test, make dev-start, make nas-deploy, etc.
├── mypy.ini                    # mypy type checker configuration
├── pyproject.toml              # Modern packaging configuration (PEP 621, setuptools)
├── .dockerignore               # Files excluded from Docker builds
├── README.md                   # User documentation and quickstart guide
└── .gitignore                  # Files excluded from version control
```

---

## 🔍 Detailed Component Descriptions

### 📦 The `zeclock/` Package

This is the application core. It contains all the Python logic for reading resources, composing frames, and driving the DMD server.

| File | Role |
|------|------|
| `__init__.py` | Initializes the Python package and exposes the version (`0.1.0`) |
| `clock.py` | Main application: async loop, state machine, animation pre-computation, CLI (`--color`, `--animation-color`, `--bootstrap`) |
| `dmdserver_client.py` | Lightweight TCP client: forges DMDStream packets (header + RGB565 big-endian), manages persistent connection |
| `overlay.py` | Image merging via DotBlt algorithm: `overlay_or` (monochrome) and `overlay_or_rgb` (dual color) |
| `installer.py` | Runtime bootstrap: detects platform, downloads dmdserver from GitHub, installs DotClk resources |
| `readers/__init__.py` | Exports `BitmapFont`, `load_font`, `Scene`, `load_scene` |
| `readers/fnt_reader.py` | Parses bitmap `.fnt` fonts: headers, character info (width, kerning), 4-bit bitmap, masks |
| `readers/scn_reader.py` | Parses `.scn` animations: storyboard (delays, blanks, clock_style, positions), 4-bit dotmap frames with masks |
| `plugin_registry.py` | `PluginRegistry`: stores loaded plugins with state, frequency, and error tracking; handles override logic and frequency normalization |
| `plugin_config.py` | `PluginConfig`: loads and validates `plugins.yaml` configuration; provides defaults, frequency clamping, and plugin-specific settings |
| `plugin_manager.py` | `PluginManager`: top-level orchestrator that discovers, loads, validates, schedules, and drives plugins through their lifecycle |
| `plugins/__init__.py` | Plugin system package: exports `ClockPlugin` ABC, `validate_plugin_name`, `validate_plugin_description` |
| `plugins/base.py` | `ClockPlugin` abstract base class defining the plugin interface (name, description, frame_delay_ms, initialize, render_frame, cleanup) |
| `plugins/helpers.py` | `PluginHelpers` shared rendering utilities: frame creation, BitmapFont text rendering, pixel-art icon drawing, DotBlt-style compositing, font discovery and text measurement |
| `plugins/pinball_plugin.py` | Built-in pinball animation plugin: wraps `.scn` playback with DotBlt clock overlay, supports dual color and scene storyboard metadata |
| `plugins/pong_plugin.py` | Built-in Pong clock plugin: simulates a Pong game where the score always shows the current time (hours vs minutes) |
| `plugins/gif_plugin.py` | Built-in GIF plugin: picks a random animated GIF from a configurable directory, plays it once respecting native frame delays, then signals completion |
| `plugins/weather_plugin.py` | Built-in weather plugin: fetches data from Open-Meteo API, displays current conditions, tomorrow's forecast, and 3-day outlook |
| `plugins/stock_plugin.py` | Built-in stock plugin: fetches quotes from Yahoo Finance, displays price, daily change, and extended hours data with market state detection |
| `plugins/weather_icons.py` | WMO weather condition code to 16×16 pixel-art icon bitmap mapping |

### 🧪 Examples (`examples/`)

Scripts for quickly testing the installation or understanding the API:

- `run_clock.py`: Launches `zeclock.clock.main()` directly.
- `demo.py`: Demo of loading animations and sending monochrome frames to the server.
- `test_readers.py`: Quick validation of `.fnt` font and `.scn` animation reading.

### ⚙️ External Submodules

| Submodule | Description |
|-----------|-------------|
| `DotClk/` | Original C++ code for Teensy / Arduino boards. Reference for validating Python rendering conformity with historical hardware behavior. |
| `libdmdutil.src/` | C++ source code for the dmdserver library. Allows manual compilation if pre-built binaries don't fit. |
| `dmd-simulator/` | Local graphical simulator (Python, SDL2, websockets) for testing without a physical ZeDMD panel. Independent package with its own `pyproject.toml`. |

### 📋 Configuration and Packaging

| File | Role |
|------|------|
| `pyproject.toml` | Single packaging configuration (PEP 621). Defines metadata, dependencies (`pillow>=9.0`, `aiohttp>=3.8`, `pyyaml>=6.0`, `colorama>=0.4.6`), extras (`zedmd`, `dev`), and the CLI entry point `zeclock`. Backend: setuptools. |
| `Makefile` | Development workflow: `make test` (pytest+flake8+mypy+black), `make dev-start`/`dev-stop`, `make nas-deploy`/`nas-stop`, `make format` |
| `mypy.ini` | mypy type checker configuration |
| `.dockerignore` | Files excluded from Docker image builds |
| `config/dmdserver.ini` | Reference configuration file for dmdserver (ports, ZeDMD USB/WiFi, brightness) |
| `config/dmdserver-virtual.ini` | Configuration for virtual mode (no physical display attached) |

---

## 🎯 User Directory `~/.zeclock/` (Runtime)

During normal operation, the application expects the following directories in the user's home (created automatically by the bootstrap):

```text
~/.zeclock/
├── bin/
│   ├── dmdserver                # Native dmdserver executable
│   ├── libdmdutil.so            # Dynamic libraries
│   ├── libzedmd.so
│   └── ...
├── config/
│   ├── dmdserver.ini            # TCP server and ZeDMD connection configuration
│   └── plugins.yaml             # Plugin configuration (active plugins, frequencies, settings)
├── plugins/                     # User-installed plugins (override built-in by name)
│   └── *.py                     # Custom ClockPlugin implementations
└── resources/
    ├── Fonts/
    │   ├── STANDARD.fnt         # Main clock font
    │   └── ...                  # Other .fnt fonts
    └── animations/
        └── <Themes>/           # Thematic folders (Pinball, Classic, Holiday...)
            └── *.scn           # Animation files (2300+)
```

The bootstrap mechanism (`installer.py`) automatically manages the creation of this tree on first launch or via `zeclock --bootstrap`.

---

## 📦 Installation and Distribution

The project uses `pyproject.toml` (PEP 621) exclusively for packaging:

```bash
# Isolated global installation (recommended)
pipx install git+https://github.com/DMDTools/zeClock.git

# Instant execution without installation
uvx --from git+https://github.com/DMDTools/zeClock.git zeclock

# Development mode installation
pip install -e ".[dev]"
```

The CLI entry point `zeclock` is defined in `pyproject.toml` and points to `zeclock.clock:main`.
