# Plugin Authoring Guide

This guide walks you through creating custom plugins for zeClock. Plugins render content to the DMD display during attract mode — the periods between clock display.

## Table of Contents

- [Getting Started](#getting-started)
- [Plugin Interface Reference](#plugin-interface-reference)
- [Using PluginHelpers](#using-pluginhelpers)
- [Configuration](#configuration)
- [Lifecycle](#lifecycle)
- [Signaling Completion](#signaling-completion)
- [Using CachedDataMixin](#using-cacheddatamixin)
- [Using PagedPlugin](#using-pagedplugin)
- [Error Handling Best Practices](#error-handling-best-practices)
- [Installation](#installation)
- [Testing Your Plugin](#testing-your-plugin)
- [Example Plugins](#example-plugins)

---

## Getting Started

Here's a minimal "hello world" plugin that displays a greeting on the DMD:

```python
"""hello_world_plugin.py - A minimal zeClock plugin."""

from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class HelloWorldPlugin(ClockPlugin):
    """Displays 'Hello World' on the DMD display."""

    @property
    def name(self) -> str:
        return "hello-world"

    @property
    def description(self) -> str:
        return "Displays a hello world message"

    @property
    def frame_delay_ms(self) -> int:
        return 1000  # Update once per second

    async def initialize(self, config: dict) -> None:
        self._helpers = config["_helpers"]
        self._frames_rendered = 0
        self._max_frames = config.get("duration_seconds", 5)

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        if self._frames_rendered >= self._max_frames:
            return None  # Signal completion

        frame = self._helpers.create_frame()
        text_frame = self._helpers.render_text(
            "Hello World!", centered=True, y=12, color=(255, 128, 0)
        )
        frame = self._helpers.composite_frames(frame, text_frame)

        self._frames_rendered += 1
        return frame

    async def cleanup(self) -> None:
        self._frames_rendered = 0
```

Save this file to `~/.zeclock/plugins/hello_world_plugin.py` and it will be automatically discovered on the next zeClock startup.

---

## Plugin Interface Reference

All plugins must subclass `ClockPlugin` from `zeclock.plugins.base`. The abstract base class enforces the contract at class definition time — missing methods will raise `TypeError` when you try to instantiate your plugin.

### Properties

| Property | Type | Description | Constraints |
|----------|------|-------------|-------------|
| `name` | `str` | Unique plugin identifier | 1–64 chars, lowercase alphanumeric, hyphens, underscores. Pattern: `^[a-z0-9_-]{1,64}$` |
| `description` | `str` | Human-readable description | 1–256 characters, non-empty |
| `frame_delay_ms` | `int` | Delay between frames in milliseconds | Integer in range [20, 5000] |

### Methods

#### `async initialize(self, config: dict) -> None`

Called once before the first `render_frame()` call. Use this to:
- Store the `PluginHelpers` instance from `config["_helpers"]`
- Read plugin-specific settings from the config dict
- Fetch initial data (API calls, file loading, etc.)
- Set up internal state

**Timeout:** 10 seconds. If your `initialize()` takes longer or raises an exception, the plugin is marked as failed and excluded from scheduling for the session.

#### `async render_frame(self, width: int, height: int) -> Optional[Image.Image]`

Called repeatedly to produce frames for the DMD display. Must return:
- A `PIL.Image.Image` in RGB mode with dimensions `(width, height)` — the next frame to display
- `None` — to signal that the plugin has finished rendering

**Timeout:** 2 seconds per frame. If a frame takes longer or raises an exception, the last good frame is held on display.

**Parameters:**
- `width`: Display width in pixels (typically 128 or 256)
- `height`: Display height in pixels (typically 32 or 64)

#### `async cleanup(self) -> None`

Called when the plugin is deactivated. Use this to:
- Close network connections
- Release file handles
- Reset internal state for the next activation

---

## Using PluginHelpers

The `PluginHelpers` instance is injected into your plugin via the config dict during `initialize()`. It provides common rendering utilities so you don't need to work with raw PIL operations for typical tasks.

```python
async def initialize(self, config: dict) -> None:
    self._helpers = config["_helpers"]  # PluginHelpers instance
```

### Available Methods

#### `create_frame(color=(0, 0, 0)) -> Image.Image`

Creates a blank RGB frame at the display dimensions.

```python
# Black background (default)
frame = self._helpers.create_frame()

# Custom background color
frame = self._helpers.create_frame(color=(0, 0, 32))  # Dark blue
```

#### `render_text(text, x=0, y=0, color=(255, 128, 0), font_name="STANDARD", centered=False) -> Image.Image`

Renders text using the DotClk bitmap font system. Returns a frame-sized image with the text rendered on a black background.

```python
# Positioned text using MENU font (has uppercase letters)
text_frame = self._helpers.render_text("SCORE: 42", x=10, y=5, color=(0, 255, 0), font_name="MENU")

# Centered text
title_frame = self._helpers.render_text("WEATHER", centered=True, y=0, color=(255, 200, 0), font_name="MENU")

# Small text with full ASCII (SYSTEM font)
desc_frame = self._helpers.render_text("Partly cloudy", x=2, y=20, color=(200, 200, 200), font_name="SYSTEM")
```

**Parameters:**
- `text`: The string to render
- `x`: X position (ignored if `centered=True`)
- `y`: Y position for the text top
- `color`: RGB color tuple
- `font_name`: Font name without extension (e.g. `"STANDARD"`, `"MENU"`, `"SYSTEM"`)
- `centered`: Center text horizontally on the frame

### Available Fonts

The DotClk bitmap fonts have fixed character sets. Characters not in a font render as blank space — no error is raised.

| Font | Height | Characters | Best For |
|------|--------|-----------|----------|
| `STANDARD` | 21px | `0-9 : / A M P` (space) | Main clock display only. Too large for plugin content. |
| `MENU` | 11px | `0-9 A-Z & + - . / : < >` (space) | Temperatures, labels, headings. Uppercase only. |
| `SYSTEM` | 7px | Full ASCII (32–126): letters, digits, punctuation | Descriptions, city names, any text. Smallest font. |

**Important:** The `°` (degree) symbol is not available in any font. Use just the unit letter (e.g. `"23C"` instead of `"23°C"`).

**Choosing a font:**
- Need full text (lowercase, punctuation)? → `SYSTEM` (7px)
- Need readable labels/numbers? → `MENU` (11px)
- Only digits for a clock? → `STANDARD` (21px)

On a 32px tall display, you can fit:
- 1 line of STANDARD (21px) — leaves 11px
- 2 lines of MENU (11px each) — leaves 10px
- 4 lines of SYSTEM (7px each) — leaves 4px
- Mix: 1 MENU line + 2 SYSTEM lines = 25px

#### `draw_icon(frame, icon_data, x, y, size=(16, 16), color=(255, 255, 255)) -> Image.Image`

Draws a pixel-art icon onto an existing frame. Icons are stored as raw bitmap bytes (1 bit per pixel, row-major, MSB first).

```python
# Define a simple 8x8 heart icon (8 bytes)
heart_icon = bytes([
    0x66,  # .##..##.
    0xFF,  # ########
    0xFF,  # ########
    0xFF,  # ########
    0x7E,  # .######.
    0x3C,  # ..####..
    0x18,  # ...##...
    0x00,  # ........
])

frame = self._helpers.draw_icon(frame, heart_icon, x=5, y=8, size=(8, 8), color=(255, 0, 0))
```

#### `composite_frames(background, foreground) -> Image.Image`

Composites the foreground onto the background using OR blending (DotBlt style). Black pixels in the foreground are treated as transparent.

```python
frame = self._helpers.create_frame()
text_frame = self._helpers.render_text("Hello", x=10, y=5)
frame = self._helpers.composite_frames(frame, text_frame)
```

This is the standard pattern: create a base frame, render elements into separate layers, then composite them together.

#### `get_font_names() -> List[str]`

Lists available font names in the resources directory.

```python
fonts = self._helpers.get_font_names()
# e.g. ["MENU", "STANDARD", "SYSTEM"]
```

#### `get_text_width(text, font_name="STANDARD") -> int`

Calculates the pixel width of text without rendering. Useful for layout calculations.

```python
width = self._helpers.get_text_width("Temperature")
x_pos = (128 - width) // 2  # Center manually
```

#### `resolve_color(color_name, default="orange") -> Tuple[int, int, int]`

Resolves a color name to an RGB tuple using the shared palette. Useful for letting users configure colors by name in plugin settings.

```python
# Resolve a color from config
color = self._helpers.resolve_color("blue")        # (0, 0, 255) or similar
color = self._helpers.resolve_color("nope", "red") # Falls back to red
```

#### `render_text_right_aligned(text, y, margin=1, color=(255, 128, 0), font_name="STANDARD") -> Image.Image`

Renders text right-aligned on the frame with an optional right margin. Handy for scores, values, or any content that should hug the right edge.

```python
# Right-aligned temperature value
temp_frame = self._helpers.render_text_right_aligned("23C", y=5, color=(255, 200, 0), font_name="MENU")
frame = self._helpers.composite_frames(frame, temp_frame)
```

#### `render_text_centered_at(text, cx, y, color=(255, 128, 0), font_name="STANDARD") -> Image.Image`

Renders text centered horizontally around a specific x coordinate. Useful for centering text within a column or sub-region of the display.

```python
# Center text in the left half of a 128px display
col_frame = self._helpers.render_text_centered_at("MON", cx=32, y=2, font_name="MENU")
frame = self._helpers.composite_frames(frame, col_frame)
```

#### `draw_staleness_indicator(frame, total_frames, frame_delay_ms) -> None`

Draws a blinking red dot in the top-right corner of the frame. Use this to indicate that displayed data is stale (e.g., cached beyond its freshness window). The dot blinks at approximately 500ms intervals based on the frame count.

```python
if self._is_cache_stale():
    total_frames = self._current_page * self._frames_per_page + self._frame_count
    self._helpers.draw_staleness_indicator(frame, total_frames, self._frame_delay_ms)
```

---

## Configuration

Plugins receive their configuration through the `config` dict passed to `initialize()`. Plugin-specific settings are defined in `~/.zeclock/config/plugins.yaml`.

### Configuration File Format

```yaml
# ~/.zeclock/config/plugins.yaml
clock_display_seconds: 5  # How long clock shows between plugins (1-300)

plugins:
  - name: hello-world
    frequency: 30          # 30% chance of selection
    settings:
      duration_seconds: 5
      message: "Hello!"

  - name: weather
    frequency: 70          # 70% chance of selection
    settings:
      latitude: 48.8566
      longitude: 2.3522
      city_name: "Paris"
      temperature_unit: "celsius"
      language: "fr"               # "en" or "fr" for condition descriptions
      page_duration_seconds: 4
```

### Accessing Configuration in Your Plugin

The `config` dict passed to `initialize()` contains everything from the `settings` map in the YAML, plus the special `_helpers` key:

```python
async def initialize(self, config: dict) -> None:
    self._helpers = config["_helpers"]

    # Read your plugin-specific settings
    self._message = config.get("message", "Hello!")
    self._duration = config.get("duration_seconds", 5)
```

### Frequency

The `frequency` value (0–100) determines how likely your plugin is to be selected when the clock transitions to attract mode. Frequencies are normalized across all active plugins so they sum to 100%. For example, if two plugins have frequencies 70 and 30, they'll be selected 70% and 30% of the time respectively.

---

## Lifecycle

Understanding the plugin lifecycle helps you manage resources correctly.

```
Discovery → Loading → Initialization → Activation (Rendering) → Deactivation
```

### Detailed Flow

1. **Discovery**: On startup, the Plugin Manager scans plugin directories for Python files containing a `ClockPlugin` subclass.

2. **Loading**: Valid plugin classes are imported and registered by name. Invalid files (syntax errors, missing dependencies) are skipped with a warning.

3. **Initialization**: When a plugin is selected for display, `initialize(config)` is called with the plugin's configuration. You have 10 seconds to complete initialization.

4. **Activation (Rendering)**: `render_frame(width, height)` is called repeatedly at the interval specified by `frame_delay_ms`. This continues until:
   - Your plugin returns `None` (signaling completion)
   - 30 seconds of total render time elapses (maximum duration)
   - 5 consecutive render errors occur (automatic deactivation)

5. **Deactivation**: `cleanup()` is called to release resources. The display transitions back to clock-only mode.

### Timing Constraints

| Phase | Timeout | Consequence of Timeout |
|-------|---------|----------------------|
| `initialize()` | 10 seconds | Plugin marked as failed, excluded from session |
| `render_frame()` | 2 seconds per call | Last good frame held, error counter incremented |
| Total activation | 30 seconds max | Normal completion, transition to clock |

---

## Signaling Completion

Return `None` from `render_frame()` to tell the Plugin Manager that your plugin has finished displaying its content:

```python
async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
    if self._done:
        return None  # Done! Transition back to clock.

    # ... render your frame ...
    return frame
```

After returning `None`:
- `cleanup()` is called
- The display transitions back to clock-only mode
- After `clock_display_seconds` elapses, another plugin is selected

If you never return `None`, the 30-second maximum duration will stop your plugin automatically. This is not treated as an error.

---

## Using CachedDataMixin

If your plugin fetches data from an external API, use `CachedDataMixin` to get a standard cache-with-refresh pattern. It handles staleness tracking and preserves old cached data when a fetch fails.

```python
"""cached_plugin.py - Plugin using CachedDataMixin for API data."""

from typing import Any, Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin, CachedDataMixin


class CachedPlugin(CachedDataMixin, ClockPlugin):
    """Plugin that fetches and caches external data."""

    _cache_duration_seconds = 600  # 10 minutes (override default of 900)

    @property
    def name(self) -> str:
        return "my-cached-plugin"

    @property
    def description(self) -> str:
        return "Displays data from an external API"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def _fetch_data(self) -> Any:
        """Fetch fresh data. Return None on failure."""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.example.com/data") as resp:
                if resp.status == 200:
                    return await resp.json()
        return None

    async def initialize(self, config: dict) -> None:
        self._helpers = config["_helpers"]
        await self._refresh_cache_if_needed()

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        await self._refresh_cache_if_needed()
        if self._cache_data is None:
            return None  # No data available

        frame = self._helpers.create_frame()
        text_frame = self._helpers.render_text(
            str(self._cache_data), centered=True, y=12, font_name="SYSTEM"
        )
        return self._helpers.composite_frames(frame, text_frame)

    async def cleanup(self) -> None:
        pass
```

### CachedDataMixin API

| Attribute / Method | Description |
|---|---|
| `_cache_duration_seconds` | How long cached data stays fresh (default: 900s / 15 min). Override as a class attribute. |
| `_cache_data` | The cached data (any type). `None` when empty. |
| `_cache_fetched_at` | Timestamp of last successful fetch. |
| `is_cache_stale()` | Returns `True` if cache is empty or older than the configured duration. |
| `_refresh_cache_if_needed()` | Calls `_fetch_data()` if stale. On failure, preserves existing cached data. |
| `_fetch_data()` | **Abstract** — implement this to perform the actual API call. Return data on success, `None` on failure. |

---

## Using PagedPlugin

For plugins that display multiple pages of content (e.g., weather forecasts, stock tickers), subclass `PagedPlugin` instead of `ClockPlugin`. It handles frame counting, page advancement, and automatic completion signaling.

```python
"""paged_example.py - Plugin using PagedPlugin for multi-page display."""

from PIL import Image
from zeclock.plugins.base import PagedPlugin


class MyPagedPlugin(PagedPlugin):
    """Cycles through multiple pages of content."""

    @property
    def name(self) -> str:
        return "my-paged-plugin"

    @property
    def description(self) -> str:
        return "Displays multiple pages of information"

    async def initialize(self, config: dict) -> None:
        self._helpers = config["_helpers"]
        self._data = ["Page 1 content", "Page 2 content", "Page 3 content"]

        # Set up paging: 3 pages, 5 seconds each, 10 FPS
        page_duration = config.get("page_duration_seconds", 5)
        self._init_paging(
            total_pages=len(self._data),
            page_duration_seconds=page_duration,
            frame_delay_ms=100,
        )

    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a single page. Called automatically by the paging logic."""
        frame = self._helpers.create_frame()
        text_frame = self._helpers.render_text(
            self._data[page], centered=True, y=12, font_name="MENU"
        )
        return self._helpers.composite_frames(frame, text_frame)
```

### PagedPlugin API

| Method / Attribute | Description |
|---|---|
| `_init_paging(total_pages, page_duration_seconds=4, frame_delay_ms=100)` | Call from `initialize()` to set up page cycling. `page_duration_seconds` is clamped to 2–30. |
| `render_page(page, width, height) -> Image.Image` | **Abstract** — implement this instead of `render_frame()`. Receives the zero-based page index. |
| `frame_delay_ms` | Managed automatically by `PagedPlugin` (set via `_init_paging`). |
| `render_frame()` | Handled internally — advances pages and returns `None` after all pages are shown. |
| `cleanup()` | Resets paging state. Override and call `await super().cleanup()` if you need additional cleanup. |

### Combining PagedPlugin with CachedDataMixin

For plugins that fetch data and display it across multiple pages, combine both:

```python
from typing import Any
from PIL import Image
from zeclock.plugins.base import CachedDataMixin, PagedPlugin


class MyDataPlugin(CachedDataMixin, PagedPlugin):
    """Fetches data and displays it across multiple pages."""

    _cache_duration_seconds = 600

    @property
    def name(self) -> str:
        return "my-data-plugin"

    @property
    def description(self) -> str:
        return "Fetches and pages through external data"

    async def _fetch_data(self) -> Any:
        # ... fetch from API ...
        return ["item1", "item2", "item3"]

    async def initialize(self, config: dict) -> None:
        self._helpers = config["_helpers"]
        await self._refresh_cache_if_needed()

        total = len(self._cache_data) if self._cache_data else 0
        self._init_paging(total_pages=total, page_duration_seconds=4)

    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        frame = self._helpers.create_frame()
        text_frame = self._helpers.render_text(
            self._cache_data[page], centered=True, y=12, font_name="SYSTEM"
        )
        return self._helpers.composite_frames(frame, text_frame)
```

---

## Error Handling Best Practices

The Plugin Manager is designed to be resilient. Here's how errors are handled and how to write robust plugins:

### What Happens on Errors

| Situation | Plugin Manager Response |
|-----------|----------------------|
| `render_frame()` raises an exception | Last good frame held on display, error counter +1 |
| `render_frame()` exceeds 2s timeout | Same as exception — last frame held, counter +1 |
| 5 consecutive render errors | Plugin deactivated for the session |
| Successful frame after errors | Error counter resets to 0 |

### Best Practices

1. **Handle network failures gracefully**: If your plugin fetches data, cache it and display cached data when the network is unavailable.

```python
async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
    if self._data is None:
        # No data available, signal completion rather than erroring
        return None
    # ... render with cached data ...
```

2. **Don't let exceptions bubble up from render_frame**: Catch expected errors and either display a fallback or signal completion.

```python
async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
    try:
        data = self._process_data()
        return self._render(data, width, height)
    except ValueError:
        # Data is bad, signal completion
        return None
```

3. **Keep render_frame fast**: The 2-second timeout is generous, but aim for milliseconds. Do heavy work in `initialize()` or in a background task.

4. **Use initialize() for setup that can fail**: If your plugin needs an API key, file, or network resource, validate it in `initialize()`. Raising there cleanly excludes the plugin rather than causing repeated render errors.

5. **Clean up resources in cleanup()**: Close connections, cancel timers, and reset state so the plugin is ready for the next activation.

---

## Installation

### User Plugins

Place your plugin file in the user plugin directory:

```
~/.zeclock/plugins/your_plugin.py
```

The directory is created automatically on first startup if it doesn't exist. Your plugin will be discovered on the next zeClock startup.

### File Naming

The file name doesn't matter for discovery — the Plugin Manager looks for classes that subclass `ClockPlugin`. However, using a descriptive name like `weather_plugin.py` or `scoreboard_plugin.py` is recommended.

### Overriding Built-in Plugins

If your plugin returns the same `name` as a built-in plugin (e.g. `"weather"` or `"pinball"`), your version replaces the built-in. This is logged at INFO level.

### Activating Your Plugin

Add your plugin to `~/.zeclock/config/plugins.yaml`:

```yaml
plugins:
  - name: hello-world
    frequency: 50
    settings:
      duration_seconds: 10
```

Or use the CLI to test it immediately:

```bash
# Run only your plugin
zeclock --plugins hello-world

# Run alongside other plugins
zeclock --plugins hello-world,weather
```

### Verifying Discovery

Use `--list-plugins` to confirm your plugin was discovered:

```bash
zeclock --list-plugins
```

Output:
```
pinball          Pinball animation display                active
pong             Pong game where the score is the current time  active
gif              Displays animated GIFs on the DMD       active
weather          Current weather and forecast display     active
stock            Stock prices and daily change display    active
hello-world      Displays a hello world message          active
```

---

## Testing Your Plugin

You can test your plugin in isolation without running the full zeClock application.

### Basic Test Script

```python
"""test_my_plugin.py - Test a plugin in isolation."""

import asyncio
from pathlib import Path
from PIL import Image
from zeclock.plugins.helpers import PluginHelpers

# Import your plugin
from my_plugin import MyPlugin


async def test_plugin():
    # Set up helpers (adjust resources_path to your zeClock installation)
    resources_path = Path.home() / ".zeclock" / "resources"
    helpers = PluginHelpers(width=128, height=32, resources_path=resources_path)

    # Create and initialize the plugin
    plugin = MyPlugin()
    config = {
        "_helpers": helpers,
        # Add your plugin-specific settings here
        "my_setting": "value",
    }
    await plugin.initialize(config)

    # Render frames until completion
    frame_count = 0
    while True:
        frame = await plugin.render_frame(128, 32)
        if frame is None:
            print(f"Plugin completed after {frame_count} frames")
            break

        # Validate frame
        assert isinstance(frame, Image.Image), "Must return PIL Image"
        assert frame.mode == "RGB", f"Expected RGB, got {frame.mode}"
        assert frame.size == (128, 32), f"Expected (128, 32), got {frame.size}"

        frame_count += 1
        if frame_count > 1000:
            print("Safety limit reached")
            break

    await plugin.cleanup()
    print("Test passed!")


if __name__ == "__main__":
    asyncio.run(test_plugin())
```

### Using pytest

```python
"""test_my_plugin.py - pytest tests for a custom plugin."""

import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image
from zeclock.plugins.helpers import PluginHelpers


@pytest.fixture
def helpers(tmp_path):
    """Create a PluginHelpers instance for testing."""
    fonts_dir = tmp_path / "Fonts"
    fonts_dir.mkdir()
    return PluginHelpers(width=128, height=32, resources_path=tmp_path)


@pytest.fixture
def config(helpers):
    """Create a basic config dict."""
    return {
        "_helpers": helpers,
        "my_setting": "test_value",
    }


@pytest.mark.asyncio
async def test_plugin_initializes(config):
    from my_plugin import MyPlugin

    plugin = MyPlugin()
    await plugin.initialize(config)
    # No exception means success


@pytest.mark.asyncio
async def test_plugin_renders_valid_frames(config):
    from my_plugin import MyPlugin

    plugin = MyPlugin()
    await plugin.initialize(config)

    frame = await plugin.render_frame(128, 32)
    assert frame is not None
    assert isinstance(frame, Image.Image)
    assert frame.mode == "RGB"
    assert frame.size == (128, 32)

    await plugin.cleanup()


@pytest.mark.asyncio
async def test_plugin_signals_completion(config):
    from my_plugin import MyPlugin

    plugin = MyPlugin()
    await plugin.initialize(config)

    # Render until completion
    for _ in range(10000):
        frame = await plugin.render_frame(128, 32)
        if frame is None:
            break
    else:
        pytest.fail("Plugin never signaled completion")

    await plugin.cleanup()
```

### Saving Frames for Visual Inspection

```python
# Save individual frames as PNG for visual debugging
frame = await plugin.render_frame(128, 32)
frame.save("frame_001.png")

# Or scale up for easier viewing (DMD pixels are tiny)
scaled = frame.resize((512, 128), Image.NEAREST)
scaled.save("frame_001_scaled.png")
```

---

## Example Plugins

### Annotated Weather Plugin

The built-in weather plugin (`zeclock/plugins/weather_plugin.py`) is a complete real-world example. Here's an annotated walkthrough of its key patterns:

```python
"""WeatherPlugin - Annotated example of a production zeClock plugin."""

from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class WeatherPlugin(ClockPlugin):
    """Displays weather conditions and forecasts from Open-Meteo API."""

    # --- Properties ---
    # These are simple, returning fixed or computed values.

    @property
    def name(self) -> str:
        return "weather"  # Lowercase, alphanumeric + hyphens/underscores

    @property
    def description(self) -> str:
        return "Current weather and forecast display"  # Max 256 chars

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms  # 100ms = 10 FPS for smooth transitions

    # --- Initialization ---
    # Validate config, set up state, fetch initial data.

    async def initialize(self, config: dict) -> None:
        # Always grab the helpers instance first
        self._helpers = config.get("_helpers")

        # Read required configuration — signal completion if missing
        self._latitude = config.get("latitude")
        self._longitude = config.get("longitude")
        self._city_name = config.get("city_name", "")
        # Language for condition descriptions: "en" or "fr"
        self._language = config.get("language", "en")

        missing = []
        if self._latitude is None:
            missing.append("latitude")
        if self._longitude is None:
            missing.append("longitude")
        if not self._city_name:
            missing.append("city_name")

        if missing:
            # Log and mark as not initialized — render_frame will return None
            self._initialized = False
            return

        # Read optional settings with defaults and clamping
        self._temperature_unit = config.get("temperature_unit", "celsius")
        page_duration = config.get("page_duration_seconds", 4)
        self._page_duration_seconds = max(2, min(30, int(page_duration)))

        # Pre-calculate frame counts for page cycling
        self._frames_per_page = (
            self._page_duration_seconds * 1000 + self._frame_delay_ms - 1
        ) // self._frame_delay_ms

        # Reset state for this activation
        self._current_page = 0
        self._frame_count = 0
        self._initialized = True

        # Fetch weather data (uses 15-minute cache)
        await self._refresh_cache_if_needed()

    # --- Rendering ---
    # Cycle through 4 pages, return None when done.

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        # Guard: not initialized or no data
        if not self._initialized:
            return None
        if self._cache is None:
            return None

        # All pages displayed? Signal completion.
        if self._current_page >= 4:
            return None

        # Render the current page using helpers
        frame = self._render_page(self._current_page, width, height)

        # Advance frame counter, switch pages when duration reached
        self._frame_count += 1
        if self._frame_count >= self._frames_per_page:
            self._frame_count = 0
            self._current_page += 1

        return frame

    # --- Cleanup ---
    # Reset state so the plugin is ready for next activation.

    async def cleanup(self) -> None:
        self._current_page = 0
        self._frame_count = 0

    # --- Rendering Helpers (private) ---
    # Each page is a separate method for clarity.

    def _render_page(self, page: int, width: int, height: int) -> Image.Image:
        frame = self._helpers.create_frame()

        if page == 0:
            # Current conditions: icon + temperature + description + city
            icon_data = get_weather_icon(self._cache.current_condition_code)
            frame = self._helpers.draw_icon(frame, icon_data, 2, 1, (16, 16))

            temp_str = f"{round(self._cache.current_temp)}°C"
            temp_frame = self._helpers.render_text(temp_str, x=20, y=1, color=(255, 128, 0))
            frame = self._helpers.composite_frames(frame, temp_frame)

        elif page == 1:
            # Tomorrow: label + icon + high/low temps
            label = self._helpers.render_text("Tomorrow", x=2, y=0, color=(255, 200, 0))
            frame = self._helpers.composite_frames(frame, label)

        elif page == 2:
            # 3-day outlook: 3 columns with icons and high temps
            col_width = width // 3
            for i, day in enumerate(self._cache.forecast_days[:3]):
                icon_x = i * col_width + (col_width - 16) // 2
                icon_data = get_weather_icon(day.condition_code)
                frame = self._helpers.draw_icon(frame, icon_data, icon_x, 2, (16, 16))

        elif page == 3:
            # 7-day overview: 7 narrow columns with single-letter day,
            # 12x12 icon, and high temp
            col_width = width // 7
            for i, day in enumerate(self._cache.forecast_days[:7]):
                col_x = i * col_width
                icon_x = col_x + (col_width - 12) // 2
                icon_data = get_weather_icon(day.condition_code)
                frame = self._helpers.draw_icon(frame, icon_data, icon_x, 9, (12, 12))

        return frame
```

### Key Patterns to Follow

1. **Store helpers in initialize**: `self._helpers = config["_helpers"]`
2. **Validate config early**: Check required fields in `initialize()`, set a flag if invalid
3. **Guard render_frame**: Return `None` immediately if not properly initialized
4. **Track frame count for page timing**: Use `frame_delay_ms` and page duration to calculate frames per page
5. **Use composite_frames for layering**: Render text/icons into separate frames, then composite onto the base
6. **Signal completion explicitly**: Return `None` when your content is fully displayed
7. **Reset state in cleanup**: Prepare for the next activation cycle
