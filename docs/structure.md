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
│       ├── weather_plugin.py   # Built-in plugin: weather conditions and forecast from Open-Meteo API
│       └── weather_icons.py    # Weather condition code to pixel-art icon mapping
├── examples/                   # Example and quick-test scripts
│   ├── run_clock.py            # Minimal clock launcher
│   ├── demo.py                 # Frame loading and sending demo
│   └── test_readers.py         # Quick validation of .fnt and .scn readers
├── config/                     # Default configuration
│   └── dmdserver.ini           # Reference ini file for dmdserver
├── docs/                       # Technical documentation
│   ├── architecture.md         # Architecture and rendering pipeline
│   ├── structure.md            # This file (project organization)
│   └── tech.md                 # Detailed technical stack
├── DotClk/                     # Git submodule - Original C++ DotClk project (Teensy)
├── dmd-simulator/              # Git submodule - Graphical DMD simulator (Python/SDL2)
├── libdmdutil.src/             # Git submodule - C++ source for libdmdutil/dmdserver
├── pyproject.toml              # Modern packaging configuration (PEP 621, setuptools)
├── requirements.txt            # Minimal development dependencies
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
| `pyproject.toml` | Single packaging configuration (PEP 621). Defines metadata, dependencies (`pillow>=9.0`, `numpy`), extras (`zedmd`, `dev`), and the CLI entry point `zeclock`. Backend: setuptools. |
| `requirements.txt` | Minimal development list: `pillow>=9.0.0`, `numpy>=1.20.0`, `asyncio`, `colorama>=0.4.6` |
| `config/dmdserver.ini` | Reference configuration file for dmdserver (ports, ZeDMD USB/WiFi, brightness) |

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
