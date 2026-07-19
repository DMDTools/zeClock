"""Clock Plugin - Configurable time display for ZeDMD.

Refactored from the inline clock rendering in ZeClock to be a proper
configurable plugin. Provides all the features of a modern digital clock:

- 12h / 24h time format
- Optional seconds display
- Blinking or static colon separator
- Date display (multiple formats)
- Day of week display
- Timezone support (display time in any timezone)
- Color configuration (fixed color or auto-rotate)
- Configurable display pages (time only, time + date, date only)
- Alarm indicator support
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from .base import ClockPlugin, ConfigField, PluginNotConfiguredError

logger = logging.getLogger(__name__)

# Date format presets
DATE_FORMATS = {
    "dmy": "%d/%m/%Y",       # 19/07/2026
    "mdy": "%m/%d/%Y",       # 07/19/2026
    "ymd": "%Y-%m-%d",       # 2026-07-19
    "short_dmy": "%d/%m",    # 19/07
    "short_mdy": "%m/%d",    # 07/19
    "text_en": "%b %d",      # Jul 19
    "text_fr": "%d %b",      # 19 Jul
}

# Day names (short, 3 chars max for DMD)
DAY_NAMES = {
    "en": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
    "fr": ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"],
    "de": ["MON", "DIE", "MIT", "DON", "FRE", "SAM", "SON"],
    "es": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"],
}

# Available color names mapped to RGB
COLOR_PRESETS: Dict[str, Tuple[int, int, int]] = {
    "orange": (255, 128, 0),
    "blue": (0, 128, 255),
    "red": (255, 0, 0),
    "purple": (255, 0, 255),
    "green": (0, 255, 128),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "pink": (255, 64, 128),
    "white": (255, 255, 255),
}

# Color auto-rotate list (one per minute)
AUTO_COLORS = list(COLOR_PRESETS.values())


class ClockDisplayPlugin(ClockPlugin):
    """Configurable digital clock plugin for ZeDMD.

    Features:
    - 12h/24h time format with optional seconds
    - Blinking or static colon separator
    - Date display in multiple formats
    - Day of week (multi-language)
    - Timezone support (UTC offset or IANA name)
    - Color configuration (fixed or auto-rotate)
    - Multiple display pages cycling through time/date/day
    - Configurable page duration
    """

    @property
    def name(self) -> str:
        return "clock"

    @property
    def description(self) -> str:
        return "Configurable digital clock with date, timezone, and color options"

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    @property
    def rotatable(self) -> bool:
        # The clock plugin is NOT part of normal rotation scheduling.
        # It is rendered between other plugins by the ZeClock state machine.
        # Setting rotatable=False ensures the scheduler never selects it,
        # but it remains visible in the web UI for configuration.
        return False

    @property
    def config_schema(self) -> List[ConfigField]:
        """Declare configuration fields for the Web UI."""
        return [
            ConfigField(
                "time_format",
                "Time Format",
                "text",
                required=False,
                description="24h or 12h (default: 24h)",
                default="24h",
            ),
            ConfigField(
                "show_seconds",
                "Show Seconds",
                "text",
                required=False,
                description="yes or no (default: no)",
                default="no",
            ),
            ConfigField(
                "blink_colon",
                "Blink Colon",
                "text",
                required=False,
                description="yes or no (default: yes)",
                default="yes",
            ),
            ConfigField(
                "show_date",
                "Show Date",
                "text",
                required=False,
                description="yes or no (default: yes)",
                default="yes",
            ),
            ConfigField(
                "date_format",
                "Date Format",
                "text",
                required=False,
                description="dmy, mdy, ymd, short_dmy, short_mdy, text_en, text_fr (default: short_dmy)",
                default="short_dmy",
            ),
            ConfigField(
                "show_day",
                "Show Day of Week",
                "text",
                required=False,
                description="yes or no (default: yes)",
                default="yes",
            ),
            ConfigField(
                "language",
                "Language",
                "text",
                required=False,
                description="en, fr, de, es (default: en)",
                default="en",
            ),
            ConfigField(
                "color",
                "Clock Color",
                "text",
                required=False,
                description="orange, blue, red, purple, green, yellow, cyan, pink, white, auto (default: auto)",
                default="auto",
            ),
            ConfigField(
                "timezone_offset",
                "Timezone Offset (hours)",
                "number",
                required=False,
                description="UTC offset in hours, e.g. 2 for UTC+2, -5 for UTC-5 (default: local)",
                default=None,
            ),
            ConfigField(
                "page_duration_seconds",
                "Page Duration (seconds)",
                "number",
                required=False,
                description="Duration per display page in seconds (default: 5)",
                default=5,
            ),
        ]

    def __init__(self) -> None:
        """Initialize clock plugin with defaults."""
        self._helpers: Any = None
        self._frame_delay_ms: int = 100  # 10 FPS for smooth blink
        self._time_format: str = "24h"
        self._show_seconds: bool = False
        self._blink_colon: bool = True
        self._show_date: bool = True
        self._date_format: str = "short_dmy"
        self._show_day: bool = True
        self._language: str = "en"
        self._color_mode: str = "auto"
        self._fixed_color: Tuple[int, int, int] = (255, 128, 0)
        self._timezone_offset: Optional[float] = None  # None = local time
        self._page_duration_seconds: int = 5
        self._upscale_mode: str = "epx"

        # Runtime state
        self._current_page: int = 0
        self._page_start_time: float = 0.0
        self._last_color_change: float = 0.0
        self._current_color: Tuple[int, int, int] = (255, 128, 0)

        # Frame caching for performance
        self._cached_frame: Optional[Image.Image] = None
        self._cached_key: str = ""

    async def initialize(self, config: dict) -> None:
        """Initialize the clock plugin with configuration.

        Args:
            config: Plugin-specific settings from plugins.yaml.
        """
        self._helpers = config.get("_helpers")
        self._upscale_mode = config.get("_upscale_mode", "epx")

        # Time format: 24h or 12h
        time_format = str(config.get("time_format", "24h")).lower().strip()
        self._time_format = time_format if time_format in ("12h", "24h") else "24h"

        # Show seconds
        self._show_seconds = _parse_bool(config.get("show_seconds", "no"))

        # Blink colon
        self._blink_colon = _parse_bool(config.get("blink_colon", "yes"))

        # Show date
        self._show_date = _parse_bool(config.get("show_date", "yes"))

        # Date format
        date_fmt = str(config.get("date_format", "short_dmy")).lower().strip()
        self._date_format = date_fmt if date_fmt in DATE_FORMATS else "short_dmy"

        # Show day of week
        self._show_day = _parse_bool(config.get("show_day", "yes"))

        # Language
        lang = str(config.get("language", "en")).lower().strip()
        self._language = lang if lang in DAY_NAMES else "en"

        # Color
        color_str = str(config.get("color", "auto")).lower().strip()
        if color_str == "auto":
            self._color_mode = "auto"
            self._current_color = AUTO_COLORS[0]
            self._last_color_change = time.time()
        elif color_str in COLOR_PRESETS:
            self._color_mode = "fixed"
            self._fixed_color = COLOR_PRESETS[color_str]
            self._current_color = self._fixed_color
        else:
            self._color_mode = "auto"
            self._current_color = AUTO_COLORS[0]
            self._last_color_change = time.time()

        # Timezone offset (in hours from UTC, None = local)
        tz_offset = config.get("timezone_offset")
        if tz_offset is not None:
            try:
                self._timezone_offset = float(tz_offset)
            except (ValueError, TypeError):
                self._timezone_offset = None
        else:
            self._timezone_offset = None

        # Page duration
        page_dur = config.get("page_duration_seconds", 5)
        try:
            self._page_duration_seconds = max(2, min(30, int(page_dur)))
        except (ValueError, TypeError):
            self._page_duration_seconds = 5

        # Adjust frame delay: if showing seconds, need faster updates
        if self._show_seconds:
            self._frame_delay_ms = 100  # 10 FPS for smooth second transitions
        elif self._blink_colon:
            self._frame_delay_ms = 200  # 5 FPS for blink
        else:
            self._frame_delay_ms = 500  # 2 FPS for static display

        # Reset page state
        self._current_page = 0
        self._page_start_time = time.time()

        logger.info(
            "[clock] Initialized: format=%s, seconds=%s, blink=%s, "
            "date=%s(%s), day=%s, color=%s, tz_offset=%s",
            self._time_format,
            self._show_seconds,
            self._blink_colon,
            self._show_date,
            self._date_format,
            self._show_day,
            self._color_mode,
            self._timezone_offset,
        )

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the clock display frame.

        The clock cycles through pages:
        - Page 0: Time (always shown)
        - Page 1: Time + Date (if show_date=yes)
        - Page 2: Time + Day of week (if show_day=yes)

        Returns None when all pages have been displayed (signals to plugin
        manager that rotation can continue).
        """
        now = time.time()

        # Update color in auto mode (change every 60 seconds)
        if self._color_mode == "auto":
            if now - self._last_color_change >= 60:
                self._current_color = AUTO_COLORS[int(now // 60) % len(AUTO_COLORS)]
                self._last_color_change = now

        # Determine which pages to show
        pages = self._get_active_pages()
        total_pages = len(pages)

        # Check page advancement
        if now - self._page_start_time >= self._page_duration_seconds:
            self._current_page += 1
            self._page_start_time = now

            # All pages shown - signal completion
            if self._current_page >= total_pages:
                self._current_page = 0
                return None

        # Clamp current page
        if self._current_page >= total_pages:
            self._current_page = 0

        # Get current datetime (with timezone offset if configured)
        dt = self._get_current_datetime()

        # Render the appropriate page
        page_type = pages[self._current_page]
        frame = self._render_page(page_type, dt, width, height)
        return frame

    def _get_active_pages(self) -> List[str]:
        """Get the list of active display pages based on configuration."""
        pages = ["time"]  # Time is always shown

        if self._show_date:
            pages.append("time_date")

        if self._show_day:
            pages.append("time_day")

        return pages

    def _get_current_datetime(self) -> datetime:
        """Get current datetime, adjusted for timezone offset if configured."""
        if self._timezone_offset is not None:
            tz = timezone(timedelta(hours=self._timezone_offset))
            return datetime.now(tz)
        else:
            return datetime.now()

    def _render_page(
        self, page_type: str, dt: datetime, width: int, height: int
    ) -> Image.Image:
        """Render a specific page type.

        Args:
            page_type: One of "time", "time_date", "time_day".
            dt: Current datetime.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        if page_type == "time":
            return self._render_time_only(dt, width, height)
        elif page_type == "time_date":
            return self._render_time_with_date(dt, width, height)
        elif page_type == "time_day":
            return self._render_time_with_day(dt, width, height)
        else:
            return self._render_time_only(dt, width, height)

    def _format_time_string(self, dt: datetime) -> Tuple[str, str]:
        """Format the time string based on configuration.

        Handles 12h/24h format, seconds, and blinking colon.

        Returns:
            Tuple of (time_string, am_pm_indicator).
        """
        # Determine separator based on blink state
        if self._blink_colon:
            blink_state = (int(time.time() * 2)) % 2  # Toggle every 500ms
            separator = ":" if blink_state == 0 else " "
        else:
            separator = ":"

        hour = dt.hour
        am_pm = ""

        if self._time_format == "12h":
            am_pm = "AM" if hour < 12 else "PM"
            hour = hour % 12
            if hour == 0:
                hour = 12

        if self._show_seconds:
            time_str = f"{hour:02d}{separator}{dt.minute:02d}{separator}{dt.second:02d}"
        else:
            time_str = f"{hour:02d}{separator}{dt.minute:02d}"

        return time_str, am_pm

    def _format_date_string(self, dt: datetime) -> str:
        """Format the date string based on configuration."""
        fmt = DATE_FORMATS.get(self._date_format, DATE_FORMATS["short_dmy"])
        return dt.strftime(fmt).upper()

    def _get_day_name(self, dt: datetime) -> str:
        """Get the day of week name in the configured language."""
        day_names = DAY_NAMES.get(self._language, DAY_NAMES["en"])
        return day_names[dt.weekday()]

    def _render_time_only(
        self, dt: datetime, width: int, height: int
    ) -> Image.Image:
        """Render time centered on the full display.

        Uses the largest available font (STANDARD) for maximum visibility.
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        frame = self._helpers.create_frame()
        time_str, am_pm = self._format_time_string(dt)
        color = self._current_color

        # Render time centered using STANDARD font (largest)
        time_frame = self._helpers.render_text(
            time_str, centered=True, color=color
        )
        frame = self._helpers.composite_frames(frame, time_frame)

        # If 12h mode, add AM/PM indicator in top-right corner (SYSTEM font)
        if am_pm and self._time_format == "12h":
            ampm_frame = self._helpers.render_text_right_aligned(
                am_pm, y=0, margin=2, color=color, font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, ampm_frame)

        return frame

    def _render_time_with_date(
        self, dt: datetime, width: int, height: int
    ) -> Image.Image:
        """Render time on top and date on bottom.

        Layout:
        - Top row: Time in MENU font (medium size)
        - Bottom row: Date in SYSTEM font (small size)
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        frame = self._helpers.create_frame()
        time_str, am_pm = self._format_time_string(dt)
        date_str = self._format_date_string(dt)
        color = self._current_color

        # Scale factor for HD
        sy = height / 32

        # Time at top (MENU font - medium size, centered)
        time_width = self._helpers.get_text_width(time_str, font_name="MENU")
        time_x = (width - time_width) // 2
        time_y = int(1 * sy)

        time_frame = self._helpers.render_text(
            time_str, x=time_x, y=time_y, color=color, font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, time_frame)

        # AM/PM next to time if 12h
        if am_pm and self._time_format == "12h":
            ampm_x = time_x + time_width + 2
            ampm_frame = self._helpers.render_text(
                am_pm, x=ampm_x, y=time_y, color=color, font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, ampm_frame)

        # Date at bottom (SYSTEM font - small, centered)
        date_width = self._helpers.get_text_width(date_str, font_name="SYSTEM")
        date_x = (width - date_width) // 2
        date_y = int(23 * sy)

        # Use a slightly dimmer version of the color for the date
        date_color = (
            int(color[0] * 0.6),
            int(color[1] * 0.6),
            int(color[2] * 0.6),
        )

        date_frame = self._helpers.render_text(
            date_str, x=date_x, y=date_y, color=date_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, date_frame)

        return frame

    def _render_time_with_day(
        self, dt: datetime, width: int, height: int
    ) -> Image.Image:
        """Render time on top and day of week on bottom.

        Layout:
        - Top row: Time in MENU font
        - Bottom row: Day name in SYSTEM font (highlighted color)
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        frame = self._helpers.create_frame()
        time_str, am_pm = self._format_time_string(dt)
        day_name = self._get_day_name(dt)
        color = self._current_color

        # Scale factor for HD
        sy = height / 32

        # Time at top (MENU font, centered)
        time_width = self._helpers.get_text_width(time_str, font_name="MENU")
        time_x = (width - time_width) // 2
        time_y = int(1 * sy)

        time_frame = self._helpers.render_text(
            time_str, x=time_x, y=time_y, color=color, font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, time_frame)

        # AM/PM if 12h
        if am_pm and self._time_format == "12h":
            ampm_x = time_x + time_width + 2
            ampm_frame = self._helpers.render_text(
                am_pm, x=ampm_x, y=time_y, color=color, font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, ampm_frame)

        # Day of week at bottom (SYSTEM font, centered, bright)
        day_width = self._helpers.get_text_width(day_name, font_name="SYSTEM")
        day_x = (width - day_width) // 2
        day_y = int(23 * sy)

        # Use a contrasting color for the day name
        day_color = (
            min(255, int(color[0] * 0.5) + 100),
            min(255, int(color[1] * 0.5) + 100),
            min(255, int(color[2] * 0.5) + 100),
        )

        day_frame = self._helpers.render_text(
            day_name, x=day_x, y=day_y, color=day_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, day_frame)

        return frame

    async def cleanup(self) -> None:
        """Reset page state for next activation."""
        self._current_page = 0
        self._page_start_time = time.time()
        self._cached_frame = None
        self._cached_key = ""


def _parse_bool(value: Any) -> bool:
    """Parse a boolean value from various input types.

    Handles: True/False, "yes"/"no", "true"/"false", "1"/"0", 1/0.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower().strip() in ("yes", "true", "1", "on")
    return False
