# Implementation Plan: VU Meter Plugin

## Overview

Implement the `vumeter` attract-mode plugin for zeClock that renders an animated audio VU meter visualization on DMD displays. The implementation uses Python with PIL for rendering, subclasses `ClockPlugin`, and includes property-based tests via Hypothesis and unit tests via pytest.

## Tasks

- [x] 1. Create plugin file with class skeleton and identity properties
  - [x] 1.1 Create `zeclock/plugins/vumeter_plugin.py` with `VUMeterPlugin` class
    - Subclass `ClockPlugin` from `zeclock.plugins.base`
    - Implement `name` property returning `"vumeter"`
    - Implement `description` property returning a descriptive string (1-256 chars)
    - Implement `frame_delay_ms` property returning `50`
    - Add all instance variable declarations (`_helpers`, `_num_bars`, `_duration_seconds`, `_bar_color`, `_peak_color`, `_decay_rate`, `_amplitudes`, `_peaks`, `_frame_counter`, `_max_frames`, `_completed`)
    - Add necessary imports: `random`, `typing`, `PIL.Image`, `PIL.ImageDraw`, `ClockPlugin`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Implement initialization and configuration validation
  - [x] 2.1 Implement `initialize(self, config: dict)` method
    - Extract `_helpers` from `config["_helpers"]`; raise if missing
    - Read `num_bars`, `duration_seconds`, `color`, `peak_color`, `decay_rate` from config with defaults
    - Implement `_clamp_config` helper: check type, clamp to valid range, fall back to default for non-numeric
    - Apply clamping: `num_bars` to [1, 64], `duration_seconds` to [1, 30], `decay_rate` to [0.01, 0.5]
    - Initialize `_amplitudes` and `_peaks` as lists of `num_bars` zeros
    - Set `_frame_counter = 0`, compute `_max_frames = int(duration_seconds * 1000 / frame_delay_ms)`
    - Set `_completed = False`
    - Resolve `_bar_color` and `_peak_color` via `self._helpers.resolve_color(color, "green")` and `self._helpers.resolve_color(peak_color, "red")`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 2.2 Write property test for configuration clamping (Property 1)
    - **Property 1: Configuration clamping preserves valid range**
    - Use Hypothesis to generate random numeric and non-numeric values for `num_bars`, `duration_seconds`, `decay_rate`
    - Verify clamped values are always within valid ranges or equal defaults for non-numeric inputs
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - [ ]* 2.3 Write property test for array initialization sizing (Property 2)
    - **Property 2: Initialization produces correctly sized arrays**
    - Use Hypothesis to generate `num_bars` in [1, 64]
    - Verify amplitudes and peaks arrays have correct length and all elements are 0.0
    - **Validates: Requirements 2.7**

  - [ ]* 2.4 Write property test for initialization robustness (Property 15)
    - **Property 15: Initialization robustness under invalid config**
    - Use Hypothesis to generate config dicts with valid `_helpers` but arbitrary invalid values for other keys
    - Verify `initialize()` completes without raising an exception
    - **Validates: Requirements 8.7**

- [x] 3. Implement frame rendering with bar layout and drawing
  - [x] 3.1 Implement `render_frame(self, width: int, height: int)` method
    - Check completion: if `_completed` or `_frame_counter >= _max_frames`, set `_completed = True`, return `None`
    - Call amplitude update logic (random deltas per bar, clamp to [0.0, 1.0])
    - Call peak update logic (track up, decay down)
    - Create frame via `self._helpers.create_frame()` (or `Image.new("RGB", (width, height), (0, 0, 0))`)
    - Calculate `bar_width = (width - (num_bars - 1)) // num_bars`, clamp to minimum 1
    - Calculate visible bars: limit to what fits within display width if `bar_width == 1`
    - For each bar: compute `bar_x = i * (bar_width + 1)`, `bar_height = int(amplitude * height)`
    - Draw filled rectangle from `(bar_x, height - bar_height)` to `(bar_x + bar_width - 1, height - 1)` using `_bar_color`
    - Draw peak indicator: 1-pixel-high line at `y = height - 1 - int(peak * (height - 1))` spanning bar width, using `_peak_color`
    - Increment `_frame_counter`
    - Return the frame image
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 3.2 Write property test for frame output validity (Property 3)
    - **Property 3: Frame output validity**
    - Use Hypothesis to generate random `width` in [16, 256] and `height` in [8, 64]
    - Verify returned Image is RGB mode with exact dimensions `(width, height)`
    - **Validates: Requirements 3.1, 6.2, 9.1, 9.2**

  - [ ]* 3.3 Write property test for bar height rendering (Property 4)
    - **Property 4: Bar height corresponds to amplitude**
    - Use Hypothesis to generate random amplitudes in [0.0, 1.0] and heights in [8, 64]
    - Manually set amplitude, render, and verify filled pixel height equals `int(a * h)`
    - **Validates: Requirements 3.2, 3.4, 9.4**

  - [ ]* 3.4 Write property test for bar layout positioning (Property 5)
    - **Property 5: Bar layout positioning**
    - Use Hypothesis to generate random `width` in [16, 256] and `num_bars` in [1, 64]
    - Verify bar width formula and bar_x positioning
    - **Validates: Requirements 3.3, 9.3, 9.5**

- [x] 4. Checkpoint - Verify core rendering
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement peak indicator logic and amplitude animation
  - [x] 5.1 Write unit tests for peak indicator and amplitude behavior
    - Test peak tracks amplitude upward (amplitude exceeds peak → peak = amplitude)
    - Test peak decays when above amplitude (peak decreases by decay_rate per frame)
    - Test peak indicator renders at correct y-coordinate
    - Test peak indicator at position 0.0 renders at bottom row
    - Test amplitude changes are bounded within [-0.15, +0.15] per frame
    - Test amplitudes are always clamped to [0.0, 1.0]
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [ ]* 5.2 Write property test for peak tracks amplitude upward (Property 6)
    - **Property 6: Peak tracks amplitude upward**
    - Use Hypothesis to generate scenarios where new amplitude exceeds current peak
    - Verify peak position equals new amplitude after update
    - **Validates: Requirements 4.1**

  - [ ]* 5.3 Write property test for peak decay (Property 7)
    - **Property 7: Peak decays toward amplitude**
    - Use Hypothesis to generate peak > amplitude scenarios with random decay rates in [0.01, 0.5]
    - Verify peak equals `max(0.0, old_peak - decay_rate)` after one frame
    - **Validates: Requirements 4.2**

  - [ ]* 5.4 Write property test for peak indicator rendering position (Property 8)
    - **Property 8: Peak indicator rendering position**
    - Use Hypothesis to generate peak positions in [0.0, 1.0] and heights in [8, 64]
    - Verify peak indicator y-coordinate equals `height - 1 - int(peak * (height - 1))`
    - **Validates: Requirements 4.3, 9.6**

  - [ ]* 5.5 Write property test for amplitude bounded changes (Property 9)
    - **Property 9: Amplitude bounded changes and clamping**
    - Use Hypothesis to run multiple frames and verify delta within [-0.15, +0.15] and result in [0.0, 1.0]
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 5.6 Write property test for per-bar amplitude independence (Property 10)
    - **Property 10: Per-bar amplitude independence**
    - Use Hypothesis to generate `num_bars >= 2`, render 3+ frames
    - Verify not all bar amplitudes are identical
    - **Validates: Requirements 5.3, 5.4**

- [x] 6. Implement completion signaling and cleanup
  - [x] 6.1 Implement `cleanup(self)` method
    - Reset `_amplitudes` to list of zeros (length `_num_bars`)
    - Reset `_peaks` to list of zeros (length `_num_bars`)
    - Reset `_frame_counter` to 0
    - Set `_completed` to False
    - Wrap all reset operations in try/except to suppress exceptions
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 6.2 Write property test for completion timing (Property 11)
    - **Property 11: Completion at max frame count**
    - Use Hypothesis to generate `duration_seconds` in [1, 30]
    - Verify plugin returns valid Image for exactly `int(duration_seconds * 1000 / 50)` frames, then None
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 6.3 Write property test for completion idempotence (Property 12)
    - **Property 12: Completion is permanent (idempotence)**
    - After plugin returns None, call render_frame N more times, verify all return None
    - **Validates: Requirements 6.4**

  - [ ]* 6.4 Write property test for cleanup restores state (Property 13)
    - **Property 13: Cleanup restores initial state**
    - Run plugin for several frames, call cleanup(), call initialize() with valid config
    - Verify all amplitudes are 0.0, all peaks are 0.0, frame counter is 0
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.5**

  - [ ]* 6.5 Write property test for cleanup idempotence (Property 14)
    - **Property 14: Cleanup idempotence**
    - Call cleanup() multiple times consecutively, verify no exception
    - **Validates: Requirements 7.6**

- [x] 7. Checkpoint - Verify completion and cleanup
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integration: plugin registration and end-to-end verification
  - [x] 8.1 Register plugin for discovery
    - Add import/registration in `zeclock/plugins/__init__.py` so `VUMeterPlugin` is discoverable by the plugin manager
    - Verify the plugin loads correctly alongside other plugins
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 8.2 Write integration unit tests
    - Test full lifecycle: initialize → render N frames → returns None → cleanup → re-initialize works
    - Test with SD resolution (128x32) and HD resolution (256x64)
    - Test plugin identity properties are stable across accesses
    - Test missing `_helpers` raises exception
    - Test color resolution fallback with invalid color names
    - Test bar width minimum of 1px when `num_bars > width`
    - _Requirements: 1.4, 2.10, 3.7, 8.5, 8.6, 9.1, 9.2_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The plugin file goes at `zeclock/plugins/vumeter_plugin.py`
- Tests go in `tests/test_vumeter_plugin.py` (unit + integration) and `tests/test_vumeter_properties.py` (property-based)
- Use `@settings(max_examples=100)` for Hypothesis property tests
- Mock `PluginHelpers` using patterns from existing tests (see `tests/conftest.py`)
- All async methods (`initialize`, `render_frame`, `cleanup`) require `pytest-asyncio`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5"] },
    { "id": 6, "tasks": ["8.1"] },
    { "id": 7, "tasks": ["8.2"] }
  ]
}
```
