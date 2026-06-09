# Implementation Plan: Plugin Configuration UX

## Overview

Implement configuration schema declaration for plugins, "configure me" DMD messages, a geocoding service, and auto-generated web UI forms with city autocomplete.

## Tasks

- [x] 1. Add ConfigField schema and PluginNotConfiguredError to plugin base class (`zeclock/plugins/base.py`). Add `ConfigField` dataclass with fields: name, label, field_type, required, description, default. Add `config_schema` property to `ClockPlugin` (returns empty list by default). Add `PluginNotConfiguredError` exception class.
- [x] 2. Handle unconfigured state in PluginManager (`plugin_manager.py`). Catch `PluginNotConfiguredError` in `activate_plugin()` — set unconfigured flag, do NOT mark as failed. Other exceptions still mark as failed. Add `_render_configure_message(name)` using MENU font, centered, truncate name to 12 chars. In `get_frame()`, return configure message frame for unconfigured plugins.
- [x] 3. Create geocoder module (`zeclock/geocoder.py`). Implement `GeoResult` dataclass. Implement `geocode(city_name)` and `search_cities(query)` using Nominatim API. Add User-Agent "zeClock/1.0", 10s timeout, in-memory cache dict, input validation (reject empty/whitespace, min 3 chars for search). Return up to 5 results for search_cities.
- [x] 4. Add REST API endpoints (`rest_remote.py`). Add `GET /api/plugins/config-schema` — returns all plugin schemas aggregated. Add `GET /api/geocode/search?q=<query>` — calls `search_cities()`, returns 400 if query < 3 chars.
- [x] 5. Update Weather plugin (`plugins/weather_plugin.py`). Add `config_schema` declaring "city" field (type: city, required). In `initialize()`: if no lat/long and no city → raise `PluginNotConfiguredError`. If city but no coords → call `geocoder.geocode()`. If geocode fails → raise `PluginNotConfiguredError`. Cache result in-memory for session. If explicit lat/long provided → skip geocode.
- [x] 6. Update Stock plugin (`plugins/stock_plugin.py`). Add `config_schema` declaring "symbols" field (type: text, required). In `initialize()`: if symbols is missing/null/empty/whitespace-only → raise `PluginNotConfiguredError`.
- [x] 7. Update Gif plugin (`plugins/gif_plugin.py`). Add `config_schema` declaring "gif_dir" field (type: text, required). In `initialize()`: if gif_dir doesn't exist or contains zero .gif files → raise `PluginNotConfiguredError`.
- [x] 8. Web UI auto-generated plugin configuration forms (`app.js`, `index.html`, `style.css`). On Settings tab load: fetch `GET /api/plugins/config-schema`. For each plugin with schema, render a card with form inputs grouped by plugin name. Map field_type to HTML: text→input[text], number→input[number], list→input[text] with hint, city→autocomplete input. On save: merge values into plugins.yaml settings via `POST /api/config/plugins`.
- [x] 9. Web UI city autocomplete (`app.js`, `style.css`). For "city" type fields: debounced input handler (300ms, triggers after 3+ chars). Call `GET /api/geocode/search?q=<value>`. Display dropdown with up to 5 results as "City, Country". On selection: populate input with display name, store hidden lat/long. Show "No results found" when empty. Style dropdown (dark theme, positioned below input, z-index above content).

## Task Dependency Graph

```json
{
  "waves": [
    {"name": "Foundation", "tasks": ["1", "3"]},
    {"name": "Core Logic", "tasks": ["2", "4", "5", "6", "7"]},
    {"name": "Web UI Forms", "tasks": ["8"]},
    {"name": "City Autocomplete", "tasks": ["9"]}
  ]
}
```

## Notes

- No new Python packages required — geocoding uses stdlib `urllib.request`
- Nominatim API is free, no API key needed (just requires User-Agent header)
- Tasks 5, 6, 7 can be done in parallel after task 1
- Tasks 8 and 9 can be done in parallel after task 4
- No backward compatibility constraint — all plugins will need config_schema (even if empty list)
