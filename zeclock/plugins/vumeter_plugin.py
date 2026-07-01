"""VUMeterPlugin - Animated VU meter visualization on the DMD.

Renders an animated audio VU meter with vertical bars and floating peak
indicators. Uses synthetic amplitude data (random deltas) to simulate
frequency-band level meters. Does not capture real audio.
"""

import random
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from .base import ClockPlugin


class VUMeterPlugin(ClockPlugin):
    """Animated VU meter visualization plugin.

    Simulates classic LED-bar-style level meters with smooth, randomized
    amplitude changes and floating peak indicators that decay over time.
    """

    # Instance state (set during initialize)
    _helpers: object
    _num_bars: int
    _duration_seconds: int
    _bar_color: Tuple[int, int, int]
    _peak_color: Tuple[int, int, int]
    _decay_rate: float
    _amplitudes: List[float]
    _peaks: List[float]
    _frame_counter: int
    _max_frames: int
    _completed: bool

    @property
    def name(self) -> str:
        """Unique identifier: 'vumeter'."""
        return "vumeter"

    @property
    def description(self) -> str:
        """Human-readable description of the plugin."""
        return "Animated VU meter audio visualization"

    @property
    def frame_delay_ms(self) -> int:
        """Frame delay of 50ms (20 FPS)."""
        return 50

    @staticmethod
    def _clamp_config(value, default, min_val, max_val, numeric_type):
        """Check type, clamp to valid range, fall back to default for non-numeric.

        Args:
            value: The raw config value to validate.
            default: Default value to use if value is not of the expected type.
            min_val: Minimum allowed value (inclusive).
            max_val: Maximum allowed value (inclusive).
            numeric_type: Expected numeric type (int or float). For int,
                also accepts float values by converting them.

        Returns:
            The clamped value within [min_val, max_val], or default if
            value is not a valid numeric type.
        """
        # Accept both int and float as "numeric" for numeric_type checks
        if numeric_type is int:
            if not isinstance(value, (int, float)):
                return default
            # Reject booleans (bool is subclass of int in Python)
            if isinstance(value, bool):
                return default
            value = int(value)
        elif numeric_type is float:
            if not isinstance(value, (int, float)):
                return default
            if isinstance(value, bool):
                return default
            value = float(value)
        else:
            if not isinstance(value, numeric_type):
                return default

        return max(min_val, min(max_val, value))

    async def initialize(self, config: dict) -> None:
        """Prepare the plugin for rendering.

        Args:
            config: Plugin-specific settings including '_helpers'.

        Raises:
            KeyError: If '_helpers' is not present in config.
        """
        # Extract helpers - raise if missing (KeyError is acceptable)
        self._helpers = config["_helpers"]

        # Read config values with defaults
        raw_num_bars = config.get("num_bars", 16)
        raw_duration_seconds = config.get("duration_seconds", 10)
        raw_decay_rate = config.get("decay_rate", 0.05)
        color = config.get("color", "green")
        peak_color = config.get("peak_color", "red")

        # Apply clamping with type checking and range validation
        self._num_bars = self._clamp_config(raw_num_bars, 16, 1, 64, int)
        self._duration_seconds = self._clamp_config(
            raw_duration_seconds, 10, 1, 30, int
        )
        self._decay_rate = self._clamp_config(raw_decay_rate, 0.05, 0.01, 0.5, float)

        # Initialize amplitude and peak arrays
        self._amplitudes = [0.0] * self._num_bars
        self._peaks = [0.0] * self._num_bars

        # Initialize frame counter and compute max frames
        self._frame_counter = 0
        self._max_frames = int(self._duration_seconds * 1000 / self.frame_delay_ms)

        # Set completion flag
        self._completed = False

        # Resolve colors via helpers
        if not isinstance(color, str):
            color = "green"
        if not isinstance(peak_color, str):
            peak_color = "red"
        self._bar_color = self._helpers.resolve_color(color, "green")
        self._peak_color = self._helpers.resolve_color(peak_color, "red")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next VU meter frame.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        # Check completion: if already completed or frame counter has reached max
        if self._completed or self._frame_counter >= self._max_frames:
            self._completed = True
            return None

        # Update amplitudes: random delta per bar, clamped to [0.0, 1.0]
        for i in range(self._num_bars):
            delta = random.uniform(-0.15, 0.15)
            self._amplitudes[i] = max(0.0, min(1.0, self._amplitudes[i] + delta))

        # Update peaks: track up, decay down
        for i in range(self._num_bars):
            if self._amplitudes[i] > self._peaks[i]:
                self._peaks[i] = self._amplitudes[i]
            else:
                self._peaks[i] = max(0.0, self._peaks[i] - self._decay_rate)

        # Create a blank black frame
        frame = Image.new("RGB", (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Calculate bar width: (width - (num_bars - 1)) // num_bars, minimum 1
        bar_width = (width - (self._num_bars - 1)) // self._num_bars
        if bar_width < 1:
            bar_width = 1

        # Calculate visible bars: limit to what fits if bar_width == 1
        if bar_width == 1:
            # Each bar takes bar_width + 1 pixels (bar + gap), except the last
            # which takes just bar_width. So visible_bars = (width + 1) // 2
            visible_bars = min(self._num_bars, (width + 1) // (bar_width + 1))
            if visible_bars < 1:
                visible_bars = 1
        else:
            visible_bars = self._num_bars

        # Draw each bar and its peak indicator
        for i in range(visible_bars):
            bar_x = i * (bar_width + 1)

            # Ensure bar fits within width
            if bar_x + bar_width > width:
                break

            # Draw bar: filled rectangle from bottom up
            bar_height = int(self._amplitudes[i] * height)
            if bar_height > 0:
                # Rectangle from (bar_x, height - bar_height) to
                # (bar_x + bar_width - 1, height - 1)
                draw.rectangle(
                    [bar_x, height - bar_height, bar_x + bar_width - 1, height - 1],
                    fill=self._bar_color,
                )

            # Draw peak indicator: 1-pixel-high line at peak position
            peak_y = height - 1 - int(self._peaks[i] * (height - 1))
            draw.rectangle(
                [bar_x, peak_y, bar_x + bar_width - 1, peak_y],
                fill=self._peak_color,
            )

        # Increment frame counter
        self._frame_counter += 1

        return frame

    async def cleanup(self) -> None:
        """Release resources and reset state.

        Resets all internal state (amplitudes, peaks, frame counter, completed
        flag) to initial values. Never raises an exception to the caller —
        all errors are suppressed. Safe to call multiple times consecutively
        (idempotent).
        """
        try:
            num_bars = getattr(self, "_num_bars", 0)
            self._amplitudes = [0.0] * num_bars
            self._peaks = [0.0] * num_bars
            self._frame_counter = 0
            self._completed = False
        except Exception:
            pass
