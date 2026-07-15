"""Speaker Timer Plugin - Conference countdown timer for ZeDMD.

Displays a large countdown timer visible from stage distance.
Color changes automatically based on remaining time:
  - Green: more than 5 minutes remaining
  - Yellow: between 1 and 5 minutes remaining
  - Red: less than 1 minute remaining or time exceeded

Controlled remotely via the web UI (start/pause/reset/presets).
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from .base import ClockPlugin

logger = logging.getLogger(__name__)

# Timer states
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_FINISHED = "finished"  # countdown reached zero, now counting up

# Color thresholds (as percentage of total duration)
DEFAULT_YELLOW_THRESHOLD_PCT = 20  # below 20% remaining → orange
DEFAULT_RED_THRESHOLD_PCT = 10  # below 10% remaining → red

# Default presets (in seconds)
DEFAULT_PRESETS: List[Dict[str, Any]] = [
    {"name": "Lightning", "duration": 300},
    {"name": "Short", "duration": 1200},
    {"name": "Standard", "duration": 2700},
]

# Colors
COLOR_GREEN: Tuple[int, int, int] = (0, 255, 0)
COLOR_YELLOW: Tuple[int, int, int] = (255, 255, 0)
COLOR_RED: Tuple[int, int, int] = (255, 0, 0)
COLOR_IDLE: Tuple[int, int, int] = (255, 128, 0)  # orange when idle


class SpeakerTimerPlugin(ClockPlugin):
    """Conference speaker countdown timer.

    This plugin is designed to be force-activated via the web UI and
    stay active indefinitely until manually stopped. It does NOT signal
    completion on its own (never returns None from render_frame).
    """

    # Class-level state — persists across activations
    _timer_state: str = STATE_IDLE
    _duration_seconds: int = 1200  # 20 minutes default
    _start_time: float = 0.0
    _elapsed_at_pause: float = 0.0
    _presets: List[Dict[str, Any]] = DEFAULT_PRESETS.copy()
    _yellow_threshold_pct: int = DEFAULT_YELLOW_THRESHOLD_PCT
    _red_threshold_pct: int = DEFAULT_RED_THRESHOLD_PCT

    @property
    def name(self) -> str:
        return "speaker-timer"

    @property
    def description(self) -> str:
        return "Conference speaker countdown timer with color changes"

    @property
    def frame_delay_ms(self) -> int:
        return 200  # 5 FPS — sufficient for a timer display

    @property
    def rotatable(self) -> bool:
        return False

    async def initialize(self, config: dict) -> None:
        """Initialize the speaker timer plugin.

        Config keys:
            yellow_threshold (int): Seconds remaining to switch to yellow (default: 300)
            red_threshold (int): Seconds remaining to switch to red (default: 60)
            presets (list): List of {"name": str, "duration": int} dicts
        """
        self._helpers: Any = config.get("_helpers")

        # Apply config (only on first init or if explicitly provided)
        if "yellow_threshold" in config:
            SpeakerTimerPlugin._yellow_threshold_pct = int(config["yellow_threshold"])
        if "red_threshold" in config:
            SpeakerTimerPlugin._red_threshold_pct = int(config["red_threshold"])
        if "presets" in config:
            SpeakerTimerPlugin._presets = config["presets"]

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the timer display with progress bar.

        Never returns None — this plugin stays active until force-deactivated.
        """
        remaining = self._get_remaining_seconds()
        color = self._get_color(remaining)

        # When finished, freeze display at 00:00 and blink
        if SpeakerTimerPlugin._timer_state == STATE_FINISHED:
            time_str = "00:00"
            color = COLOR_RED
            blink = int(time.time() * 2) % 2
            if blink == 0:
                return self._helpers.create_frame()  # blank frame for blink
        else:
            time_str = self._format_time(remaining)

        frame = self._helpers.create_frame()

        # Draw progress bar at the bottom (2px tall, full width)
        self._draw_progress_bar(frame, width, height, remaining, color)

        # Render the time string centered using the largest font
        text_frame = self._helpers.render_text(time_str, centered=True, color=color)
        frame = self._helpers.composite_frames(frame, text_frame)

        # If paused, add a blinking effect (hide text every other second)
        if SpeakerTimerPlugin._timer_state == STATE_PAUSED:
            blink = int(time.time() * 2) % 2
            if blink == 0:
                frame = self._helpers.create_frame()  # blank frame for blink

        return frame

    def _draw_progress_bar(
        self,
        frame: Image.Image,
        width: int,
        height: int,
        remaining: float,
        color: Tuple[int, int, int],
    ) -> None:
        """Draw a multi-color progress bar at the bottom of the frame.

        The bar is 4px tall, full width, with colored segments:
        red zone | yellow/orange zone | green zone
        The fill level shrinks from right to left as time runs out.
        When overtime, the full bar is red.
        """
        bar_height = 4
        bar_y = height - bar_height

        if SpeakerTimerPlugin._timer_state == STATE_IDLE:
            ratio = 1.0
        elif remaining <= 0:
            ratio = 0.0
        else:
            ratio = remaining / SpeakerTimerPlugin._duration_seconds
            ratio = max(0.0, min(1.0, ratio))

        # Calculate zone boundaries as fractions of the full bar
        # Red zone: 0% to red_threshold_pct% of the bar
        # Orange zone: red_threshold_pct% to yellow_threshold_pct% of the bar
        # Green zone: yellow_threshold_pct% to 100% of the bar
        red_frac = SpeakerTimerPlugin._red_threshold_pct / 100.0
        yellow_frac = SpeakerTimerPlugin._yellow_threshold_pct / 100.0

        # Pixel boundaries for each zone
        red_end = int(width * red_frac)
        yellow_end = int(width * yellow_frac)
        # Green goes from yellow_end to width

        # How far the bar is filled (from left)
        fill_px = int(width * ratio)

        pixels = frame.load()
        assert pixels is not None

        for y in range(bar_y, min(bar_y + bar_height, height)):
            for x in range(width):
                if x < fill_px:
                    # Determine color based on which zone this pixel is in
                    if x < red_end:
                        px_color = COLOR_RED
                    elif x < yellow_end:
                        px_color = (255, 128, 0)  # orange
                    else:
                        px_color = COLOR_GREEN
                    pixels[x, y] = px_color

    async def cleanup(self) -> None:
        """Cleanup — state is preserved at class level for next activation."""
        pass

    # --- Timer control methods (called by the web API) ---

    @classmethod
    def start(cls) -> Dict[str, Any]:
        """Start or resume the timer."""
        if cls._timer_state == STATE_IDLE or cls._timer_state == STATE_FINISHED:
            # Fresh start
            cls._start_time = time.time()
            cls._elapsed_at_pause = 0.0
            cls._timer_state = STATE_RUNNING
        elif cls._timer_state == STATE_PAUSED:
            # Resume from pause
            cls._start_time = time.time() - cls._elapsed_at_pause
            cls._timer_state = STATE_RUNNING
        return cls.get_status()

    @classmethod
    def pause(cls) -> Dict[str, Any]:
        """Pause the timer."""
        if cls._timer_state == STATE_RUNNING:
            cls._elapsed_at_pause = time.time() - cls._start_time
            cls._timer_state = STATE_PAUSED
        return cls.get_status()

    @classmethod
    def reset(cls) -> Dict[str, Any]:
        """Reset the timer to idle state."""
        cls._timer_state = STATE_IDLE
        cls._start_time = 0.0
        cls._elapsed_at_pause = 0.0
        return cls.get_status()

    @classmethod
    def set_duration(cls, seconds: int) -> Dict[str, Any]:
        """Set the countdown duration (resets the timer)."""
        cls._duration_seconds = max(1, int(seconds))
        cls._timer_state = STATE_IDLE
        cls._start_time = 0.0
        cls._elapsed_at_pause = 0.0
        return cls.get_status()

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get current timer status."""
        remaining = cls._get_remaining_seconds_class()
        return {
            "state": cls._timer_state,
            "duration": cls._duration_seconds,
            "remaining": remaining,
            "elapsed": cls._get_elapsed_seconds(),
            "formatted": cls._format_time_class(remaining),
            "presets": cls._presets,
            "yellow_threshold": cls._yellow_threshold_pct,
            "red_threshold": cls._red_threshold_pct,
        }

    @classmethod
    def _get_elapsed_seconds(cls) -> float:
        """Get elapsed seconds since timer started."""
        if cls._timer_state == STATE_RUNNING:
            return time.time() - cls._start_time
        elif cls._timer_state == STATE_PAUSED:
            return cls._elapsed_at_pause
        elif cls._timer_state == STATE_FINISHED:
            return time.time() - cls._start_time
        return 0.0

    @classmethod
    def _get_remaining_seconds_class(cls) -> float:
        """Get remaining seconds (negative if overtime)."""
        if cls._timer_state == STATE_IDLE:
            return float(cls._duration_seconds)
        elapsed = cls._get_elapsed_seconds()
        remaining = cls._duration_seconds - elapsed
        if remaining <= 0 and cls._timer_state == STATE_RUNNING:
            cls._timer_state = STATE_FINISHED
        return remaining

    def _get_remaining_seconds(self) -> float:
        """Instance method wrapper for class method."""
        return SpeakerTimerPlugin._get_remaining_seconds_class()

    def _get_color(self, remaining: float) -> Tuple[int, int, int]:
        """Determine display color based on remaining time percentage."""
        if SpeakerTimerPlugin._timer_state == STATE_IDLE:
            return COLOR_IDLE

        if remaining <= 0:
            return COLOR_RED

        duration = SpeakerTimerPlugin._duration_seconds
        if duration <= 0:
            return COLOR_GREEN

        pct_remaining = (remaining / duration) * 100.0
        if pct_remaining <= SpeakerTimerPlugin._red_threshold_pct:
            return COLOR_RED
        elif pct_remaining <= SpeakerTimerPlugin._yellow_threshold_pct:
            return COLOR_YELLOW
        else:
            return COLOR_GREEN

    @classmethod
    def _format_time_class(cls, remaining: float) -> str:
        """Format remaining time as HH:MM:SS or -MM:SS."""
        if cls._timer_state == STATE_IDLE:
            total: float = float(cls._duration_seconds)
        else:
            total = remaining

        negative = total < 0
        abs_seconds = int(abs(total))

        hours = abs_seconds // 3600
        minutes = (abs_seconds % 3600) // 60
        seconds = abs_seconds % 60

        if negative:
            if hours > 0:
                return f"-{hours}:{minutes:02d}:{seconds:02d}"
            else:
                return f"-{minutes:02d}:{seconds:02d}"
        else:
            if hours > 0:
                return f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes:02d}:{seconds:02d}"

    def _format_time(self, remaining: float) -> str:
        """Instance method wrapper."""
        return SpeakerTimerPlugin._format_time_class(remaining)

    # --- Plugin web control interface ---

    @classmethod
    def get_web_controls(cls) -> Dict[str, Any]:
        """Declare web UI controls for this plugin.

        Returns a descriptor that the web UI uses to render controls.
        """
        return {
            "plugin": "speaker-timer",
            "label": "Speaker Timer",
            "api_prefix": "/api/speaker-timer",
            "controls": [
                {
                    "type": "button",
                    "action": "start",
                    "label": "Start",
                    "style": "success",
                },
                {
                    "type": "button",
                    "action": "pause",
                    "label": "Pause",
                    "style": "warning",
                },
                {
                    "type": "button",
                    "action": "reset",
                    "label": "Reset",
                    "style": "danger",
                },
            ],
            "has_custom_ui": True,
        }
