# zeClock

> 🕒 A smart animated clock for ZeDMD DMD displays, inspired by the DotClk project

Transform your desk into an arcade room with a DMD clock that displays time over retro pinball animations!

![zeClock Demo](https://placehold.co/600x400?text=Placeholder+demo+video)

## Features

- **Native DotClk animations**: Direct playback of `.scn` files (2300+ animations available)
- **DotClk bitmap fonts**: Support for original `.fnt` fonts
- **Direct ZeDMD communication**: Native libzedmd integration via ctypes (no separate dmdserver needed)
- **Backend abstraction**: Swap between direct libzedmd and TCP dmdserver backends
- **Asynchronous architecture**: Smooth 25 FPS rendering without blocking CPU
- **Smart overlay**: Bitwise OR merging like original DotClk
- **Dual color schemes**: Different colors for clock and animations
- **Attract mode**: Automatic activation after inactivity
- **REST API**: Remote control (display changes, notifications)
- **MQTT remote control**: Bidirectional pub/sub with Home Assistant MQTT Discovery
- **Simple installation**: Single `--bootstrap` command installs everything

## Two Operating Modes

zeClock is designed to work in two distinct modes:

### 🖥️ Mode 1: Local Development (PC / Mac)

Use this mode on your computer for **developing, testing, and trying out** zeClock. ZeDMD hardware is **optional** — without it, the display is emulated directly in your web browser with a WebGL dot-matrix shader for authentic DMD look.

| Setup | What you need |
|-------|--------------|
| **With ZeDMD** | ZeDMD connected via USB or WiFi + Python 3.9+ |
| **Without ZeDMD** | Python 3.9+ only — output rendered in browser at `http://localhost:3000` |

This is the fastest way to try zeClock: install, bootstrap, and run in virtual mode — the clock appears in your browser in seconds.

### 🍓 Mode 2: Autonomous (Raspberry Pi)

Use this mode to run zeClock **24/7 unattended** on a dedicated Raspberry Pi (or equivalent SBC). The Pi boots directly into zeClock with:

- Read-only filesystem (power-loss safe)
- WiFi auto-connect with captive portal fallback
- Automatic systemd service startup
- Persistent configuration on a separate partition

See [`deploy/rpi/`](deploy/rpi/) for the full Packer-based image build process.

---

## Quick Start (Local Development)

The simplest way to try zeClock — **no hardware required**:

```bash
# 1. Clone and install
git clone https://github.com/DMDTools/zeClock.git
cd zeClock
pip install -e ".[dev]"

# 2. Bootstrap resources (downloads fonts + animations)
zeclock --bootstrap

# 3. Start with virtual DMD in your browser
make dev-start-virtual
```

Open **http://localhost:3000** — the clock is running with a WebGL DMD shader in your browser!

For HD mode (256x64): `make dev-start-virtual-hd`

To stop: `make dev-stop` or `Ctrl+C`

---

## Prerequisites

- **Python 3.9+**
- **ZeDMD** (128x32 standard or 256x64 HD) connected via USB or WiFi — *optional for development, browser emulation available*
- **Linux** (Raspberry Pi, Ubuntu, WSL), **macOS**, or **Windows** (Git Bash/WSL)

## Installation

**zeClock** features a modern packaging layout and an automatic runtime initialization (Bootstrap) mechanism, making it fully compatible with isolated environments out of the box.

### Option A: Global Isolated Installation (Recommended - via pipx or uvx)

You can install and run zeClock in an isolated environment without affecting your global Python packages:

```bash
# With pipx (Permanent global installation):
pipx install git+https://github.com/DMDTools/zeClock.git

# OR with uvx (Instant execution without manual installation):
uvx --from git+https://github.com/DMDTools/zeClock.git zeclock
```

### Option B: Development Installation (Source)

```bash
git clone https://github.com/DMDTools/zeClock.git
cd zeClock

# Editable install with development dependencies:
pip install -e ".[dev]"
```

### 🚀 Automatic Resource Bootstrap on First Launch

On the first run (using the global `zeclock` command), the application automatically detects if the native libraries and retro resources are missing from your `~/.zeclock/` user directory.

It will then prompt you with an **interactive setup wizard** directly in your terminal to download and configure everything automatically.

If you prefer to install all resources in a single non-interactive command:
```bash
zeclock --bootstrap
```

This process automatically installs the following in your `~/.zeclock/` directory:
*   **libzedmd**: The native shared library for direct ZeDMD communication, installed to `~/.zeclock/lib/`.
*   **Fonts & Animations** (from [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources)): Over **2300 retro animations** (`.scn`) and the original bitmap fonts (`.fnt`).

## Getting Started (with ZeDMD hardware)

zeClock communicates directly with ZeDMD hardware via libzedmd — no separate dmdserver process is needed.

**Launch zeClock**

```bash
# Default: auto backend (uses libzedmd if available, falls back to dmdserver)
zeclock

# Fixed orange clock
zeclock --color orange

# Orange clock with blue animations
zeclock --color orange --animation-color blue
```

That's it! With the default `auto` backend, zeClock connects directly to your ZeDMD over WiFi or USB using libzedmd.

### CLI Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--backend` | `auto`, `zedmd`, `dmdserver` | `auto` | Backend selection |
| `--wifi-addr` | IP address | from config | ZeDMD WiFi address |
| `--device` | path | auto-detect | USB serial device (e.g. `/dev/ttyUSB0`) |
| `--brightness` | 0-15 | 10 | Display brightness |
| `--hd` | — | — | Use ZeDMD HD resolution (256x64) |
| `--width` | pixels | 128 (or 256 with `--hd`) | Display width |
| `--height` | pixels | 32 (or 64 with `--hd`) | Display height |
| `--color` | color name | `auto` | Clock color |
| `--animation-color` | color name | same as clock | Animation color |
| `--bootstrap` | — | — | Install libzedmd + DotClk resources |

**Backend modes:**
- `auto` (default): Tries libzedmd first, falls back to dmdserver TCP if unavailable
- `zedmd`: Direct libzedmd only — exits with error if library not found or connection fails
- `dmdserver`: TCP connection to a running dmdserver process (for development/virtual-dmd)

**ZeDMD HD (256x64):**

zeClock supports ZeDMD HD displays natively. The resolution is auto-detected from the hardware after connection — if your ZeDMD is flashed with HD firmware (256x64), zeClock adapts automatically. You can also force HD mode explicitly:

```bash
# Auto-detection (recommended — works if ZeDMD HD firmware is flashed)
zeclock

# Force HD resolution explicitly
zeclock --hd

# Custom resolution
zeclock --width 256 --height 64
```

### Configuration File

zeClock reads configuration from `~/.zeclock/config/zeclock.ini`:

```ini
[zedmd]
# WiFi connection (takes precedence over USB)
wifi_addr = 192.168.0.35
# USB serial device (leave empty for auto-detection)
# device = /dev/ttyUSB0
# Brightness (0-15)
brightness = 10

[display]
# Display resolution — auto-detected from hardware when possible
# Standard ZeDMD: 128x32 (default)
# ZeDMD HD: 256x64
# width = 256
# height = 64

[location]
# Global location (used by weather plugin and sunrise/sunset brightness)
latitude = 45.1885
longitude = 5.7245
city_name = Grenoble

[brightness_schedule]
# Maximum hardware brightness for 100% (0-15, default: 7)
max_brightness = 7
# Schedule: HH:MM-HH:MM brightness%, ... (overnight ranges supported)
default = 22:00-08:00 10%
# monday = 08:00-18:00 80%, 22:00-08:00 10%
# Sunrise/sunset auto-brightness (requires [location])
# sunrise_brightness = 100%
# sunset_brightness = 10%
# "Time only" mode: clock only, no plugins
time_only = 22:00-08:00

[mqtt]
# MQTT remote control (requires: pip install zeclock[mqtt])
# enabled = true
# host = localhost
# port = 1883
# device_id = zeclock
# ha_discovery = true

[rest_api]
# REST API remote control
# enabled = true
# host = 0.0.0.0
# port = 8080

[dmdserver]
# Used when --backend dmdserver is specified
host = localhost
port = 6789
```

CLI arguments take precedence over config file values.

### Brightness Scheduling

zeClock supports automatic brightness adjustment based on time of day, day of week, and sunrise/sunset.

**How it works:**

- Brightness is expressed as a percentage (0–100%)
- 100% maps to the configured `max_brightness` (default: HW 7 out of 15)
- Below ~7%, software dimming kicks in for ultra-low brightness (HW 1 + pixel dimming)
- 0% turns the screen off completely (all black)

**Schedule format** (in `[brightness_schedule]`):

```ini
# Per-day schedules (comma-separated time ranges)
monday = 08:00-18:00 80%, 22:00-08:00 10%
saturday = 20:00-23:00 50%, 23:00-08:00 5%

# Default applies to all days without a specific schedule
default = 22:00-08:00 10%
```

Overnight ranges (e.g., `22:00-08:00`) are supported. Unmatched times use 100%.

**Sunrise/sunset mode** (requires `[location]`):

```ini
[location]
latitude = 45.1885
longitude = 5.7245

[brightness_schedule]
sunrise_brightness = 100%
sunset_brightness = 10%
```

Uses the [sunrise-sunset.org](https://sunrise-sunset.org) API (no key required). Falls back to schedule rules if the API is unreachable.

**"Time only" mode:**

During configured hours, only the clock is displayed — no plugins, no animations:

```ini
time_only = 22:00-08:00
```

### Development Mode (Virtual DMD)

For development without physical hardware, see the [Quick Start](#quick-start-local-development) section above or [CONTRIBUTING.md](CONTRIBUTING.md#development-mode-virtual-dmd).

### Remote Control (MQTT & REST API)

zeClock can be controlled remotely via MQTT (primary) and/or a REST API. Both share the same command set and can run simultaneously.

**Enable in `~/.zeclock/config/zeclock.ini`:**

```ini
[mqtt]
enabled = true
host = 192.168.1.100
port = 1883
# username = myuser
# password = mypass
device_id = zeclock
# Home Assistant MQTT Discovery (auto-creates entities)
ha_discovery = true

[rest_api]
enabled = true
host = 0.0.0.0
port = 8080
```

**Install MQTT support:**

```bash
pip install zeclock[mqtt]
# or: pip install aiomqtt
```

**MQTT topics:**

| Topic | Direction | Description |
|-------|-----------|-------------|
| `zeclock/<device_id>/command` | → zeClock | Send commands (JSON) |
| `zeclock/<device_id>/state` | ← zeClock | Current state (JSON, retained) |
| `zeclock/<device_id>/availability` | ← zeClock | `online` / `offline` (retained) |

**Commands (MQTT JSON payload or REST body):**

```jsonc
// Turn screen off (all black)
{"command": "screen_off"}

// Turn screen back on
{"command": "screen_on"}

// Force a specific plugin
{"command": "force_plugin", "plugin": "weather"}

// Resume normal plugin rotation
{"command": "force_plugin", "plugin": null}

// Display text for N seconds
{"command": "display_text", "text": "Hello!", "duration": 15}

// Get current status
{"command": "get_status"}
```

**REST API endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Current clock status |
| `POST` | `/api/screen/on` | Turn screen on |
| `POST` | `/api/screen/off` | Turn screen off |
| `POST` | `/api/plugin/force` | Force plugin `{"plugin": "name"}` |
| `POST` | `/api/plugin/resume` | Resume normal rotation |
| `POST` | `/api/text` | Display text `{"text": "...", "duration": 10}` |

**Home Assistant integration:**

When `ha_discovery = true`, zeClock automatically registers itself in Home Assistant via MQTT Discovery. You get:
- A **switch** to turn the screen on/off
- **Sensors** for active plugin and display mode

No manual HA configuration needed — just point both at the same MQTT broker.

## Plugins

zeClock includes built-in plugins that alternate with the clock display. Each plugin renders animated content on the DMD.

### Pinball

Retro pinball DMD animations with clock overlay. Plays randomly from 2300+ `.scn` animation files with DotBlt composition.

![Pinball plugin demo](https://placehold.co/400x100/0a0a0a/ff8800?text=Pinball+Plugin+Demo)

### Pong

Two AI players compete in a real Pong match. The score persists across activations — the clock only takes over between points. First to 5 wins with confetti celebration.

![Pong plugin demo](https://placehold.co/400x100/0a0a0a/ff8800?text=Pong+Plugin+Demo)

### Weather

Current conditions, tomorrow's forecast, 3-day outlook, and 7-day overview. Data from Open-Meteo API (no key required), cached 15 minutes.

![Weather plugin demo](https://placehold.co/400x100/0a0a0a/ff8800?text=Weather+Plugin+Demo)

### Eyes

Animated robot eyes tracking a buzzing fly. The eyes react with expressions (surprised, annoyed, sleepy) based on the fly's behavior.

![Eyes plugin demo](https://placehold.co/400x100/0a0a0a/ff8800?text=Eyes+Plugin+Demo)

### Stock

Real-time stock prices from Yahoo Finance with intraday sparkline graphs. Supports multiple symbols, pre/post market data.

![Stock plugin demo](https://placehold.co/400x100/0a0a0a/ff8800?text=Stock+Plugin+Demo)

### GIF

Plays animated GIFs from `~/.zeclock/plugins/gif/`. Drop any `.gif` file in the directory and it will be randomly selected.

### Plugin configuration

Plugins are configured in `~/.zeclock/config/plugins.yaml`:

```yaml
clock_display_seconds: 5
plugins:
  - name: pinball
    frequency: 40
  - name: pong
    frequency: 20
  - name: weather
    frequency: 20
    settings:
      latitude: 45.19
      longitude: 5.72
      city_name: Grenoble
      language: fr
  - name: eyes
    frequency: 10
  - name: stock
    frequency: 10
    settings:
      symbols: ["AAPL", "MSFT", "^FCHI"]
```

Override from CLI: `zeclock --plugins pinball,pong`

## Writing Plugins

Want to create your own plugin? See the [Plugin Authoring Guide](docs/plugin_authoring.md) for the complete reference (interface, helpers API, lifecycle, testing), or [CONTRIBUTING.md](CONTRIBUTING.md#writing-plugins) for a quick overview.

## Project Structure

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full project structure and architecture details.

**Installed resources** (`~/.zeclock/`):

```
~/.zeclock/
├── lib/                         # libzedmd native library
├── config/
│   ├── zeclock.ini              # User configuration (backend, display, brightness, location)
│   └── plugins.yaml             # Plugin configuration (frequency, settings)
└── resources/
    └── animations/              # 2300+ retro .scn animations
```

Fonts are bundled in the package — no separate download needed.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and architecture.

```bash
make test              # Run tests + lint + type check
make dev-start-virtual # Virtual DMD in browser (128x32)
make dev-start-virtual-hd  # Virtual DMD HD (256x64)
```

## Troubleshooting

**libzedmd not found**

```bash
# Run bootstrap to install
zeclock --bootstrap

# Check that libraries are installed
ls ~/.zeclock/lib/

# Verify library loads
python -c "import ctypes; ctypes.CDLL('$HOME/.zeclock/lib/libzedmd.so')"
```

**ZeDMD not detected (WiFi)**

```bash
# Verify WiFi address is reachable
ping 192.168.0.35

# Check config file
cat ~/.zeclock/config/zeclock.ini

# Force WiFi address via CLI
zeclock --wifi-addr 192.168.0.35
```

**ZeDMD not detected (USB)**

```bash
# List serial ports
ls /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial*

# Force device via CLI
zeclock --device /dev/ttyUSB0
```

**Animations not displaying**

```bash
# Check that resources are installed
ls ~/.zeclock/resources/animations/

# Reinstall resources
zeclock --bootstrap
```

## Roadmap

See [TODO.md](TODO.md) for the full roadmap and planned features.

## References

- **DotClk** (inspiration): [sigmafx/DotClk](https://github.com/sigmafx/DotClk)
- **DotClk Resources**: [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources)
- **libzedmd**: [PPUC/libzedmd](https://github.com/PPUC/libzedmd)
- **ZeDMD**: [PPUC/ZeDMD](https://github.com/PPUC/ZeDMD)
- **ZeDMD OS**: [PPUC/zedmdos](https://github.com/PPUC/zedmdos)

## License

MIT License - see [LICENSE](LICENSE)

## Acknowledgments

- **SigmaFX** for the original DotClk project and its beautiful animations
- **PPUC** for the ZeDMD hardware and libzedmd
- **vpinball** for libdmdutil and dmdserver
- The **virtual pinball** community for the DMD ecosystem

## Support

- **Issues**: [GitHub Issues](https://github.com/DMDTools/zeClock/issues)
- **Discussions**: [GitHub Discussions](https://github.com/DMDTools/zeClock/discussions)

---

**Made with ❤️ by ojacques - Inspired by the magic of retro pinball** 🎮✨
