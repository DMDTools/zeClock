# zeClock Architecture

This document describes the overall architecture, rendering data flow, and hardware pipeline of the **zeClock** project.

---

## 🗺️ Global Architecture (Data Flow)

**zeClock** is an asynchronous Python client application that communicates with ZeDMD hardware through a pluggable backend system. The default backend (`ZeDMDBackend`) drives the display directly via `libzedmd` (C shared library called through Python ctypes). An alternative backend (`DMDServerBackend`) communicates over TCP with a separate `dmdserver` process, useful for development with `virtual-dmd.py`.

```mermaid
graph TD
    subgraph "Application Layer (Python)"
        A["zeclock (clock.py)"] -->|Initializes| B["BitmapFont (fnt_reader.py)"]
        A -->|Initializes| C["Scene (scn_reader.py)"]
        A -->|Pre-computes frames| D["Overlay (overlay.py)"]
        A -->|Sends frames via| E["DMDBackend (backends/)"]
        A -->|Auto bootstrap| F2["Installer (installer.py)"]
    end

    subgraph "Backend Layer"
        E -->|"--backend zedmd (default)"| E1["ZeDMDBackend (ctypes/libzedmd)"]
        E -->|"--backend dmdserver"| E2["DMDServerBackend (TCP socket)"]
    end

    subgraph "Hardware & Rendering Layer"
        G["ZeDMD (ESP32 / Teensy Hardware)"]
        H["RGB LED Panels (128x32 / 256x64)"]
        I["dmd-simulator (SDL2 Graphical Simulation)"]
        F["dmdserver (TCP Daemon)"]
    end

    E1 -->|USB Serial / WiFi via libzedmd| G
    E2 -->|TCP Socket: Port 6789| F
    F -->|USB Serial / WiFi| G
    G -->|Matrix Bus| H
    F -->|Local Simulation| I
```

---

## 🧩 Application Component Architecture

### 1. Main Orchestrator: `ZeClock` (`clock.py`)

Manages global state and the time-based execution loop.

- **Render Loop (Tick Event)**: Runs as an async background task. Precisely calculates the remaining delay before the next frame to call `asyncio.sleep` and stabilize the framerate (25 FPS by default, or per-scene timing).
- **Animation State Machine**: Coordinates transitions between "Clock Only" mode and "Attract Mode" (retro pinball animations). After 5 seconds of inactivity, a new animation is randomly selected.
- **Async Pre-computer (`_precompute_animation`)**: To avoid any slowdown during real-time rendering, an async task loads a randomly chosen `.scn` animation, merges each frame with the current time (in two versions: with and without the colon `:` for blinking) and stores everything in RAM. The PinballPlugin and GifPlugin further optimize this by running pre-computation in a **background thread**, appending frames progressively so rendering can start before all frames are ready.
- **Dual Color**: Supports independent colors for the clock and animations, with an `auto` mode that rotates colors every 60 seconds.
- **CLI Entry Point**: The `main()` function exposes `--color`, `--animation-color`, and `--bootstrap` arguments.

### 2. Backend Abstraction Layer (`backends/`)

Pluggable backend system for DMD communication. All backends implement the `DMDBackend` abstract base class, ensuring the clock and plugins remain backend-agnostic.

- **`DMDBackend` ABC (`backends/base.py`)**: Defines the common interface:
  - `connect() -> bool`: Establish connection to the display.
  - `send_frame(image, buffered, color) -> bool`: Send a frame to the display.
  - `disconnect() -> None`: Close the connection.
  - `connected` property: Whether the backend is currently connected.
  - Context manager protocol (`__enter__` / `__exit__`): Calls `connect()` / `disconnect()` automatically.
- **`ZeDMDBackend` (`backends/zedmd.py`)**: Direct hardware communication via `libzedmd` (C shared library loaded through ctypes). Sends frames as RGB888 directly via `ZeDMD_RenderRgb888`, avoiding any Python-level pixel conversion. Supports WiFi and USB connections. On connect, auto-detects the physical panel dimensions via `ZeDMD_GetPanelWidth`/`ZeDMD_GetPanelHeight` and enables upscaling (`ZeDMD_EnableUpscaling`) so libzedmd handles centering/scaling when the frame size differs from the panel size. The upscale algorithm is controlled by `BackendConfig.upscale_mode` (`epx` by default, `hq2x`, or `nearest`). Includes connection health monitoring via a log callback registered with libzedmd (`ZeDMD_SetLogCallback`) that detects transport errors (StreamBytes failures, serial/TCP/UDP errors) in real-time, combined with a periodic `ZeDMD_GetPanelWidth` probe. Automatic reconnection uses exponential backoff and works for both USB and WiFi transports. Thread-safe error counting (via `threading.Lock`) protects shared state between the libzedmd internal thread and the Python asyncio thread.
- **`DMDServerBackend` (`backends/dmdserver.py`)**: TCP client using the DMDStream protocol (refactored from `dmdserver_client.py`). Used for development with `virtual-dmd.py`.
- **`BackendFactory` (`backends/factory.py`)**: Instantiates the correct backend based on `--backend` CLI argument (`auto`, `zedmd`, `dmdserver`). In `auto` mode, tries ZeDMD first, falls back to dmdserver.

#### DMDStream Protocol (used by DMDServerBackend)

- **Header** (big-endian):
  - Magic word: `DMDStream\x00` (10 bytes)
  - Version: 1 (uint8)
  - Mode: 3 = RGB565 (uint32 big-endian)
  - Dimensions: width, height (uint16 big-endian)
  - Flags: buffered, disconnectOthers (uint8 each)
  - Data size: payload length (uint32 big-endian)
- **Payload**: RGB565 big-endian data (2 bytes per pixel).
- **Persistent connection**: Socket stays open between frames for continuous streaming.

### 3. Binary File Readers (`readers/`)

Optimized parsers for decoding native DotClk hardware formats:

- **`BitmapFont` (`fnt_reader.py`)**: Decodes the binary `.fnt` format. Reads font headers (version, name, character count), maps ASCII characters with their advance width and kerning info, decompresses the global bitmap encoded at 4 bits per pixel (2 pixels per byte, dotmap format with header), and extracts individual grayscale glyphs. When rendering on HD displays (256×64) with SD fonts, `render_text()` renders at native resolution then delegates 2× upscaling to `overlay.upscale_2x()` (EPX, hq2x, or nearest-neighbor), controlled by the `upscale_mode` parameter. HD fonts (name ending with `_HD`) render directly at target size without upscaling.
- **`Scene` (`scn_reader.py`)**: Decodes the binary `.scn` animation format. Extracts the storyboard containing display metadata:
  - `first_frame_delay` / `last_frame_delay`: Hold delays on first/last frame (ms).
  - `first_blank` / `last_blank`: Whether display should be blank during those delays.
  - `clock_style`: Clock style (0 = Standard centered, 1 = Custom coordinates).
  - `custom_x` / `custom_y`: Custom clock position coordinates.
  - `frame_layer`: Layer order (0 = Clock behind animation, 1 = Clock above).
  - `frame_delay_ms`: Delay between frames (default 40ms = 25 FPS).

### 4. Composition Engine: `Overlay` (`overlay.py`)

This module handles image merging (clock on one side, animation on the other) and pixel-art upscaling. It faithfully implements the original DotClk hardware **`DotBlt`** algorithm and serves as the single entry point for all pixel-art upscaling in zeClock.

Mask metadata (`mask_data`, `mask_width_bytes`) is attached dynamically to PIL Image objects by the binary readers and accessed via typed `Any` casts in the overlay compositor.

- Each animation frame or bitmap text carries a binary mask (`mask_data`).
- **DotBlt Algorithm**:
  - If the upper layer's mask bit is `0`, the upper image pixel is applied (overwriting the background).
  - If the mask bit is `1`, the background pixel is preserved.
- **Dual Colorization** via `overlay_or_rgb`: Monochrome grayscale images are dynamically projected into RGB space. The clock receives the `color` (e.g., Orange) and the animation receives the `animation_color` (e.g., Blue), ensuring perfect readability of clock digits over retro pinball animations.
- **Pixel-art upscaling** — public API used by `BitmapFont.render_text()` and any other caller that needs to scale SD content to HD displays:
  - `upscale_nx(img, scale, mode)`: General dispatcher for arbitrary integer scale factors. Routes to the best algorithm for the given scale: `upscale_2x` for scale=2, `scale3x` for scale=3 with `mode="epx"`, and nearest-neighbor for all other scales. This is the preferred entry point when the scale factor is not known at compile time.
  - `upscale_2x(img, mode)`: Dispatcher for 2× upscaling. `mode="epx"` (default), `mode="hq2x"`, or `mode="nearest"`.
  - `epx_upscale_2x(img)`: EPX/Scale2x algorithm. Smooths diagonal edges and corners without introducing new colors or blurring. A hole-prevention rule ensures filled pixels are never replaced by empty ones (avoids gaps at inner corners of shapes such as "E"). Works on mode `L` (grayscale) images.
  - `hq2x(img)`: hq2x (High Quality 2×) algorithm by Maxim Stepin. Produces smoother curves and anti-aliased diagonals via neighbor interpolation. May introduce intermediate gray values. Best for pre-computed content (fonts, animations) where upscaling happens once at initialization. Works on mode `L` (grayscale) images.
  - `nearest_upscale_2x(img)`: Simple pixel doubling via `Image.Resampling.NEAREST`. Fastest method, works on any PIL image mode.
  - `scale3x(img)`: Scale3x/AdvMAME3x algorithm. Generalizes EPX to the 3× case — each source pixel expands to a 3×3 output block using neighbor comparisons on the full 3×3 neighborhood. Never introduces new colors; preserves pixel-art style. Useful for 3× scale factors (e.g., 128×32 → 384×96). Works on mode `L` (grayscale) images.
  - `_upscale_mask_2x(...)`: Internal helper that expands a DotBlt bit-mask 2× (each set bit → 2×2 block) so DotBlt compositing remains correct after scaling. Called automatically by both 2× upscalers when `mask_data` is present on the source image.
  - `_upscale_mask_nx(...)`: Internal helper that expands a DotBlt bit-mask by an arbitrary integer scale factor N (each set bit → N×N block). Used by `scale3x` and the nearest-neighbor fallback in `upscale_nx` to keep DotBlt compositing correct at any scale.

### 5. Plugin System (`plugins/`, `plugin_manager.py`, `plugin_registry.py`, `plugin_config.py`)

Extensible plugin architecture that allows contributors to author display plugins alternating with the default clock display during attract mode.

- **`PluginManager` (`plugin_manager.py`)**: Top-level orchestrator for the plugin lifecycle. Responsibilities:
  - **Discovery**: Scans built-in plugins (`zeclock/plugins/`) then user plugins (`~/.zeclock/plugins/`), importing Python files and finding `ClockPlugin` subclasses.
  - **Validation**: Checks plugin name format, description, and frame_delay_ms before registration.
  - **Loading**: Instantiates plugin classes, handles import errors gracefully (logs WARNING, skips file).
  - **Override logic**: User plugins with the same name as a built-in plugin replace the built-in.
  - **Configuration injection**: Merges plugin-specific YAML config with a `_helpers` key containing the `PluginHelpers` instance.
  - **Scheduling**: Selects the next plugin via weighted random selection from normalized frequencies.
  - **Activation**: Calls `initialize(config)` with a 10-second timeout; marks plugin as failed on error.
  - **Frame rendering**: Calls `render_frame()` with a 2-second timeout; holds last good frame on errors; deactivates after 5 consecutive failures.
  - **Duration enforcement**: Stops a plugin after 30 seconds or when it returns `None`.
- **`PluginRegistry` (`plugin_registry.py`)**: Internal data structure holding all loaded plugins with their state (active, failed), frequency, error count, and source (builtin/user). Provides frequency normalization so active plugins always sum to 100%.
- **`PluginConfig` (`plugin_config.py`)**: Loads `~/.zeclock/config/plugins.yaml`, creates defaults if missing, clamps values (frequency 0–100, clock_display_seconds 1–300), and handles invalid YAML gracefully.
- **`ClockPlugin` ABC (`base.py`)**: Defines the plugin interface contract. Plugins must implement:
  - `name` property: unique identifier (1–64 lowercase alphanumeric, hyphens, underscores).
  - `description` property: human-readable description (1–256 characters).
  - `frame_delay_ms` property: desired delay between frames (20–5000 ms).
  - `async initialize(config)`: prepare the plugin for rendering.
  - `async render_frame(width, height)`: produce a single RGB PIL Image frame, or `None` to signal completion.
  - `async cleanup()`: release resources on deactivation.
- **`PagedPlugin` (`base.py`)**: Abstract subclass of `ClockPlugin` for plugins that cycle through multiple display pages. Handles frame counting, page advancement, and automatic completion signaling. Subclasses implement `render_page(page, width, height)` instead of `render_frame()`. Accepts `page_duration_seconds` (2–30s, default 4) and manages internal paging state via `_init_paging()`.
- **Validation Utilities**: `validate_plugin_name()` and `validate_plugin_description()` enforce naming and description constraints at registration time.
- **Built-in Plugins**:
  - **PinballPlugin** (`pinball_plugin.py`): Wraps the existing `.scn` animation playback logic with DotBlt clock overlay composition. Randomly selects a scene file, pre-computes frames **progressively in a background thread** so `render_frame()` can start serving frames before all are ready — the clock keeps rendering while computation continues. Respects storyboard metadata (clock_style, custom_x, custom_y, frame_layer), and supports independent clock/animation colors. Thread-safe access to the frame list is protected by a `threading.Lock`.
  - **PongPlugin** (`pong_plugin.py`): Animated Pong game with real scoring and human-like AI. Two paddles play with randomized imperfections (reaction delay, limited speed, prediction error). The ball speeds up after each rally. A game resets after one side reaches 5 points or the plugin duration expires. Features score flash animations, serve delay blinking, and renders scores using the MENU font.
  - **GifPlugin** (`gif_plugin.py`): Picks a random animated GIF from a configurable directory (`~/.zeclock/plugins/gif/` by default), extracts frames **progressively in a background thread** so `render_frame()` can start serving frames before all are ready — the clock keeps rendering during loading. Scales frames to fit the display dimensions using a two-path strategy (pixel-perfect GIFs whose dimensions are exact integer multiples of the display size use the configured upscale algorithm — `epx`, `hq2x`, or `nearest` — while GIFs requiring arbitrary rescaling use LANCZOS). Thread-safe access to the frame list is protected by a `threading.Lock`. Plays the animation once, then signals completion.
  - **WeatherPlugin** (`weather_plugin.py`): Fetches weather data from the Open-Meteo API and cycles through display pages (current conditions, tomorrow's forecast, 3-day outlook) with configurable page duration. Supports 15-minute caching, staleness indicators, and Celsius/Fahrenheit units.
  - **StockPlugin** (`stock_plugin.py`): Fetches stock quotes from Yahoo Finance (no API key required) and displays current price, daily change, and change percentage for configured ticker symbols. Shows one symbol per page with configurable page duration. Detects market state (OPEN, PRE, POST, CLOSED) and displays extended hours price and variation when in pre/post market. Supports 10-minute caching with a staleness indicator.
- **`PluginHelpers` (`helpers.py`)**: Shared rendering utilities injected into plugins at initialization. Provides:
  - `create_frame()`: Creates blank RGB PIL Images at the correct display dimensions.
  - `render_text()`: Renders text using the BitmapFont system with positioning and colorization.
  - `draw_icon()`: Draws 16×16 pixel-art icons from raw bitmap data onto frames.
  - `composite_frames()`: Merges foreground onto background using DotBlt-style OR blending (non-black pixels overwrite).
  - `get_font_names()` / `get_text_width()`: Font discovery and text measurement for layout calculations.
  - `draw_staleness_indicator()`: Draws a blinking red dot in the top-right corner when data is stale (used by WeatherPlugin and StockPlugin).
  - `ConfettiAnimation`: Reusable particle animation class. Particles shoot upward from configurable cannon positions and fall with gravity. Supports three intensity levels (`small`/`medium`/`big`) and multiple color palettes (`CONFETTI_COLORS_PARTY`, `CONFETTI_COLORS_WARM`, `CONFETTI_COLORS_COOL`).

### 6. Automatic Bootstrap: `Installer` (`installer.py`)

Runtime initialization module that detects and automatically installs system dependencies:

- **Platform Detection**: Linux x64/aarch64, macOS arm64/x64, Windows x64.
- **libzedmd Installation**: Downloads the latest release from `PPUC/libzedmd` on GitHub to `~/.zeclock/lib/`.
- **DotClk Animations Installation**: Downloads 2300+ animations from `sigmafx/DotClk-Resources`. Fonts are bundled in the package (`zeclock/resources/fonts/`) and do not require downloading.
- **Interactive or Automatic Mode**: User prompt by default, or `--bootstrap` for silent installation.
- **dmdserver Installation** (optional): Available via `--with-dmdserver` for development setups.

---

## 🎨 Frame Rendering Pipeline

Logical steps executed each frame to build the final image sent to the display:

```mermaid
sequenceDiagram
    participant C as clock.py (ZeClock)
    participant F as fnt_reader.py (BitmapFont)
    participant O as overlay.py (Overlay)
    participant B as DMDBackend (backends/)

    C->>C: Event loop tick (dynamic timing)
    C->>F: Render current time text ("12:34" or "12 34")
    F->>F: Assemble .fnt font glyphs (centered or custom)
    F->>F: Pack text mask (bytearray bitwise ops)
    F-->>C: Return PIL Image (L-mode + mask_data attribute)
    
    alt Retro pinball animation is active
        C->>O: Merge time and animation frame (overlay_or_rgb)
        O->>O: Extract and apply DotBlt binary mask
        O->>O: Apply RGB tints (Clock Color vs Animation Color)
        O-->>C: Return merged frame (PIL RGB-mode)
    else No animation
        C->>C: Colorize time image to RGB (per-pixel bytearray)
    end
    
    C->>B: Send final RGB image via send_frame()
    B->>B: ZeDMDBackend: send RGB888 directly (no conversion needed)
    B->>B: DMDServerBackend: convert RGB888 → RGB565 big-endian for TCP
    B->>B: Transmit to hardware (libzedmd ctypes) or TCP socket
```

---

## 🔄 Animation State Machine

```mermaid
stateDiagram-v2
    [*] --> ClockOnly: Startup
    ClockOnly --> PluginSelect: clock_display_seconds elapsed
    PluginSelect --> PluginActive: Plugin selected (weighted random)
    PluginActive --> ClockOnly: Plugin signals completion or 30s max
    PluginActive --> ClockOnly: 5 consecutive errors (deactivate plugin)
    ClockOnly --> ClockOnly: Refresh every 500ms (colon blink)
    note right of PluginSelect: PluginManager selects via\nnormalized frequency weights
```

- **ClockOnly**: Displays time with colon blinking every 500ms. Duration configurable via `clock_display_seconds` (default 5s).
- **PluginSelect**: PluginManager selects the next plugin using weighted random selection from normalized frequencies.
- **PluginActive**: The selected plugin renders frames at its configured `frame_delay_ms`. Ends when the plugin returns `None`, 30 seconds elapse, or 5 consecutive errors occur.
- **Fallback**: If all plugins are deactivated due to errors, the system falls back to the built-in pinball animation behavior.
