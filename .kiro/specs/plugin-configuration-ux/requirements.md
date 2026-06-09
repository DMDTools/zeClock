# Requirements Document

## Introduction

This feature improves the configuration experience for zeClock plugins. When a plugin is activated but lacks required settings, it displays a helpful "configure me" message on the physical DMD display instead of failing silently. Additionally, the weather plugin gains human-friendly location configuration by accepting a city name and automatically geocoding it to coordinates using the OpenStreetMap Nominatim API.

## Glossary

- **DMD**: Dot Matrix Display — the physical LED display (128x32 or 256x64 pixels) connected to the Raspberry Pi
- **Plugin_System**: The zeClock plugin framework responsible for loading, initializing, and rendering plugins
- **Weather_Plugin**: The built-in plugin that fetches and displays weather data from Open-Meteo API
- **Stock_Plugin**: The built-in plugin that fetches and displays stock prices from Yahoo Finance
- **Gif_Plugin**: The built-in plugin that plays animated GIFs from a configurable directory
- **Configuration_Message**: A text frame rendered on the DMD informing the user that a plugin requires configuration
- **Geocoder**: A service that converts a city name into latitude/longitude coordinates
- **Nominatim_API**: OpenStreetMap's free geocoding service used to resolve city names to coordinates
- **Web_UI**: The configuration web interface running at zeclock.local:8080
- **plugins.yaml**: The YAML configuration file storing plugin-specific settings
- **zeclock.ini**: The INI configuration file storing global settings including location

## Requirements

### Requirement 1: Configuration Detection

**User Story:** As a zeClock user, I want the system to detect when a plugin is missing required configuration, so that I am informed rather than seeing a silent failure.

#### Acceptance Criteria

1. WHEN a plugin raises a PluginNotConfiguredError during initialization, THE Plugin_System SHALL mark that plugin as "unconfigured" and retain it in the active rotation cycle without marking it as "failed" in the Plugin_Registry
2. THE Plugin_System SHALL provide a method for each plugin to declare its required configuration fields via a config_schema property that returns a list of ConfigField descriptors
3. IF a plugin raises any exception other than PluginNotConfiguredError during initialization, THEN THE Plugin_System SHALL mark that plugin as failed and exclude it from the rotation cycle

### Requirement 2: Plugin Configuration Schema Declaration

**User Story:** As a plugin developer, I want to declare what configuration my plugin needs (field names, types, descriptions), so that the web UI can automatically generate a configuration form for users.

#### Acceptance Criteria

1. EACH plugin SHALL be able to declare a configuration schema via a config_schema property that returns a list of ConfigField dataclass instances
2. THE ConfigField declaration SHALL include for each field: name (string key in plugins.yaml), field_type (one of: "text", "number", "city", "list"), label (human-readable string, max 50 characters), required (boolean), description (string, max 200 characters), and default value (or None)
3. THE Plugin_System SHALL expose the aggregated configuration schemas of all registered plugins via GET /api/plugins/config-schema, returning a JSON object with a "plugins" array where each entry contains "name", "description", and "schema" fields
4. THE Web_UI SHALL automatically render configuration form fields for each plugin based on its declared schema, using appropriate HTML input types for each field_type ("text" → text input, "number" → number input, "city" → autocomplete text input, "list" → text input with comma-separated values)
5. THE Web_UI SHALL group plugin configuration fields under the plugin name as a heading in the Settings tab
6. WHEN a user submits configuration values through the auto-generated form, THE Web_UI SHALL save them to plugins.yaml via POST /api/config/plugins, and the backend SHALL persist the file to disk before returning a success response
7. THE schema declaration SHALL support a "city" field_type that the Web_UI renders as an autocomplete text input with a dropdown, and the backend resolves to latitude/longitude via the Geocoder upon selection
8. FOR "city" type fields, THE Web_UI SHALL trigger an autocomplete search request to GET /api/geocode/search after the user has typed 3 or more characters, debounced by 300 milliseconds after the last keystroke
9. WHEN the geocode search returns results, THE Web_UI SHALL present a dropdown list of up to 5 matching city results showing "{city name}, {country}" for the user to pick from
10. WHEN the user selects a city from the autocomplete dropdown, THE Web_UI SHALL store the city display name, latitude (float), and longitude (float) in the plugin's configuration
11. IF the geocode search returns zero results, THEN THE Web_UI SHALL display a "No results found" message in the dropdown area without preventing further typing

### Requirement 3: DMD Configuration Message Display (Shared Capability)

**User Story:** As a zeClock user, I want to see a helpful message on the DMD display when any plugin needs configuration, so that I know what to do without checking logs.

#### Acceptance Criteria

1. THE Plugin_System SHALL provide a shared "configuration message" rendering capability that any plugin can trigger by raising PluginNotConfiguredError during initialization
2. WHEN an unconfigured plugin is selected for display during rotation, THE Plugin_System SHALL render a Configuration_Message on the DMD using the MENU bitmap font and the same color scheme as the existing text overlay system
3. THE Configuration_Message SHALL display the format: "{Plugin Name}: Configure me" where Plugin Name is the plugin's display name truncated to 12 characters if longer
4. THE Configuration_Message SHALL be rendered horizontally and vertically centered on the DMD, fitting within both SD (128x32) and HD (256x64) display dimensions without clipping
5. THE Configuration_Message SHALL be displayed for the plugin's normal rotation duration as determined by the plugin scheduling system
6. WHEN a previously unconfigured plugin is re-initialized with valid settings (after configuration via the Web_UI), THE Plugin_System SHALL stop displaying the Configuration_Message and render normal plugin content on the next rotation cycle
7. THE shared capability SHALL NOT require plugins to implement their own "configure me" rendering logic — the Plugin_System framework handles rendering when it detects the unconfigured flag

### Requirement 4: Weather Plugin City Name Configuration

**User Story:** As a zeClock user, I want to configure the weather plugin by typing a city name instead of latitude/longitude coordinates, so that setup is quick and intuitive.

#### Acceptance Criteria

1. WHEN a city_name is provided without latitude and longitude in the weather plugin configuration, THE Weather_Plugin SHALL resolve the city name to coordinates using the Geocoder service during initialization
2. WHEN the Geocoder returns multiple results for a city name, THE Weather_Plugin SHALL use the first result (highest relevance as ranked by the Nominatim API)
3. WHEN the Geocoder returns a valid result, THE Weather_Plugin SHALL store the resolved latitude and longitude in memory for use in subsequent weather data fetches during the current session
4. IF the Geocoder returns an error (network failure, timeout, or no results), THEN THE Weather_Plugin SHALL raise PluginNotConfiguredError, causing the Plugin_System to display the Configuration_Message
5. THE Geocoder SHALL include a User-Agent header in the format "zeClock/1.0" when calling the Nominatim_API, as required by the Nominatim usage policy
6. THE Weather_Plugin SHALL cache the geocoding result in memory so that the Nominatim_API is called at most once per application startup, regardless of how many times the plugin is activated during the session
7. WHEN both a city_name and valid latitude/longitude (both non-null numeric values) are provided in configuration, THE Weather_Plugin SHALL use the explicit coordinates and skip geocoding entirely

### Requirement 5: Stock Plugin Configuration Guidance

**User Story:** As a zeClock user, I want to see a helpful message on the DMD when the stock plugin has no symbols configured, so that I know how to add stock tickers.

#### Acceptance Criteria

1. WHEN the Stock_Plugin is initialized with a symbols configuration that is missing, null, an empty list, or a list containing only empty/whitespace strings, THE Stock_Plugin SHALL raise PluginNotConfiguredError
2. WHEN the Stock_Plugin has raised PluginNotConfiguredError, THE Plugin_System SHALL display a Configuration_Message with the text "Stock: Configure me" using the shared rendering capability

### Requirement 6: Gif Plugin Configuration Guidance

**User Story:** As a zeClock user, I want to see a helpful message on the DMD when the gif plugin has no GIF files available in its directory, so that I know what to do.

#### Acceptance Criteria

1. WHEN the Gif_Plugin is initialized and the configured gif directory does not exist or contains zero .gif files, THE Gif_Plugin SHALL raise PluginNotConfiguredError
2. WHEN the Gif_Plugin has raised PluginNotConfiguredError, THE Plugin_System SHALL display a Configuration_Message with the text "Gif: Configure me" using the shared rendering capability
3. THE Gif_Plugin SHALL declare a config_schema with a "gif_dir" field (type: text) describing the directory path where GIF files should be placed

### Requirement 7: Geocoding Service

**User Story:** As a developer, I want a reusable geocoding service, so that any plugin needing location data can resolve city names to coordinates.

#### Acceptance Criteria

1. THE Geocoder SHALL expose a geocode(city_name) function that accepts a non-empty string (minimum 1 character after trimming whitespace) and returns a result containing latitude and longitude as floating-point values, plus a display_name and country string
2. THE Geocoder SHALL expose a search_cities(query) function that accepts a string of 3 or more characters and returns a list of up to 5 matching results, each containing latitude, longitude, display_name, and country
3. THE Geocoder SHALL call the Nominatim_API with the search query and format=json parameters, and include a User-Agent header identifying the application
4. WHEN the Nominatim_API returns an empty result list, THE Geocoder SHALL return an error indicating the city was not found
5. IF a network error or HTTP non-200 response occurs during the geocoding request, THEN THE Geocoder SHALL return an error indicating the service is unavailable, without raising an unhandled exception
6. THE Geocoder SHALL enforce a maximum timeout of 10 seconds on each HTTP request to the Nominatim_API
7. IF the city_name argument to geocode() is empty or contains only whitespace after trimming, THEN THE Geocoder SHALL return an error indicating invalid input without making a network request
