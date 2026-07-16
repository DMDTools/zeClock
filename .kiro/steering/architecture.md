---
inclusion: auto
---

# Architecture Decisions and Patterns

## Backend Abstraction

- `DMDBackend` abstract base class (`backends/base.py`) defines the interface: `connect()`, `send_frame()`, `disconnect()`, `connected` property
- `BackendFactory` (`backends/factory.py`) instantiates the correct backend based on CLI `--backend` argument
- Two implementations: `ZeDMDBackend` (ctypes/libzedmd, direct hardware) and `DMDServerBackend` (TCP socket, development)
- Context manager protocol for automatic connect/disconnect

## Plugin System

- **State machine**: `CLOCK_ONLY` -> `PLUGIN_SELECT` -> `PLUGIN_ACTIVE` -> back to `CLOCK_ONLY`
- **Weighted random selection**: Plugins have configurable frequency, normalized to 100%
- **Plugin ABCs**: `ClockPlugin` (single frames) and `PagedPlugin` (multi-page cycling)
- **Discovery**: Built-in plugins in `zeclock/plugins/`, user plugins in `~/.zeclock/plugins/`
- **Lifecycle**: discovery -> validation -> initialization (10s timeout) -> render (2s timeout per frame) -> cleanup
- **Error handling**: 5 consecutive failures deactivates a plugin; falls back to pinball animations

## HD Support

- Auto-detection of panel dimensions from hardware (`ZeDMD_GetPanelWidth`/`ZeDMD_GetPanelHeight`)
- Pixel-art upscaling algorithms in `overlay.py`: EPX/Scale2x (default), hq2x, Scale3x, nearest-neighbor
- `upscale_nx()` is the general dispatcher; `upscale_2x()` for 2x specifically
- HD fonts (suffix `_HD`) render directly; SD fonts upscale via EPX at render time
- DotBlt masks are upscaled alongside images to maintain compositing correctness

## Rendering Pipeline

1. Main async loop calculates precise timing for stable framerate (25 FPS default)
2. `BitmapFont` renders time text as grayscale PIL Image with binary mask
3. `overlay.py` composites clock + animation using DotBlt algorithm (mask-based blending)
4. Dual colorization: clock and animation get independent RGB tints
5. Final RGB frame sent to backend (`RGB888` for ZeDMD, `RGB565` for dmdserver)

## Remote Control

- Protocol-agnostic via shared `CommandHandler` in `remote/`
- **MQTT** (`remote/mqtt_remote.py`): bidirectional, Home Assistant Discovery support
- **REST API** (`remote/rest_remote.py`): HTTP endpoints + static Web UI served at `/ui/`
- Command priority: text overlay > screen off > forced plugin > normal state machine

## Background Pre-computation

- Heavy plugins (PinballPlugin, GifPlugin) pre-compute frames in **daemon threads**
- Frames are appended progressively so rendering can start before all frames are ready
- Thread-safe access via `threading.Lock`
- Cooperative yielding with `await asyncio.sleep(0)` in async loading loops

## Key Design Principles

- **Pure Python + Pillow only** for pixel operations (no NumPy) - ensures Raspberry Pi portability
- **Minimal production dependencies**: Pillow, PyYAML, aiohttp, colorama
- **Backend-agnostic**: Clock and plugins never interact directly with hardware
- **Graceful degradation**: Import errors logged and skipped, failed plugins deactivated, reconnection with exponential backoff
