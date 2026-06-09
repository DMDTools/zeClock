# Technical Design: Plugin Configuration UX

## Overview

This design adds a configuration schema system to the zeClock plugin framework, enabling: (1) automatic "configure me" messages on the DMD when plugins lack settings, (2) auto-generated web UI configuration forms, and (3) a geocoding service for human-friendly city-based location input.

## Architecture

The feature adds three layers to the existing plugin framework:
1. **Schema layer** — plugins declare their configuration needs via `config_schema`
2. **Runtime layer** — PluginManager detects unconfigured plugins (via `PluginNotConfiguredError`) and renders shared "configure me" frames
3. **UI layer** — Web UI auto-generates forms from schemas, with special handling for "city" type (autocomplete + geocoding)

## Components and Interfaces

### ConfigField (data model in `plugins/base.py`)

```python
@dataclass
class ConfigField:
    name: str           # Key in plugins.yaml settings dict
    label: str          # Human-readable label for Web UI (max 50 chars)
    field_type: str     # "text" | "number" | "city" | "list"
    required: bool = True
    description: str = ""  # max 200 chars
    default: Any = None
```

### PluginNotConfiguredError (exception in `plugins/base.py`)

```python
class PluginNotConfiguredError(Exception):
    """Raised by plugin.initialize() when required config is missing."""
    pass
```

### ClockPlugin.config_schema (property in `plugins/base.py`)

```python
@property
def config_schema(self) -> List[ConfigField]:
    """Override to declare configuration fields."""
    return []
```

### Geocoder (`zeclock/geocoder.py`)

```python
@dataclass
class GeoResult:
    latitude: float
    longitude: float
    display_name: str
    country: str

def geocode(city_name: str) -> Optional[GeoResult]
def search_cities(query: str) -> List[GeoResult]  # max 5 results
```

- Uses `urllib.request` (no new dependencies)
- User-Agent: `zeClock/1.0`
- Timeout: 10 seconds
- Caches results in memory (dict) for the session
- Input validation: rejects empty/whitespace queries

### REST API additions (`rest_remote.py`)

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/api/plugins/config-schema` | GET | — | `{"plugins": [{"name": str, "description": str, "schema": [ConfigField...]}]}` |
| `/api/geocode/search` | GET | `?q=<query>` (min 3 chars) | `{"results": [{"display_name": str, "country": str, "latitude": float, "longitude": float}]}` |

### PluginManager changes (`plugin_manager.py`)

- `activate_plugin()`: catches `PluginNotConfiguredError` → sets `plugin._unconfigured = True` (does NOT mark as failed)
- Other exceptions during `initialize()` → mark as failed (existing behavior)
- `get_frame()`: if active plugin is unconfigured, calls `_render_configure_message()`
- `_render_configure_message(name: str) -> Image`: renders "{Name}: Configure me" centered using MENU font

## Data Models

### Plugin config_schema examples

**Weather plugin:**
```python
config_schema = [
    ConfigField("city", "City", "city", required=True, description="Location for weather data")
]
```

**Stock plugin:**
```python
config_schema = [
    ConfigField("symbols", "Stock Symbols", "text", required=True,
                description="Comma-separated tickers (e.g. AAPL,MSFT)")
]
```

**Gif plugin:**
```python
config_schema = [
    ConfigField("gif_dir", "GIF Directory", "text", required=True,
                description="Path to directory containing .gif files")
]
```

### API response: `/api/plugins/config-schema`

```json
{
  "plugins": [
    {
      "name": "weather",
      "description": "Displays current weather conditions",
      "schema": [
        {"name": "city", "label": "City", "field_type": "city", "required": true, "description": "Location for weather data", "default": null}
      ]
    },
    {
      "name": "stock",
      "description": "Displays stock prices",
      "schema": [
        {"name": "symbols", "label": "Stock Symbols", "field_type": "text", "required": true, "description": "Comma-separated tickers", "default": null}
      ]
    },
    {
      "name": "gif",
      "description": "Displays animated GIFs on the DMD",
      "schema": [
        {"name": "gif_dir", "label": "GIF Directory", "field_type": "text", "required": true, "description": "Path to directory containing .gif files", "default": null}
      ]
    }
  ]
}
```

## Error Handling

- **PluginNotConfiguredError raised**: plugin stays in rotation, shows "configure me" message — NOT marked as failed
- **Other exceptions during initialize()**: plugin marked as failed, excluded from rotation (existing behavior preserved)
- **Geocoding failure** (network error, timeout, no results): `geocode()` returns `None`, plugin raises `PluginNotConfiguredError`
- **Web UI geocode search failure**: shows "No results found" in dropdown, doesn't crash or block input
- **Invalid city type field value**: if autocomplete was bypassed and raw text submitted, backend attempts geocoding on save; if fails, stores text only (no coordinates)
- **Empty/whitespace input to geocoder**: returns error immediately without network request

## Correctness Properties

### Property 1: Unconfigured vs Failed
A plugin raising `PluginNotConfiguredError` MUST NOT be marked as failed in the registry. It MUST remain in the rotation cycle displaying the configure message.

### Property 2: Geocoding Cache
The geocoder MUST NOT be called more than once per city name per application session (in-memory cache).

### Property 3: Consistent Rendering
The "configure me" frame MUST use the MENU bitmap font and the same color scheme as the existing text overlay feature.

### Property 4: Plugin Name Truncation
Plugin names longer than 12 characters MUST be truncated in the DMD configuration message to ensure readability on 128x32 displays.

## Testing Strategy

- Unit tests for `geocoder.py` with mocked HTTP responses (success, no results, timeout, network error)
- Unit tests for `PluginNotConfiguredError` handling in `plugin_manager.py` (unconfigured vs failed)
- Unit tests for configure message rendering (font, centering, truncation)
- Integration test: weather plugin with city name only → resolves coordinates and fetches weather
- Integration test: stock plugin with no symbols → shows configure message
- Integration test: gif plugin with empty dir → shows configure message
- Manual test: Web UI autocomplete dropdown for city field (debounce, selection, no results)
