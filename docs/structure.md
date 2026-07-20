# zeClock Project Structure

This document describes the file and folder organization of the **zeClock** project.

---

## 📂 General File Organization

```text
zeClock/
├── zeclock/                    # Main Python package (source code)
│   ├── __init__.py             # Package initialization, version
│   ├── clock.py                # Main async loop + CLI (entry point)
│   ├── colors.py               # Shared color constants (palette, auto-rotate list, reverse lookup)
│   ├── backend_config.py       # BackendConfig dataclass and config file parsing
│   ├── dmdserver_client.py     # Backward-compatible alias (imports DMDServerBackend as DMDServerClient)
│   ├── overlay.py              # Image composition via DotBlt masking
│   ├── brightness_scheduler.py # Brightness scheduling (time/day rules, sunrise/sunset, SW dimming)
│   ├── installer.py            # Automatic bootstrap (downloads libzedmd + resources)
│   ├── backends/               # Pluggable DMD backend system
│   │   ├── __init__.py         # Exports DMDBackend, create_backend
│   │   ├── base.py             # DMDBackend abstract base class (ABC)
│   │   ├── zedmd.py            # ZeDMDBackend: direct hardware via libzedmd ctypes
│   │   ├── dmdserver.py        # DMDServerBackend: TCP client (DMDStream protocol)
│   │   └── factory.py          # create_backend() factory function (auto/zedmd/dmdserver)
│   ├── readers/                # Binary format parsers for DotClk files
│   │   ├── __init__.py         # Exports load_font, load_scene, BitmapFont, Scene
│   │   ├── fnt_reader.py       # Bitmap font .fnt loader (4-bit per pixel)
│   │   └── scn_reader.py       # Animation .scn loader (storyboard + dotmaps)
│   ├── resources/              # Bundled package resources (distributed with the wheel)
│   │   ├── __init__.py         # Resource package marker
│   │   └── fonts/              # Bitmap fonts shipped inside the package
│   │       ├── __init__.py     # Font resource marker
│   │       ├── STANDARD.fnt    # Default clock font (+ _HD variant)
│   │       ├── ALTERN8.fnt     # Alternate font (+ _HD variant)
│   │       ├── FISHY.fnt       # Fishy font (+ _HD variant)
│   │       ├── MENU.fnt        # Menu font (+ _HD variant)
│   │       ├── SYSTEM.fnt      # System font (+ _HD variant)
│   │       ├── TREK.fnt        # Trek font (+ _HD variant)
│   │       └── TWILIGHT.fnt    # Twilight font (+ _HD variant)
│   ├── remote/                  # Remote control module (MQTT + REST API + Web UI)
│   │   ├── __init__.py         # Exports CommandHandler, RemoteCommand, MqttRemote, RestRemote
│   │   ├── command_handler.py  # Shared command execution logic (on/off, force plugin, display text)
│   │   ├── mqtt_remote.py      # MQTT remote control (pub/sub, Home Assistant Discovery)
│   │   ├── rest_remote.py      # REST API remote control (HTTP endpoints + Web UI serving)
│   │   └── web/                # Web UI static files (served at /ui/)
│   │       ├── index.html      # Web UI main page (browser-based control panel)
│   │       └── style.css       # Web UI stylesheet
│   ├── text_utils.py            # Text transliteration (accented chars → ASCII for bitmap font rendering)
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
│       ├── speaker_timer_plugin.py # Built-in plugin: conference speaker countdown timer with color changes
│       ├── stock_plugin.py     # Built-in plugin: stock prices, daily change, and extended hours data
│       ├── weather_plugin.py   # Built-in plugin: weather conditions and forecast from Open-Meteo API
│       └── weather_icons.py    # Weather condition code to pixel-art icon mapping
├── deploy/                     # Deployment configurations
│   └── rpi/                    # Raspberry Pi autonomous deployment (Packer image build)
│       ├── rpi-zeclock.pkr.hcl # Packer template for headless RPi OS image
│       ├── build.sh            # Build helper script
│       ├── variables.auto.pkrvars.hcl # Build variables
│       ├── scripts/            # Provisioning scripts (system, zeclock install, overlay)
│       └── files/systemd/      # Systemd units (zeclock, wifi-connect, etc.)
├── scripts/                    # Development and utility scripts
│   ├── dev-start.sh            # Start zeclock locally (real or virtual mode)
│   ├── dev-stop.sh             # Stop local zeclock
│   └── virtual-dmd.py          # Virtual DMD server with WebGL browser preview
├── examples/                   # Example and quick-test scripts
│   ├── run_clock.py            # Minimal clock launcher
│   ├── demo.py                 # Frame loading and sending demo
│   └── test_readers.py         # Quick validation of .fnt and .scn readers
├── config/                     # Default configuration
│   └── zeclock.ini             # Reference config file (zedmd + dmdserver sections)
├── docs/                       # Technical documentation
│   ├── architecture.md         # Architecture and rendering pipeline
│   ├── structure.md            # This file (project organization)
│   ├── tech.md                 # Detailed technical stack
│   └── plugin_authoring.md     # Plugin development guide
├── tests/                      # Test suite (pytest + hypothesis)
├── DotClk/                     # Git submodule - Original C++ DotClk project (Teensy)
├── dmd-simulator/              # Git submodule - Graphical DMD simulator (Python/SDL2)
├── libdmdutil.src/             # Git submodule - C++ source for libdmdutil/dmdserver
├── Makefile                    # Dev workflow: make test, make dev-start, etc.
├── mypy.ini                    # mypy type checker configuration
├── pyproject.toml              # Modern packaging configuration (PEP 621, setuptools)
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
| `clock.py` | Main application: async loop, state machine, animation pre-computation, CLI (`--color`, `--animation-color`, `--backend`, `--wifi-addr`, `--device`, `--brightness`, `--bootstrap`) |
| `colors.py` | Shared color constants: canonical `COLOR_MAP` (name → RGB), `COLOR_LIST` (for auto-rotate), and `COLOR_NAMES` (reverse lookup) |
| `backend_config.py` | `BackendConfig` dataclass and config file parsing (`~/.zeclock/config/zeclock.ini`); merges CLI args over config values |
| `dmdserver_client.py` | Backward-compatible alias: imports `DMDServerBackend` as `DMDServerClient` for external code compatibility |
| `overlay.py` | Image merging via DotBlt algorithm: `overlay_or` (monochrome) and `overlay_or_rgb` (dual color) |
| `brightness_scheduler.py` | Brightness scheduling engine: day-of-week time ranges, sunrise/sunset API integration, HW+SW dimming mapping, time-only mode, animation suppression |
| `installer.py` | Runtime bootstrap: detects platform, downloads libzedmd from GitHub (`PPUC/libzedmd`), installs DotClk animations (fonts are bundled in the package) |
| `backends/__init__.py` | Backend package: exports `DMDBackend` ABC and `create_backend()` factory function |
| `backends/base.py` | `DMDBackend` abstract base class: defines `connect()`, `send_frame()`, `disconnect()`, `connected` property, and context manager protocol |
| `backends/zedmd.py` | `ZeDMDBackend`: loads libzedmd via ctypes, sends frames as RGB888 directly (no pixel conversion), communicates directly with ZeDMD hardware (WiFi/USB) |
| `backends/dmdserver.py` | `DMDServerBackend`: TCP client using DMDStream protocol, refactored from the original `dmdserver_client.py` |
| `backends/factory.py` | `create_backend()`: instantiates the correct backend based on `--backend` argument (auto/zedmd/dmdserver) |
| `readers/__init__.py` | Exports `BitmapFont`, `load_font`, `Scene`, `load_scene` |
| `readers/fnt_reader.py` | Parses bitmap `.fnt` fonts: headers, character info (width, kerning), 4-bit bitmap, masks |
| `readers/scn_reader.py` | Parses `.scn` animations: storyboard (delays, blanks, clock_style, positions), 4-bit dotmap frames with masks |
| `resources/__init__.py` | Package marker for bundled resources |
| `resources/fonts/__init__.py` | Package marker for bundled font resources |
| `resources/fonts/*.fnt` | Bitmap fonts (STANDARD, ALTERN8, FISHY, MENU, SYSTEM, TREK, TWILIGHT + HD variants) shipped inside the wheel via `package-data`. Available without runtime bootstrap. |
| `remote/__init__.py` | Remote control package: exports `CommandHandler`, `RemoteCommand`, `MqttRemote`, `RestRemote` |
| `remote/command_handler.py` | `CommandHandler`: shared command execution logic for remote control (on/off, force plugin, display text, brightness) |
| `remote/mqtt_remote.py` | `MqttRemote`: MQTT-based remote control with bidirectional pub/sub and Home Assistant MQTT Discovery |
| `remote/rest_remote.py` | `RestRemote`: REST API remote control via HTTP endpoints, plugin list API, Speaker Timer sub-API, and Web UI static file serving |
| `remote/web/index.html` | Web UI main page: browser-based control panel for the clock (served at `/ui/`) |
| `remote/web/style.css` | Web UI stylesheet |
| `text_utils.py` | Text transliteration utilities: `transliterate()` replaces accented and special characters (é→e, ü→u, œ→oe, etc.) with their closest ASCII equivalents for bitmap font rendering (fonts only support printable ASCII 32–126). Strips any remaining non-ASCII characters. |
| `plugin_registry.py` | `PluginRegistry`: stores loaded plugins with state, frequency, and error tracking; handles override logic and frequency normalization |
| `plugin_config.py` | `PluginConfig`: loads and validates `plugins.yaml` configuration; provides defaults, frequency clamping, and plugin-specific settings |
| `plugin_manager.py` | `PluginManager`: top-level orchestrator that discovers, loads, validates, schedules, and drives plugins through their lifecycle |
| `plugins/__init__.py` | Plugin system package: exports `ClockPlugin` ABC, `validate_plugin_name`, `validate_plugin_description` |
| `plugins/base.py` | `ClockPlugin` abstract base class defining the plugin interface (name, description, frame_delay_ms, initialize, render_frame, cleanup) |
| `plugins/helpers.py` | `PluginHelpers` shared rendering utilities: frame creation, BitmapFont text rendering, pixel-art icon drawing, DotBlt-style compositing, font discovery and text measurement |
| `plugins/pinball_plugin.py` | Built-in pinball animation plugin: wraps `.scn` playback with DotBlt clock overlay, supports dual color and scene storyboard metadata |
| `plugins/pong_plugin.py` | Built-in Pong clock plugin: simulates a Pong game where the score always shows the current time (hours vs minutes) |
| `plugins/gif_plugin.py` | Built-in GIF plugin: picks a random animated GIF from a configurable directory, scales frames using the configured upscale algorithm for pixel-perfect integer multiples or LANCZOS for arbitrary sizes, plays it once respecting native frame delays, then signals completion |
| `plugins/weather_plugin.py` | Built-in weather plugin: fetches data from Open-Meteo API, displays current conditions, tomorrow's forecast, and 3-day outlook |
| `plugins/speaker_timer_plugin.py` | Built-in speaker timer plugin: conference countdown timer with automatic color changes (green → yellow → red), remote web API control, presets, and overtime counting |
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
| `pyproject.toml` | Single packaging configuration (PEP 621). Defines metadata, dependencies (`pillow>=9.0`, `aiohttp>=3.8`, `pyyaml>=6.0`, `colorama>=0.4.6`), extras (`zedmd`, `dev`), package-data (bundled `.fnt` fonts), and the CLI entry point `zeclock`. Backend: setuptools. |
| `Makefile` | Development workflow: `make test` (pytest+flake8+mypy+black), `make dev-start`/`dev-stop` |
| `mypy.ini` | mypy type checker configuration |
| `config/zeclock.ini` | Reference configuration file for backend selection, ZeDMD (WiFi/USB/brightness), and dmdserver (host/port) |

---

## 🎯 User Directory `~/.zeclock/` (Runtime)

During normal operation, the application expects the following directories in the user's home (created automatically by the bootstrap):

```text
~/.zeclock/
├── lib/
│   ├── libzedmd.so              # ZeDMD shared library (or .dylib / .dll)
│   ├── libsockpp.so             # Socket library dependency
│   ├── libserialport.so         # Serial port library dependency
│   └── .libzedmd-version        # Installed version tag (for update detection)
├── config/
│   ├── zeclock.ini              # Backend and ZeDMD connection configuration
│   └── plugins.yaml             # Plugin configuration (active plugins, frequencies, settings)
├── plugins/                     # User-installed plugins (override built-in by name)
│   └── *.py                     # Custom ClockPlugin implementations
└── resources/
    └── animations/
        └── <Themes>/           # Thematic folders (Pinball, Classic, Holiday...)
            └── *.scn           # Animation files (2300+)
```

Fonts are bundled inside the Python package (`zeclock/resources/fonts/`) and do not appear in this runtime tree. The bootstrap mechanism (`installer.py`) automatically manages the creation of this tree on first launch or via `zeclock --bootstrap`.

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
