# zeClock Technical Stack

This document details the technologies, libraries, protocols, and tools that make up the **zeClock** project.

---

## 🛠️ Technical Stack Components

### 1. Programming Language and Runtime

- **Python 3.9+**: Main language chosen for its flexibility, rich image processing ecosystem, and ease of integration.
  - Leverages modern async improvements (`asyncio`) and advanced typing structures.

### 2. Image Processing Engine

- **Pillow (PIL Fork) >= 9.0**: Handles all graphical operations for the clock.
  - **Canvas creation**: Monochrome grayscale images (8-bit `L` mode) and colorized true-color images (24-bit `RGB` mode).
  - **Composition and layers**: Cropping (`crop`), pasting (`paste`), and merging animation frames with clock text.
  - **Pixel manipulation**: Direct access via `img.load()` for parsing 4-bit binary formats.

### 3. Numerical Computing & Pixel Manipulation

- **Pure Python + Pillow**: All pixel operations are implemented without NumPy for maximum portability (runs on Raspberry Pi and low-power ARM boards without AVX support).
  - **Grayscale colorization**: Per-pixel intensity × RGB color tuple via `bytearray` operations.
  - **RGB565 conversion** (DMDServerBackend only): Per-pixel bit packing using `struct.pack_into` for big-endian TCP output.
  - **RGB888 passthrough** (ZeDMDBackend): Raw PIL Image bytes sent directly to libzedmd — no Python-level pixel conversion needed.
  - **Mask processing**: Bit manipulation via Python `bytearray` and bitwise operators.
  - **Image compositing**: Byte-level iteration over `Image.tobytes()` data for DotBlt blending.
  - **Pixel-art upscaling** (`overlay.py`): Public 2× upscaling API consolidated in the overlay module. `upscale_2x(img, mode)` is the single entry point; it dispatches to `epx_upscale_2x()` (EPX/Scale2x algorithm, default), `hq2x()` (High Quality 2× — smoother curves via interpolation, may introduce intermediate gray values, best for pre-computed content), or `nearest_upscale_2x()` (pixel doubling). Used by `BitmapFont.render_text()` when rendering SD fonts on HD displays (256×64). EPX smooths diagonal edges and corners without introducing new colors or blurring, preserving pixel-art style. A hole-prevention rule ensures filled pixels are never replaced by empty ones (avoids gaps at inner corners). All upscalers also upscale any attached `mask_data` bitfield via `_upscale_mask_2x()` so DotBlt compositing remains correct after scaling.
  - **Performance**: At 128×32 (4096 pixels), pure Python loops are fast enough for 25 FPS rendering.

### 4. Concurrency & Asynchronous Programming

- **asyncio**: Python's native framework for async code (`async`/`await`).
  - **Stable display frequency**: The main loop dynamically calculates each frame's execution time to adapt `asyncio.sleep` and guarantee a regular framerate.
  - **Background pre-computation**: Loading and rendering `.scn` animations runs via `asyncio.create_task`. The main display loop stays smooth and responsive.
  - **Cooperative yielding**: `await asyncio.sleep(0)` in intensive loading loops to yield back to the event loop.
- **threading** (standard module): Used in `ZeDMDBackend` for thread-safe access to the stream error flag. The libzedmd log callback executes on libzedmd's internal Run thread, so a `threading.Lock` protects the shared error flag accessed by both the callback thread and the Python asyncio thread.

### 5. Network Protocol & Communication

- **Direct Hardware (libzedmd via ctypes)**: Default communication path using the `ZeDMDBackend`.
  - Loads `libzedmd.so` / `.dylib` / `.dll` from `~/.zeclock/lib/` via `ctypes.CDLL`.
  - C API calls: `ZeDMD_GetInstance`, `ZeDMD_OpenWiFi` / `ZeDMD_Open`, `ZeDMD_SetFrameSize`, `ZeDMD_EnableUpscaling`, `ZeDMD_SetBrightness`, `ZeDMD_RenderRgb888`, `ZeDMD_Close`, `ZeDMD_SetLogCallback`, `ZeDMD_FormatLogMessage`, `ZeDMD_GetPanelWidth`, `ZeDMD_GetPanelHeight`.
  - **Log callback**: A ctypes `CFUNCTYPE` callback is registered via `ZeDMD_SetLogCallback` to intercept libzedmd internal log messages. `ZeDMD_FormatLogMessage` resolves `va_list` arguments into readable strings. Stream error patterns (e.g., "StreamBytes failed", "libserialport error", "TCP stream error", "UDP stream error") immediately set a thread-safe error flag to signal connection loss.
  - **RGB888 passthrough**: Raw RGB bytes from PIL Image are sent directly to libzedmd without any Python-level pixel conversion (3 bytes per pixel: Red, Green, Blue).
  - **Connection modes**: WiFi (IP address) or USB serial (device path or auto-detection).
  - **Panel resolution detection**: On connect, queries `ZeDMD_GetPanelWidth` / `ZeDMD_GetPanelHeight` to auto-detect the physical panel dimensions and adapts the frame size accordingly.
  - **Upscaling**: Calls `ZeDMD_EnableUpscaling` so libzedmd handles centering/scaling when the configured frame size differs from the physical panel size.
  - **Connection error handling**: Simple strategy — on any stream error detected via the log callback, `send_frame()` immediately closes the instance and returns `False`. The caller (main loop) handles the wait and reconnection with exponential backoff (initial 2s, max 30s, ×1.5 multiplier). No periodic health checks or failure thresholds.

- **Sunrise/Sunset API** (`api.sunrise-sunset.org`): Free REST API used by `BrightnessScheduler` to fetch daily sunrise/sunset times based on geographic coordinates. No API key required. Results are cached for 30 minutes. Used only when `[location]` is configured with latitude/longitude.

- **MQTT** (via `remote/mqtt_remote.py`): Primary remote control protocol. Bidirectional pub/sub communication for controlling the clock (on/off, force plugin, display text, brightness) and publishing state. Supports Home Assistant MQTT Discovery for automatic entity creation. Broker address configured in `zeclock.ini`.

- **REST API** (via `remote/rest_remote.py`): HTTP-based remote control as a complement for simple integrations and Recalbox Web Manager. Provides the same command set as MQTT via HTTP endpoints, plus:
  - **Web UI** served as static files from `zeclock/remote/web/` at `/ui/` (root `/` redirects to it). Provides a browser-based control panel.
  - **Plugin list** (`GET /api/plugins`): Returns all registered plugins with state, frequency, source, active/forced status, and optional `web_controls` metadata exposed by plugins via `get_web_controls()`.
  - **Brightness** (`/api/brightness`): `GET` returns current brightness state (override, SW dimming, time-only flag, auto/manual mode). `POST {"brightness": 0-15}` sets manual brightness override. `POST /api/brightness/auto` clears the override and resumes automatic scheduling.
  - **Speaker Timer sub-API** (`/api/speaker-timer/`): Dedicated REST endpoints for the conference timer plugin — `GET status`, `POST start` (also forces the speaker-timer plugin active), `POST pause`, `POST reset` (also resumes normal plugin rotation), `POST set` (accepts `{"seconds": N}` or `{"minutes": N}`).

- **TCP Sockets (standard `socket` module)**: Alternative communication via `DMDServerBackend` for development.
  - **DMDStream network header** (big-endian):
    - Magic word: `DMDStream\x00` (10 bytes)
    - Version: 1 (uint8)
    - Mode: 3 = RGB565 (uint32 big-endian)
    - Dimensions: width, height (uint16 big-endian)
    - Flags: buffered, disconnectOthers (uint8 each)
    - Data size: payload length (uint32 big-endian)
  - **Payload**: RGB565 big-endian data (2 bytes per pixel, width × height × 2 bytes total).
  - **Persistent connection**: Socket stays open between frames for continuous streaming.

### 6. Command-Line Interface

- **argparse** (standard module): CLI argument parsing.
  - `--color`: Clock color (orange, blue, red, purple, green, yellow, cyan, pink, auto).
  - `--animation-color`: Animation color (independent from clock).
  - `--backend`: Backend selection (auto, zedmd, dmdserver). Default: auto.
  - `--wifi-addr`: ZeDMD WiFi IP address (overrides config file).
  - `--device`: ZeDMD USB serial device path (overrides config file).
  - `--brightness`: Display brightness 0-15 (overrides config file).
  - `--hd`: Use ZeDMD HD resolution (256×64) instead of standard (128×32).
  - `--width` / `--height`: Override display dimensions in pixels.
  - `--upscale`: Upscaling algorithm for HD mode (`epx`, `hq2x`, or `nearest`). `epx` (default) uses EPX/Scale2x for smooth pixel-art scaling without new colors; `hq2x` uses High Quality 2× for smoother curves via interpolation (may introduce intermediate values, best for pre-computed content); `nearest` does fast pixel doubling.
  - `--bootstrap`: Non-interactive automatic resource installation.
  - `--no-prompt`: Disables interactive prompts.

### 8. Configuration File (`~/.zeclock/config/zeclock.ini`)

INI-format config file parsed by `backend_config.py`. CLI arguments always take precedence over file values.

| Section | Key | Values | Default | Description |
|---------|-----|--------|---------|-------------|
| `[zedmd]` | `wifi_addr` | IP address string | — | ZeDMD WiFi address |
| `[zedmd]` | `device` | device path string | — | ZeDMD USB serial device |
| `[zedmd]` | `brightness` | 0–15 | 10 | Display brightness |
| `[dmdserver]` | `host` | hostname/IP | `localhost` | dmdserver host |
| `[dmdserver]` | `port` | integer | 6789 | dmdserver TCP port |
| `[display]` | `width` | integer | 128 | Frame width in pixels |
| `[display]` | `height` | integer | 32 | Frame height in pixels |
| `[display]` | `upscale` | `epx` \| `nearest` | `epx` | Upscale algorithm used by libzedmd when the frame size differs from the physical panel size |
| `[brightness_schedule]` | `default` | schedule line | — | Default brightness schedule (all days) |
| `[brightness_schedule]` | `monday`..`sunday` | schedule line | — | Day-specific brightness schedule |
| `[brightness_schedule]` | `max_brightness` | 1–15 | 7 | Maximum HW brightness for 100% |
| `[brightness_schedule]` | `time_only` | `HH:MM-HH:MM` | — | Time-only mode range (no plugins) |

| `[location]` | `latitude` | float | — | Geographic latitude for sunrise/sunset |
| `[location]` | `longitude` | float | — | Geographic longitude for sunrise/sunset |
| `[location]` | `sunrise_brightness` | 0–100 | — | Brightness % during daytime |
| `[location]` | `sunset_brightness` | 0–100 | — | Brightness % during nighttime |
| `[mqtt]` | `enabled` | `true` \| `false` | `false` | Enable MQTT remote control |
| `[mqtt]` | `host` | hostname/IP | `localhost` | MQTT broker address |
| `[mqtt]` | `port` | integer | 1883 | MQTT broker port |
| `[mqtt]` | `username` | string | — | MQTT authentication username |
| `[mqtt]` | `password` | string | — | MQTT authentication password |
| `[mqtt]` | `device_id` | string | `zeclock` | Unique device identifier (used in topics) |
| `[mqtt]` | `topic_prefix` | string | `zeclock` | MQTT topic prefix (e.g. `zeclock/command/...`) |
| `[mqtt]` | `ha_discovery` | `true` \| `false` | `true` | Enable Home Assistant MQTT Discovery |
| `[mqtt]` | `ha_discovery_prefix` | string | `homeassistant` | HA Discovery topic prefix |
| `[mqtt]` | `state_interval` | float (≥5) | 30.0 | Seconds between state publish messages |
| `[rest_api]` | `enabled` | `true` \| `false` | `false` | Enable REST API remote control |
| `[rest_api]` | `host` | hostname/IP | `0.0.0.0` | REST API listen address |
| `[rest_api]` | `port` | integer | 8080 | REST API listen port |

Schedule line format: `HH:MM-HH:MM brightness%, HH:MM-HH:MM brightness%, ...` (supports overnight ranges and multiple entries per day).

### 7. DMD Hardware Layer

- **libzedmd** (C shared library from `PPUC/libzedmd`): Provides direct communication with ZeDMD hardware via an `extern "C"` API. Called through Python ctypes. Supports WiFi and USB connections.
- **ZeDMD**: Open-source firmware for ESP32 / Teensy boards designed to drive RGB LED panels (128x32 or 256x64 pixels). Receives data from libzedmd via USB Serial or WiFi.
- **dmdserver** (optional, built from `libdmdutil`): C++ daemon for development use. Listens for TCP connections (port 6789 by default), decodes RGB565 frames, and forwards them to hardware or a simulator. Used with `--backend dmdserver`.

---

## 📦 Dependency Management

### Production Dependencies (Runtime)

Declared in `pyproject.toml`:

| Package | Version | Role |
|---------|---------|------|
| `pillow` | >= 9.0 | Image processing, canvas, composition |
| `pyyaml` | >= 6.0 | YAML configuration parsing (plugin system) |
| `aiohttp` | >= 3.8 | Async HTTP client (weather/stock API calls) |
| `colorama` | >= 0.4.6 | ANSI terminal colors (bootstrap messages) |

### Optional Dependencies

| Group | Packages | Role |
|-------|----------|------|
| `zedmd` | `pyserial` | Direct USB communication with ZeDMD (without dmdserver) |
| `dev` | `pytest>=7.0`, `pytest-asyncio>=0.21`, `hypothesis>=6.0`, `black>=22.0`, `flake8>=4.0`, `mypy>=0.950`, `pyyaml>=6.0` | Code quality & testing |

---

## 🚀 Packaging and Distribution

### Single Configuration: `pyproject.toml` (PEP 621)

The project exclusively uses the modern PEP 621 standard with the `setuptools` backend:

```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project.scripts]
zeclock = "zeclock.clock:main"

[tool.setuptools.package-data]
zeclock = ["resources/fonts/*.fnt"]
```

The `package-data` directive ensures bitmap font files (`.fnt`) in `zeclock/resources/fonts/` are included in built wheels and sdists. This allows plugins and the rendering engine to locate fonts via `importlib.resources` or `__file__`-relative paths without relying solely on the runtime bootstrap to `~/.zeclock/resources/`.

### Compatibility with Modern Package Managers

| Tool | Command | Description |
|------|---------|-------------|
| **pipx** | `pipx install zeclock` | Permanent isolated installation |
| **uvx** | `uvx --from ... zeclock` | Instant execution without installation |
| **pip** | `pip install -e ".[dev]"` | Editable development mode |

### Runtime Bootstrap Mechanism

Rather than post-install hooks (incompatible with Wheels and sandboxed environments), zeClock uses a **first-launch bootstrap**:

1. On startup, `installer.py` checks for `~/.zeclock/lib/libzedmd.so` and `~/.zeclock/resources/animations/`.
2. Fonts are bundled in the package (`zeclock/resources/fonts/`) — no download needed.
3. If animations or libzedmd are missing, an interactive wizard offers automatic download.
4. Non-interactive alternative: `zeclock --bootstrap`.

---

## 🔧 Binary File Formats

### `.fnt` Format (DotClk Bitmap Fonts)

```
┌─────────────────────────────────────────────┐
│ Header                                       │
│  - version (uint16 LE)                       │
│  - font_name_len (uint8)                     │
│  - font_name (ASCII, font_name_len bytes)    │
│  - cnt_font_info (uint16 LE)                 │
├─────────────────────────────────────────────┤
│ Character Info (× cnt_font_info)             │
│  - ascii_char (uint8)                        │
│  - width (uint16 LE)                         │
│  - kerning (uint16 LE)                       │
├─────────────────────────────────────────────┤
│ Dotmap (global bitmap)                       │
│  - dots_width (uint16 LE)                    │
│  - dots_height (uint16 LE)                   │
│  - dots_bpp (uint16 LE)                      │
│  - has_mask (uint16 LE)                      │
│  - dots_data (4-bit/pixel, 2 pixels/byte)    │
│  - mask_data (1-bit/pixel, if has_mask)      │
└─────────────────────────────────────────────┘
```

### `.scn` Format (DotClk Animations)

```
┌─────────────────────────────────────────────┐
│ Scene Header                                 │
│  - version (uint16 LE)                       │
│  - cnt_item_dotmap (uint16 LE)               │
│  - cnt_item_storyboard (uint16 LE)           │
├─────────────────────────────────────────────┤
│ Storyboard (× cnt_item_storyboard)          │
│  - first_frame_delay (uint16 LE, ms)         │
│  - first_frame_layer (uint16 LE)             │
│  - first_blank (uint16 LE)                   │
│  - frame_delay_ms (uint16 LE)                │
│  - frame_layer (uint16 LE)                   │
│  - last_frame_delay (uint16 LE, ms)          │
│  - last_frame_layer (uint16 LE)              │
│  - last_blank (uint16 LE)                    │
│  - clock_style (uint8: 0=std, 1=custom)      │
│  - custom_x (uint8)                          │
│  - custom_y (uint8)                          │
│  - reserved (17 bytes)                       │
├─────────────────────────────────────────────┤
│ Dotmap Frames (× cnt_item_dotmap)            │
│  - dots_width (uint16 LE)                    │
│  - dots_height (uint16 LE)                   │
│  - dots_bpp (uint16 LE)                      │
│  - has_mask (uint16 LE)                      │
│  - dots_data (4-bit/pixel)                   │
│  - mask_data (1-bit/pixel, if has_mask)      │
└─────────────────────────────────────────────┘
```

---

## 📊 Performance Targets

| Metric | Value |
|--------|-------|
| Framerate | 25 FPS (40ms/frame) or per-animation |
| Resolution | 128×32 or 256×64 pixels |
| ZeDMD format | RGB888 (3 bytes/pixel, sent directly) |
| DMDServer format | RGB565 big-endian (2 bytes/pixel, over TCP) |
| End-to-end latency | < 50ms |
| RAM (pre-computation) | ~50-200 MB depending on frame count |
| Clock colon blink | 500ms on / 500ms off |
