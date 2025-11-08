# zeClock

> 🕒 A smart animated clock for ZeDMD DMD displays, inspired by the DotClk project

Transform your desk into an arcade room with a DMD clock that displays time over retro pinball animations!

![zeClock Demo](https://placehold.co/600x400?text=Placeholder+demo+video)

## Features

- **Native DotClk animations**: Direct playback of `.scn` files (2300+ animations available)
- **DotClk bitmap fonts**: Support for original `.fnt` fonts
- **WiFi/USB communication**: ZeDMD connection via libdmdutil/dmdserver
- **Asynchronous architecture**: Smooth 25 FPS rendering without blocking CPU
- **Smart overlay**: Bitwise OR merging like original DotClk
- **Dual color schemes**: Different colors for clock and animations
- **Attract mode**: Automatic activation after inactivity
- **REST API**: Remote control (display changes, notifications)
- **Simple installation**: Automated scripts for everything

## Prerequisites

- **Python 3.9+**
- **ZeDMD** (128x32 or 256x64) connected via USB or WiFi
- **Linux** (Raspberry Pi, Ubuntu, WSL), **macOS**, or **Windows** (Git Bash/WSL)

## Installation

**1. Clone the project**

```bash
git clone https://github.com/DMDTools/zeclock.git
cd zeclock
```

**2. Install zeClock**

```bash
pip install -e .
```

**3. Install libdmdutil (dmdserver)**

```bash
./scripts/install_libdmdutil.sh
# Or cross-platform Python version:
python3 scripts/install_libdmdutil.py
```

This installs:
- `dmdserver`: TCP server to communicate with ZeDMD
- Libraries: `libdmdutil`, `libzedmd`, `libserum`, etc.
- Default configuration: `~/.zeclock/config/dmdserver.ini`

**4. Install DotClk resources (animations + fonts)**

```bash
./scripts/install_dotclk_resources.sh
```

This downloads from [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources):
- **2300+ animations** `.scn` (pinball, classics, holidays...)
- **Bitmap fonts** `.fnt` original DotClk fonts

## Getting Started

**Launch dmdserver (terminal 1)**

```bash
~/.zeclock/bin/dmdserver -c ./config/dmdserver.ini -l -v
```

Options:
- `-a 0.0.0.0`: Listen on all interfaces
- `-p 6789`: TCP port (default)
- `-w`: Don't quit if no display connected
- `-l`: Enable logs

Or with config file:

```bash
~/.zeclock/bin/dmdserver -c ~/.zeclock/config/dmdserver.ini -w -l
```

**Launch zeClock (terminal 2)**

```bash
# Default: auto-rotating colors every minute
python -m zeclock.clock

# Fixed orange clock
python -m zeclock.clock --color orange

# Orange clock with blue animations
python -m zeclock.clock --color orange --animation-color blue
```

**Color options:**
- `--color`: Clock color - `orange`, `blue`, `red`, `purple`, `green`, `yellow`, `cyan`, `pink`, `auto` (default: auto-rotate every 60s)
- `--animation-color`: Animation color - same choices (default: same as clock color)

Or with animation example:

```bash
python examples/zeclock_demo.py
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
from zeclock.dmdserver_client import DMDServerClient
import time

# Load an animation
scene = load_scene(Path("~/.zeclock/resources/animations/Pinball/AFM/attract.scn").expanduser())

# Load a font
font = load_font(Path("~/.zeclock/resources/Fonts/Font1.fnt").expanduser())

# Connect to server
client = DMDServerClient("localhost", 6789)
client.connect()

# Display animation with time
for frame in scene:
    time_str = time.strftime("%H:%M")
    time_overlay = font.render_text(time_str, 128, 32)
    merged = overlay_or(frame, time_overlay)
    client.send_monochrome_frame(merged, color=(255, 128, 0))
    time.sleep(0.04)  # 25 FPS
```

## Configuration

**Environment variables**

```bash
# Resources folder
export ZECLOCK_RESOURCES="$HOME/.zeclock/resources"

# DMD server (if ZeDMD on WiFi)
export DMDSERVER_HOST="192.168.1.100"
export DMDSERVER_PORT="6789"
```

**dmdserver configuration file**

Edit `~/.zeclock/config/dmdserver.ini`:

```ini
[DMDServer]
Addr = 0.0.0.0
Port = 6789

[ZeDMD]
Enabled = 1
Device =              # Leave empty for auto-detection
Brightness = 10       # 0-15
Debug = 0

[ZeDMD-WiFi]
Enabled = 1
WiFiAddr = 192.168.1.100    # Your ZeDMD WiFi IP
```

## Project Structure

```
zeclock/
├── zeclock/
│   ├── __init__.py
│   ├── clock.py                 # Main clock
│   ├── config.py                # Configuration
│   ├── dmdserver_client.py      # TCP client for dmdserver
│   ├── overlay.py               # Animation/text merging
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── fnt_reader.py        # .fnt font reader
│   │   └── scn_reader.py        # .scn animation reader
│   └── resources/
│       └── fonts/
│           └── default.ttf      # Fallback font (Press Start 2P)
├── examples/
│   ├── run_clock.py             # Simple example
│   └── zeclock_demo.py          # Example with animations
├── scripts/
│   ├── install_libdmdutil.sh    # libdmdutil installation
│   ├── install_libdmdutil.py    # Python version
│   └── install_dotclk_resources.sh
├── setup.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

**Installed resources**

```
~/.zeclock/
├── bin/
│   ├── dmdserver                # Main executable
│   ├── libdmdutil.so            # Libraries
│   ├── libzedmd.so
│   └── ...
├── config/
│   └── dmdserver.ini            # Configuration
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
git clone https://github.com/votre-username/zeclock.git
cd zeclock
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

**dmdserver won't start**

```bash
# Check that libraries are installed
ls ~/.zeclock/bin/

# Check permissions
chmod +x ~/.zeclock/bin/dmdserver

# Test with verbose logs
dmdserver -v
```

**ZeDMD not detected**

```bash
# List serial ports
ls /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial*

# Force port in dmdserver.ini
[ZeDMD]
Device = /dev/ttyUSB0
```

**Animations not displaying**

```bash
# Check that resources are installed
ls ~/.zeclock/resources/animations/

# Reinstall if necessary
./scripts/install_dotclk_resources.sh
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
  - [ ] JeedomClock: Home automation data
  - [ ] MAMEClock: High scores
  - [ ] AWSClock: AWS costs
- [ ] **Advanced attract mode**: Random rotation between multiple clocks
- [ ] **Web interface**: Browser-based configuration
- [ ] **Galaga Clock**: Animation where Galaga shoots changing digits

## References

- **DotClk** (inspiration): [sigmafx/DotClk](https://github.com/sigmafx/DotClk)
- **DotClk Resources**: [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources)
- **libdmdutil**: [vpinball/libdmdutil](https://github.com/vpinball/libdmdutil)
- **ZeDMD**: [PPUC/ZeDMD](https://github.com/PPUC/ZeDMD)
- **ZeDMD OS**: [PPUC/zedmdos](https://github.com/PPUC/zedmdos)

## License

MIT License - see [LICENSE](LICENSE)

## Acknowledgments

- **SigmaFX** for the original DotClk project and its beautiful animations
- **vpinball** for libdmdutil and dmdserver
- **PPUC** for the ZeDMD hardware
- The **virtual pinball** community for the DMD ecosystem

## Support

- **Issues**: [GitHub Issues](https://github.com/your-username/zeclock/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/zeclock/discussions)
- **Discord**: [Pinball community Discord link]

---

**Made with ❤️ by ojacques - Inspired by the magic of retro pinball** 🎮✨
