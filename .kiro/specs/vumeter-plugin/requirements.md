# Requirements Document

## Introduction

The VU Meter plugin renders an animated audio VU meter visualization on the DMD display during attract mode. It simulates classic analog VU meter needle movement or LED-bar-style level meters with smooth, randomized amplitude changes to create an eye-catching audio-themed animation. The plugin does not capture real audio — it generates synthetic amplitude data to drive the visual display.

## Glossary

- **Plugin_System**: The zeClock plugin manager responsible for discovering, loading, initializing, scheduling, and deactivating plugins.
- **VU_Meter_Plugin**: The plugin that renders an animated VU meter visualization on the DMD display.
- **Bar**: A single vertical column in the VU meter display representing a frequency band's amplitude level.
- **Peak_Indicator**: A single-pixel-high marker that floats above a bar's current level, representing the recent peak amplitude, and decays downward over time.
- **Amplitude**: A normalized value in the range [0.0, 1.0] representing the current level of a frequency band.
- **Decay_Rate**: The speed at which a peak indicator falls back toward the current amplitude level, measured in normalized units per frame.
- **Frame**: A single rendered image (PIL Image in RGB mode) at the display resolution, produced by render_frame().
- **PluginHelpers**: The rendering utility object injected via config["_helpers"] that provides frame creation and compositing methods.

## Requirements

### Requirement 1: Plugin Identity

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to declare a valid identity, so that it can be discovered, registered, and scheduled alongside other plugins.

#### Acceptance Criteria

1. THE VU_Meter_Plugin SHALL return "vumeter" as its name property, matching the system validation pattern ^[a-z0-9_-]{1,64}$.
2. THE VU_Meter_Plugin SHALL return a description string of length between 1 and 256 characters inclusive.
3. THE VU_Meter_Plugin SHALL return an integer frame_delay_ms value of 50, representing a 20 FPS animation rate within the valid system range of [20, 5000] milliseconds.
4. THE VU_Meter_Plugin SHALL return identical values for name, description, and frame_delay_ms on every access throughout the plugin lifecycle.

### Requirement 2: Initialization

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to initialize its rendering state from configuration, so that the plugin is ready to produce frames without delay.

#### Acceptance Criteria

1. WHEN initialize is called, THE VU_Meter_Plugin SHALL store the PluginHelpers instance from config["_helpers"] for use in subsequent render_frame calls.
2. WHEN initialize is called, THE VU_Meter_Plugin SHALL read the "num_bars" setting from config with a default of 16 and store it as an integer.
3. WHEN initialize is called, THE VU_Meter_Plugin SHALL read the "duration_seconds" setting from config with a default of 10 and store it as an integer.
4. WHEN initialize is called, THE VU_Meter_Plugin SHALL read the "color" setting from config with a default of "green" and store it as a string for later resolution via PluginHelpers.resolve_color.
5. WHEN initialize is called, THE VU_Meter_Plugin SHALL read the "peak_color" setting from config with a default of "red" and store it as a string for later resolution via PluginHelpers.resolve_color.
6. WHEN initialize is called, THE VU_Meter_Plugin SHALL read the "decay_rate" setting from config with a default of 0.05 and store it as a float.
7. WHEN initialize is called, THE VU_Meter_Plugin SHALL initialize an array of num_bars bar amplitudes, each set to 0.0, and an array of num_bars peak indicator positions, each set to 0.0.
8. WHEN initialize is called, THE VU_Meter_Plugin SHALL reset the rendered frame counter to 0 so that duration tracking begins from zero.
9. WHEN initialize is called, THE VU_Meter_Plugin SHALL complete without raising an exception and return within 10 seconds.
10. IF initialize is called and the config dict does not contain a "_helpers" key, THEN THE VU_Meter_Plugin SHALL raise an exception, causing the Plugin_System to mark it as failed.

### Requirement 3: Frame Rendering

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to render valid frames showing animated VU meter bars, so that the DMD displays a visually appealing audio meter visualization.

#### Acceptance Criteria

1. WHEN render_frame is called, THE VU_Meter_Plugin SHALL return a PIL Image in RGB mode with dimensions equal to the provided width and height parameters and a black (0, 0, 0) background.
2. WHEN render_frame is called, THE VU_Meter_Plugin SHALL render each bar as a filled vertical column whose pixel height equals the bar's current amplitude multiplied by the display height, rounded down to the nearest integer (amplitude 0.0 produces 0 pixels, amplitude 1.0 produces height pixels).
3. WHEN render_frame is called, THE VU_Meter_Plugin SHALL space bars evenly across the horizontal width of the display with a 1-pixel gap between adjacent bars, where each bar's pixel width equals (width minus (num_bars minus 1)) divided by num_bars using integer division.
4. WHEN render_frame is called, THE VU_Meter_Plugin SHALL draw bars growing upward from the bottom edge of the display (row index height-1 upward).
5. WHEN render_frame is called, THE VU_Meter_Plugin SHALL render each bar using the configured bar color resolved via PluginHelpers.resolve_color.
6. WHEN render_frame is called, THE VU_Meter_Plugin SHALL complete within 2 seconds.
7. IF the computed bar pixel width is less than 1, THEN THE VU_Meter_Plugin SHALL render bars with a minimum width of 1 pixel, drawing only as many bars as can fit within the display width.

### Requirement 4: Peak Indicators

**User Story:** As a viewer, I want to see peak indicators above each bar, so that I can perceive the recent maximum level of each frequency band.

#### Acceptance Criteria

1. WHEN a bar's amplitude exceeds its current peak indicator position, THE VU_Meter_Plugin SHALL update the peak indicator position to match the new amplitude.
2. WHILE a peak indicator position is above its bar's current amplitude, THE VU_Meter_Plugin SHALL decrease the peak indicator position by the configured decay_rate per frame, clamping the result to a minimum of 0.0.
3. WHEN render_frame is called, THE VU_Meter_Plugin SHALL render each peak indicator as a single-pixel-high horizontal line spanning the full width of its corresponding bar, positioned at the vertical y-coordinate derived from the peak indicator's normalized position mapped to the display height (0.0 at the bottom, 1.0 at the top), using the configured peak color resolved via PluginHelpers.resolve_color.
4. IF a peak indicator position equals 0.0, THEN THE VU_Meter_Plugin SHALL still render the peak indicator at the bottom row of the bar's column area.

### Requirement 5: Amplitude Animation

**User Story:** As a viewer, I want the bars to animate smoothly with varied movement, so that the visualization appears dynamic and resembles a real audio signal.

#### Acceptance Criteria

1. WHEN render_frame is called, THE VU_Meter_Plugin SHALL update each bar's amplitude by adding a uniformly distributed random delta within the range [-0.15, +0.15], where each bar receives its own independently generated delta value.
2. THE VU_Meter_Plugin SHALL clamp all bar amplitudes to the range [0.0, 1.0] after applying the random delta.
3. WHEN at least 3 frames have been rendered, THE VU_Meter_Plugin SHALL produce bar amplitudes such that not all bars hold the same amplitude value, confirming per-bar independent variation.
4. THE VU_Meter_Plugin SHALL generate a separate random delta per bar per frame, ensuring no bar's delta is derived from or shared with another bar's delta.

### Requirement 6: Completion Signaling

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to signal completion after its configured duration, so that the display transitions back to clock mode.

#### Acceptance Criteria

1. WHEN render_frame is called and the internal frame counter is greater than or equal to the maximum frame count (computed as integer truncation of duration_seconds multiplied by 1000 divided by frame_delay_ms), THE VU_Meter_Plugin SHALL return None.
2. WHILE the internal frame counter is less than the maximum frame count, THE VU_Meter_Plugin SHALL return a PIL Image in RGB mode with dimensions matching the provided width and height parameters from render_frame on every call.
3. WHEN render_frame returns a valid frame, THE VU_Meter_Plugin SHALL increment the internal frame counter by 1.
4. IF render_frame is called after the VU_Meter_Plugin has already returned None, THEN THE VU_Meter_Plugin SHALL continue to return None.

### Requirement 7: Cleanup

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to reset its internal state during cleanup, so that the plugin is ready for a fresh activation in the next cycle.

#### Acceptance Criteria

1. WHEN cleanup is called, THE VU_Meter_Plugin SHALL reset all bar amplitudes to 0.0.
2. WHEN cleanup is called, THE VU_Meter_Plugin SHALL reset all peak indicator positions to 0.0.
3. WHEN cleanup is called, THE VU_Meter_Plugin SHALL reset the rendered frame counter to 0.
4. IF cleanup encounters an unexpected internal error, THEN THE VU_Meter_Plugin SHALL complete without raising an exception to the caller.
5. WHEN cleanup has completed and initialize is subsequently called with a valid config, THE VU_Meter_Plugin SHALL re-initialize successfully and produce frames as if activated for the first time.
6. IF cleanup is called multiple times consecutively without an intervening initialize call, THEN THE VU_Meter_Plugin SHALL complete without raising an exception on each call.

### Requirement 8: Configuration Validation

**User Story:** As the Plugin_System, I want the VU_Meter_Plugin to handle invalid configuration values gracefully, so that the plugin operates with safe defaults instead of crashing.

#### Acceptance Criteria

1. WHEN initialize is called and num_bars is less than 1 or greater than 64, THEN THE VU_Meter_Plugin SHALL clamp num_bars to the range [1, 64].
2. WHEN initialize is called and duration_seconds is less than 1 or greater than 30, THEN THE VU_Meter_Plugin SHALL clamp duration_seconds to the range [1, 30].
3. WHEN initialize is called and decay_rate is less than 0.01 or greater than 0.5, THEN THE VU_Meter_Plugin SHALL clamp decay_rate to the range [0.01, 0.5].
4. IF num_bars, duration_seconds, or decay_rate is not a numeric type, THEN THE VU_Meter_Plugin SHALL use the default value for that parameter (16 for num_bars, 10 for duration_seconds, 0.05 for decay_rate).
5. IF color cannot be resolved by PluginHelpers.resolve_color, THEN THE VU_Meter_Plugin SHALL fall back to the color green by passing "green" as the default parameter to resolve_color.
6. IF peak_color cannot be resolved by PluginHelpers.resolve_color, THEN THE VU_Meter_Plugin SHALL fall back to the color red by passing "red" as the default parameter to resolve_color.
7. WHEN initialize is called with any combination of invalid configuration values, THE VU_Meter_Plugin SHALL complete initialization without raising an exception.

### Requirement 9: Display Dimension Adaptability

**User Story:** As a user with different DMD hardware, I want the VU_Meter_Plugin to adapt its rendering to any supported display resolution, so that it looks correct on both SD (128x32) and HD (256x64) panels.

#### Acceptance Criteria

1. WHEN render_frame is called with width 128 and height 32, THE VU_Meter_Plugin SHALL render all bars and peak indicators within the bounds of 128 pixels wide and 32 pixels tall with no pixels drawn outside the image area.
2. WHEN render_frame is called with width 256 and height 64, THE VU_Meter_Plugin SHALL render all bars and peak indicators within the bounds of 256 pixels wide and 64 pixels tall with no pixels drawn outside the image area.
3. THE VU_Meter_Plugin SHALL calculate bar width dynamically as (width - (num_bars - 1)) divided by num_bars, using integer division.
4. THE VU_Meter_Plugin SHALL calculate bar pixel height as the bar's amplitude multiplied by the provided height parameter, using integer conversion.
5. THE VU_Meter_Plugin SHALL render bars left-aligned, starting at horizontal pixel 0, with each subsequent bar positioned at (bar_index * (bar_width + 1)) pixels from the left edge.
6. THE VU_Meter_Plugin SHALL render each peak indicator with a width equal to the calculated bar width for that resolution.
