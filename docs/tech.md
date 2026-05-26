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

- **NumPy >= 1.20**: Essential for optimizing high-frequency rendering performance.
  - **Mask processing**: Converting compact binary masks to 2D arrays via `np.unpackbits` / `np.packbits` (bitorder='little').
  - **Vectorized operations**: Mask extraction, DotBlt algorithm application, and colorization in a single NumPy pass.
  - **RGB565 conversion**: Vectorized RGB888 → RGB565 big-endian transformation via bit shifts (`>> 3`, `>> 2`, `<< 11`, `<< 5`).
  - **Matrix colorization**: Projecting grayscale levels into RGB space via intensity multiplication.

### 4. Concurrency & Asynchronous Programming

- **asyncio**: Python's native framework for async code (`async`/`await`).
  - **Stable display frequency**: The main loop dynamically calculates each frame's execution time to adapt `asyncio.sleep` and guarantee a regular framerate.
  - **Background pre-computation**: Loading and rendering `.scn` animations runs via `asyncio.create_task`. The main display loop stays smooth and responsive.
  - **Cooperative yielding**: `await asyncio.sleep(0)` in intensive loading loops to yield back to the event loop.

### 5. Network Protocol & Communication

- **TCP Sockets (standard `socket` module)**: Communication with the DMD server via TCP/IP socket.
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
  - `--bootstrap`: Non-interactive automatic resource installation.
  - `--no-prompt`: Disables interactive prompts.

### 7. DMD Server and Hardware Layer (C++)

The zeClock ecosystem relies on native C++ system components:

- **dmdserver** (built from `libdmdutil`): C++ daemon running locally. Listens for TCP connections (port 6789 by default), decodes RGB565 frames sent by zeClock, and forwards them to the hardware display controller.
- **ZeDMD**: Open-source firmware for ESP32 / Teensy boards designed to drive RGB LED panels (128x32 or 256x64 pixels). Receives data from `dmdserver` via USB Serial or WiFi.

---

## 📦 Dependency Management

### Production Dependencies (Runtime)

Declared in `pyproject.toml`:

| Package | Version | Role |
|---------|---------|------|
| `pillow` | >= 9.0 | Image processing, canvas, composition |
| `numpy` | (latest) | Vectorized binary operations, RGB565 conversion |

### Optional Dependencies

| Group | Packages | Role |
|-------|----------|------|
| `zedmd` | `pyserial` | Direct USB communication with ZeDMD (without dmdserver) |
| `dev` | `pytest>=7.0`, `black>=22.0`, `flake8>=4.0`, `mypy>=0.950` | Code quality |

### Additional Dependencies (requirements.txt)

| Package | Role |
|---------|------|
| `colorama >= 0.4.6` | ANSI terminal colors (bootstrap messages) |

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
```

### Compatibility with Modern Package Managers

| Tool | Command | Description |
|------|---------|-------------|
| **pipx** | `pipx install zeclock` | Permanent isolated installation |
| **uvx** | `uvx --from ... zeclock` | Instant execution without installation |
| **pip** | `pip install -e ".[dev]"` | Editable development mode |

### Runtime Bootstrap Mechanism

Rather than post-install hooks (incompatible with Wheels and sandboxed environments), zeClock uses a **first-launch bootstrap**:

1. On startup, `installer.py` checks for `~/.zeclock/bin/dmdserver` and `~/.zeclock/resources/`.
2. If elements are missing, an interactive wizard offers automatic download.
3. Non-interactive alternative: `zeclock --bootstrap`.

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
| Network format | RGB565 big-endian (2 bytes/pixel) |
| End-to-end latency | < 50ms |
| RAM (pre-computation) | ~50-200 MB depending on frame count |
| Clock colon blink | 500ms on / 500ms off |
