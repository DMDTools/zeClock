# zeClock

> 🕒 A smart DMD clock with a plugin system, for [ZeDMD](https://github.com/PPUC/ZeDMD), [Pixelcade](https://pixelcade.org/), and [PIN2DMD](https://pin2dmd.com/) displays

Tired of simple DMD clocks that only show time and maybe a GIF? zeClock is a full-featured DMD clock with built-in plugins (pinball animations, weather, stocks, pong, speaker timer and more), a plugin system to create your own, and connectivity to your ecosystem via REST API, MQTT, and Home Assistant.

zeClock can drive ZeDMD hardware directly via `libzedmd`, or output to **any device supported by [libdmdutil](https://github.com/vpinball/libdmdutil)'s `dmdserver`** -- including ZeDMD, Pixelcade, and PIN2DMD -- with multiple devices active simultaneously.

It comes with a **web interface** for easy configuration, and a **browser-based virtual renderer** so you can try everything before buying [ZeDMD-compatible hardware](https://github.com/PPUC/ZeDMD#which-led-panels-are-lcd-screens-are-supported).

For an autonomous setup, install zeClock on a **Raspberry Pi** connected to ZeDMD via USB — just power the Pi and get going with a 24/7 clock.

![Demo](docs/zeclock-demo.gif)

## Quick Start

**No hardware required** — try zeClock in your browser in seconds:

```bash
git clone https://github.com/DMDTools/zeClock.git
cd zeClock
pip install -e ".[dev]"
zeclock --bootstrap
make dev-start-virtual
```

Open **http://localhost:3000** — the clock is running with a WebGL DMD shader in your browser!

For HD mode (256x64): `make dev-start-virtual-hd` · To stop: `make dev-stop` or `Ctrl+C`

## Plugins

zeClock alternates between a clock display and animated plugins. Each plugin renders content on the DMD for a few seconds, then returns to the clock.

### Pinball

Retro pinball DMD animations with clock overlay. Plays randomly from 2300+ `.scn` animation files with DotBlt composition. Powered by [DotClk-Resources](https://github.com/sigmafx/DotClk-Resources), kindly shared by [SigmaFX](https://github.com/sigmafx) with authorization to use the proprietary `.scn` animations.

![Demo](docs/zeclock-pinball.gif)

### Pong

Two AI players compete in a real Pong match. The score persists across activations — the clock only takes over between points. First to 5 wins with confetti celebration.

![Demo](docs/zeclock-pong.gif)

### Weather

Current conditions, tomorrow's forecast, 3-day outlook, and 7-day overview. Data from Open-Meteo API (no key required), cached 15 minutes.

![Demo](docs/zeclock-weather.gif)

### Eyes

Animated robot eyes tracking a buzzing fly. The eyes react with expressions (surprised, annoyed, sleepy) based on the fly's behavior.

![Demo](docs/zeclock-eyes.gif)

### Stock

Real-time stock prices from Yahoo Finance with intraday sparkline graphs. Supports multiple symbols, pre/post market data.

![Demo](docs/zeclock-stocks.gif)

### GIF

Plays animated GIFs with support for multiple source directories and weighted random rotation. Drop `.gif` files in `~/.zeclock/plugins/gif/` or configure multiple directories.

A great source: [11,000+ DMD GIF pack](https://www.neo-arcadia.com/forum/viewtopic.php?t=67065) (donationware, with a free 600 GIF pack available at the same link).

![Demo](docs/zeclock-gif.gif)

### Speaker Timer

Conference countdown timer visible from stage. Control via Web UI or REST API: set duration, start, pause, reset. The progress bar transitions from green → orange (20% remaining) → red (10% remaining), then blinks at 00:00 when elapsed.

You can also send messages to the display at any time through the Web UI or API (e.g. "WRAP UP!", "5 min remaining!").

![Demo](docs/zeclock-speaker-timer.gif)

### Paragliding

AI-based paragliding flyability forecast from [Paraglidable](https://paraglidable.com/). Cycles through configured spots showing today's FLY/XC/Takeoff percentages (color-coded: green ≥80%, orange ≥60%, red <60%), plus a 3-day forecast page per spot. Data cached 30 minutes. Requires a free API key.

![Demo](docs/zeclock-paraglidable.gif)

## Plugin Configuration

Plugins are configured in `~/.zeclock/config/plugins.yaml`:

```yaml
clock_display_seconds: 10
plugins:
  - name: pinball
    frequency: 30
  - name: pong
    frequency: 20
  - name: weather
    frequency: 20
    settings:
      city_name: Grenoble
      latitude: 45.19
      longitude: 5.72
      language: fr
  - name: eyes
    frequency: 10
  - name: stock
    frequency: 10
    settings:
      symbols: AAPL,MSFT,^FCHI
      page_duration_seconds: 5
  - name: gif
    frequency: 15
    settings:
      gif_dirs:
        - path: "~/.zeclock/plugins/gif/Arcade"
          weight: 30
          recursive: true
        - path: "~/.zeclock/plugins/gif/Movies"
          weight: 10
          recursive: false
  - name: speaker-timer
    frequency: 0
    settings:
      yellow_threshold: 20
      red_threshold: 10
  - name: paragliding
    frequency: 15
    settings:
      api_key: YOUR_PARAGLIDABLE_API_KEY
      language: fr
      # Optional: filter to specific spots (comma-separated substrings)
      # spots: "St Hilaire,Chamrousse"
      page_duration_seconds: 5
```

- **clock_display_seconds**: How long the clock is shown between plugins (default: 5)
- **frequency**: Relative probability of selecting each plugin (higher = more often). Set to 0 for plugins activated only via API (like speaker-timer).

Override from CLI: `zeclock --plugins pinball,pong`

### Per-Plugin Settings

| Plugin | Setting | Description |
|--------|---------|-------------|
| **weather** | `city_name` | City name (triggers geocoding if no lat/lon) |
| | `latitude` / `longitude` | Coordinates for weather data |
| | `language` | Language for conditions (e.g. `fr`, `en`) |
| | `temperature_unit` | `celsius` (default) or `fahrenheit` |
| | `page_duration_seconds` | Duration per weather page (default: 4) |
| **stock** | `symbols` | Comma-separated tickers (e.g. `AAPL,MSFT,^FCHI`) |
| | `page_duration_seconds` | Duration per stock page (default: 5) |
| **gif** | `gif_dirs` | List of directory entries (see example above) |
| | Each entry: `path` | Directory containing `.gif` files (required) |
| | `weight` | Selection probability (default: 50) |
| | `recursive` | Search subdirectories (default: true) |
| **speaker-timer** | `yellow_threshold` | % remaining to switch to orange (default: 20) |
| | `red_threshold` | % remaining to switch to red (default: 10) |
| **pinball** | `color` | Animation color name (default: `orange`) |
| | `animation_color` | Separate animation color (default: same as `color`) |
| **pong** | `color` | Game color name (default: `orange`) |
| **eyes** | `color` | Eyes color name (default: `cyan`) |
| **paragliding** | `api_key` | Paraglidable API key (required, free from paraglidable.com) |
| | `language` | `en` or `fr` (default: `en`) |
| | `spots` | Comma-separated spot name filters (optional) |
| | `page_duration_seconds` | Duration per page (default: 5) |


## Installation

### Option A: Global Isolated Install (pipx / uvx)

```bash
# With pipx:
pipx install git+https://github.com/DMDTools/zeClock.git

# OR with uvx (no install needed):
uvx --from git+https://github.com/DMDTools/zeClock.git zeclock
```

### Option B: Development Install (Source)

```bash
git clone https://github.com/DMDTools/zeClock.git
cd zeClock
pip install -e ".[dev]"
```

### Bootstrap

On first launch, zeClock downloads resources automatically. Or run manually:

```bash
zeclock --bootstrap
```

This installs to `~/.zeclock/`:
- **libzedmd** — native ZeDMD communication library
- **2300+ retro animations** (`.scn`) and bitmap fonts (`.fnt`) from [DotClk-Resources](https://github.com/sigmafx/DotClk-Resources)

## Usage

### With ZeDMD hardware

```bash
# Auto-detect backend and connection
zeclock

# Fixed orange clock
zeclock --color orange

# Only specific plugins
zeclock --plugins pinball,weather
```

### CLI Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `--backend` | `auto`, `zedmd`, `dmdserver` | `auto` | Backend selection ([details](docs/backends.md)) |
| `--wifi-addr` | IP address | from config | ZeDMD WiFi address |
| `--device` | path | auto-detect | USB serial device |
| `--brightness` | 0-15 | 10 | Display brightness |
| `--hd` | — | — | Force HD resolution (256x64) |
| `--color` | color name | `auto` | Clock color (auto = rotate every minute) |
| `--plugins` | comma-separated | all | Only activate listed plugins |
| `--bootstrap` | — | — | Install resources |

### Configuration File

`~/.zeclock/config/zeclock.ini`:

```ini
[zedmd]
wifi_addr = 192.168.0.35
brightness = 10

[display]
font = STANDARD

[location]
# Used by brightness scheduling (sunrise/sunset auto-brightness)
# Note: the weather plugin has its own location in plugins.yaml
latitude = 45.1885
longitude = 5.7245
city_name = Grenoble

[brightness_schedule]
max_brightness = 7
default = 22:00-08:00 10%
sunrise_brightness = 100%
sunset_brightness = 10%
# time_only = 22:00-08:00

[rest_api]
enabled = true
host = 0.0.0.0
port = 8080

[dmdserver]
host = localhost
port = 6789
```

### Brightness Scheduling

Brightness is percentage-based (0–100%). 100% maps to `max_brightness` hardware level.

```ini
[brightness_schedule]
# Per-day (overnight ranges supported)
default = 22:00-08:00 10%
monday = 08:00-18:00 80%, 22:00-08:00 10%

# Or sunrise/sunset auto (requires [location])
sunrise_brightness = 100%
sunset_brightness = 10%

# "Time only" mode: clock only, no plugins during these hours
time_only = 22:00-08:00
```

## Remote Control (REST API & MQTT)

### REST API

Enable in config, then control via HTTP:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Current status |
| `POST` | `/api/screen/on` | Turn screen on |
| `POST` | `/api/screen/off` | Turn screen off |
| `POST` | `/api/plugin/force` | Force plugin `{"plugin": "name"}` |
| `POST` | `/api/plugin/resume` | Resume normal rotation |
| `POST` | `/api/text` | Display text `{"text": "...", "duration": 10}` |
| `POST` | `/api/speaker-timer/set` | Set timer `{"seconds": 300}` |
| `POST` | `/api/speaker-timer/start` | Start/resume timer |
| `POST` | `/api/speaker-timer/pause` | Pause timer |
| `POST` | `/api/speaker-timer/reset` | Reset timer |

### MQTT

```ini
[mqtt]
enabled = true
host = 192.168.1.100
port = 1883
device_id = zeclock
ha_discovery = true
```

Install: `pip install zeclock[mqtt]`

Topics: `zeclock/<device_id>/command`, `zeclock/<device_id>/state`, `zeclock/<device_id>/availability`

When `ha_discovery = true`, zeClock auto-registers in Home Assistant (switch + sensors).

## Two Operating Modes

### 🖥️ Local Development (PC / Mac)

ZeDMD hardware optional — browser emulation at `http://localhost:3000`.

### 🍓 Autonomous (Raspberry Pi)

24/7 unattended operation with read-only filesystem, WiFi auto-connect, and automatic startup via systemd. Just plug in the Pi, connect ZeDMD via USB, and power on — zeClock runs forever.

#### Prerequisites

- Raspberry Pi 4 (or 5) with WiFi
- microSD card (8 GB+)
- ZeDMD display connected via USB
- Power supply for the Pi and ZeDMD

#### Getting the Image

Download the latest `zeclock-rpi.img.xz` from [GitHub Releases](https://github.com/DMDTools/zeClock/releases), then flash:

```bash
xzcat zeclock-rpi.img.xz | sudo dd of=/dev/sdX bs=4M status=progress
sync
```

Or use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) / [balenaEtcher](https://etcher.balena.io/).

#### Boot Flow

On power-up, the Pi goes through the following sequence:

```
Power On
  │
  ├── 1. Kernel + initramfs
  │       └── overlayfs mounted (root becomes read-only, writes go to RAM)
  │
  ├── 2. systemd starts
  │       ├── setup-data-partition.service
  │       │     └── Creates /data (f2fs) partition on first boot, mounts it
  │       ├── init-data-partition.service
  │       │     └── Initializes directory structure, extracts DotClk resources
  │       ├── bind-persistent-dirs.service
  │       │     └── Restores WiFi connections, SSH keys, journal from /data
  │       ├── NetworkManager.service
  │       │     └── Connects to known WiFi (or waits for portal config)
  │       ├── rfkill-unblock-wifi.service
  │       │     └── Ensures WiFi radio is enabled
  │       ├── wifi-connect.service
  │       │     └── If no WiFi connected → exposes "zeClock-Setup" AP with captive portal
  │       └── zeclock.service
  │             └── Starts zeClock (auto-detects ZeDMD via USB)
  │
  └── ✅ Clock is running (~15-25s from power-on to display)
```

#### WiFi Configuration

**Option A — Pre-configured WiFi (headless):**
Set WiFi credentials at image build time via `deploy/rpi/variables.auto.pkrvars.hcl`:
```hcl
wifi_ssid     = "MyNetwork"
wifi_password = "MyPassword"
```

**Option B — Captive Portal (no keyboard/monitor needed):**
1. Power on the Pi without pre-configured WiFi
2. After ~30s, the Pi exposes an AP named **zeClock-Setup**
3. Connect to that AP from your phone/laptop
4. A captive portal opens — select your WiFi network and enter the password
5. The Pi connects and starts zeClock automatically

WiFi credentials persist in `/data/networkmanager/` — they survive reboots and power cuts.

#### Filesystem Architecture

```
SD Card Partition Layout:
  mmcblk0p1   /boot/firmware   FAT32   512 MB   Boot files (read-only)
  mmcblk0p2   /                ext4    ~2.5 GB  Root filesystem (read-only via overlay)
  mmcblk0p3   /data            f2fs    remaining Persistent data (read-write)
```

The root filesystem is **read-only** at runtime — protected by an initramfs-based overlayfs. All runtime writes go to RAM (tmpfs) and are lost on reboot. This makes the system immune to SD card corruption from power cuts.

Only `/data` is writable on the SD card, using **F2FS** (Flash-Friendly File System) which is resilient to power-loss.

| Persistent path | Purpose |
|-----------------|---------|
| `/data/zeclock/config/` | zeClock configuration (`zeclock.ini`, `plugins.yaml`) |
| `/data/zeclock/resources/` | Fonts and pinball animations |
| `/data/zeclock/state/` | Runtime state (Pong scores, etc.) |
| `/data/networkmanager/` | WiFi connection profiles |
| `/data/ssh/` | SSH host keys |
| `/data/log/journal/` | Persistent system journal (capped at 10 MB) |

#### Configuration on the Pi

SSH into the Pi (default user: `zeclock` / password: `zeclock`):

```bash
ssh zeclock@zeclock.local
```

Edit configuration:
```bash
nano /data/zeclock/config/zeclock.ini
sudo systemctl restart zeclock
```

The REST API is enabled by default on port 8080 — access the web UI at `http://zeclock.local:8080`.

#### Maintenance Mode

To update software or install packages, disable the read-only overlay:

```bash
# Add "skipoverlay" to kernel command line
sudo mount -o remount,rw /boot/firmware
sudo sed -i 's/$/ skipoverlay/' /boot/firmware/cmdline.txt
sudo reboot

# After maintenance, remove the flag and reboot to re-enable protection
sudo sed -i 's/ skipoverlay//' /boot/firmware/cmdline.txt
sudo reboot
```

#### Building the Image Yourself

See [`deploy/rpi/`](deploy/rpi/) for the full Packer-based build system. Quick start:

```bash
cd deploy/rpi
./build.sh   # Requires Docker with privileged mode
```

Output: `zeclock-rpi.img` (~3 GB) — ready to flash.

The image is also built automatically via GitHub Actions on every merge to `main` and on git tags (e.g. `v1.0.0`). See the [Releases page](https://github.com/DMDTools/zeClock/releases).

## Development

```bash
make test              # Run tests + lint + type check
make dev-start-virtual # Virtual DMD in browser (128x32)
make dev-start-virtual-hd  # Virtual DMD HD (256x64)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## Troubleshooting

**libzedmd not found** — Run `zeclock --bootstrap` to install.

**ZeDMD not detected (WiFi)** — Check `ping <ip>` and set `wifi_addr` in config or via `--wifi-addr`.

**ZeDMD not detected (USB)** — List ports with `ls /dev/ttyUSB*` and use `--device`.

**Animations not displaying** — Run `zeclock --bootstrap` to reinstall resources.

## References

- [sigmafx/DotClk](https://github.com/sigmafx/DotClk) — Original DotClk inspiration
- [sigmafx/DotClk-Resources](https://github.com/sigmafx/DotClk-Resources) — 2300+ animations
- [PPUC/libzedmd](https://github.com/PPUC/libzedmd) — ZeDMD native library
- [PPUC/ZeDMD](https://github.com/PPUC/ZeDMD) — ZeDMD hardware
- [vpinball/libdmdutil](https://github.com/vpinball/libdmdutil) — DMD utility library with `dmdserver` for multi-device output (ZeDMD, Pixelcade, PIN2DMD)

## License

MIT — see [LICENSE](LICENSE)

---

**Made with ❤️ by ojacques — Inspired by the magic of retro pinball** 🎮✨
