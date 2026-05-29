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
- **Simple installation**: Single `--bootstrap` command installs everything

## Prerequisites

- **Python 3.9+**
- **ZeDMD** (128x32 or 256x64) connected via USB or WiFi
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

## Getting Started

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
| `--color` | color name | `auto` | Clock color |
| `--animation-color` | color name | same as clock | Animation color |
| `--bootstrap` | — | — | Install libzedmd + DotClk resources |

**Backend modes:**
- `auto` (default): Tries libzedmd first, falls back to dmdserver TCP if unavailable
- `zedmd`: Direct libzedmd only — exits with error if library not found or connection fails
- `dmdserver`: TCP connection to a running dmdserver process (for development/virtual-dmd)

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

[dmdserver]
# Used when --backend dmdserver is specified
host = localhost
port = 6789
```

CLI arguments take precedence over config file values.

### Development Mode (Virtual DMD)

For development without physical hardware, use the dmdserver backend with `virtual-dmd.py`:

```bash
# Terminal 1: Start virtual DMD (browser preview)
make dev-start-virtual

# Terminal 2: Start zeClock with dmdserver backend
zeclock --backend dmdserver
```

This starts `scripts/virtual-dmd.py` which accepts DMDStream TCP connections and renders frames to a browser via WebSocket.

### Docker Deployment

zeClock runs as a single container with libzedmd embedded — no separate dmdserver container needed:

```bash
cd deploy/nas
docker compose up -d
```

Configure the ZeDMD WiFi address in `deploy/nas/zeclock-config/zeclock.ini`:

```ini
[zedmd]
wifi_addr = 192.168.0.35
brightness = 10
```

## Usage Examples

**Simple clock**

```python
from zeclock.clock import ZeClock
import asyncio

clock = ZeClock()
asyncio.run(clock.run())
```

**Clock with DotClk animation**

```python
from pathlib import Path
from zeclock.readers import load_scene, load_font
from zeclock.overlay import overlay_or
from zeclock.backends import create_backend
import time

# Load an animation
scene = load_scene(Path("~/.zeclock/resources/animations/Pinball/AFM/attract.scn").expanduser())

# Load a font
font = load_font(Path("~/.zeclock/resources/Fonts/Font1.fnt").expanduser())

# Create backend (auto-selects libzedmd or dmdserver)
backend = create_backend(backend="auto", wifi_addr="192.168.0.35")
backend.connect()

# Display animation with time
for frame in scene:
    time_str = time.strftime("%H:%M")
    time_overlay = font.render_text(time_str, 128, 32)
    merged = overlay_or(frame, time_overlay)
    backend.send_frame(merged, color=(255, 128, 0))
    time.sleep(0.04)  # 25 FPS

backend.disconnect()
```

## Project Structure

```
zeClock/
├── zeclock/
│   ├── __init__.py
│   ├── clock.py                 # Main asynchronous clock loop
│   ├── installer.py             # Runtime bootstrap (libzedmd & resources)
│   ├── backend_config.py        # BackendConfig dataclass and config file parsing
│   ├── overlay.py               # Bitmap blending and masking (DotBlt algorithm)
│   ├── dmdserver_client.py      # Backward-compatible alias for DMDServerBackend
│   ├── backends/
│   │   ├── __init__.py          # Exports DMDBackend, create_backend()
│   │   ├── base.py              # DMDBackend abstract base class
│   │   ├── zedmd.py             # ZeDMDBackend (ctypes/libzedmd)
│   │   ├── dmdserver.py         # DMDServerBackend (TCP socket)
│   │   └── factory.py           # create_backend() factory function
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── fnt_reader.py        # Binary .fnt bitmap font loader
│   │   └── scn_reader.py        # Binary .scn scene and animation loader
│   └── resources/
│       └── fonts/
│           └── default.ttf      # Fallback TrueType vector font
├── deploy/
│   └── nas/
│       ├── Dockerfile           # Single container with libzedmd
│       ├── docker-compose.yml   # Single zeclock service
│       └── zeclock-config/
│           └── zeclock.ini      # NAS-specific config
├── scripts/
│   └── virtual-dmd.py           # Virtual DMD for browser preview
├── examples/
│   ├── demo.py                  # Simple rendering demonstration
│   ├── run_clock.py             # Minimal clock launcher
│   └── test_readers.py          # Quick loader integration tests
├── tests/
│   ├── test_backend_base.py     # Backend ABC tests
│   ├── test_zedmd_backend.py    # ZeDMDBackend unit tests
│   ├── test_backend_factory.py  # Factory selection tests
│   └── ...
├── pyproject.toml               # Unified modern packaging configuration (PEP 621)
├── requirements.txt             # Minimum development requirements
└── README.md                    # User manual
```

**Installed resources**

```
~/.zeclock/
├── lib/
│   ├── libzedmd.so              # ZeDMD communication library
│   ├── libsockpp.so             # Socket library (dependency)
│   ├── libserialport.so         # Serial port library (dependency)
│   └── .libzedmd-version        # Installed version tag
├── config/
│   └── zeclock.ini              # User configuration
└── resources/
    ├── Fonts/
    │   ├── Font1.fnt            # Default DotClk font
    │   └── Font2.fnt
    └── animations/
        ├── Pinball/             # Animations by theme
        │   ├── AFM/
        │   ├── TronLegacy/
        │   └── ...
        ├── Classic/
        └── Holiday/
```

## Development

**Development mode installation**

```bash
git clone https://github.com/DMDTools/zeClock.git
cd zeClock
pip install -e ".[dev]"
```

**Tests**

```bash
pytest tests/
```

**Linter**

```bash
black zeclock/
flake8 zeclock/
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

**Fallback to dmdserver for development**

```bash
# Start virtual DMD
make dev-start-virtual

# Use dmdserver backend explicitly
zeclock --backend dmdserver
```

**Animations not displaying**

```bash
# Check that resources are installed
ls ~/.zeclock/resources/animations/

# Reinstall resources
zeclock --bootstrap
```

**Performance / Low FPS**

```python
# Reduce resolution or FPS
clock = ZeClock(width=128, height=32, fps=15)

# Preload animations in RAM
scene = load_scene("animation.scn")
frames = list(scene)  # Force loading
```

## Roadmap

- [ ] **REST API**: HTTP control (clock changes, notifications)
- [ ] **MQTT**: Home automation integration (Jeedom, Home Assistant)
- [ ] **Plugins**: Extensible Python plugin system
  - [ ] WeatherClock: Weather display
  - [ ] Home automation data
  - [ ] MAMEClock: High scores
  - [ ] AWSClock: AWS costs
- [ ] **Advanced attract mode**: Random rotation between multiple clocks
- [ ] **Web interface**: Browser-based configuration
- [ ] **Galaga Clock**: Animation where Galaga shoots changing digits

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
