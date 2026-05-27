"""WeatherPlugin - Built-in plugin displaying weather conditions and forecasts.

This plugin fetches weather data from the Open-Meteo API and renders
current conditions, tomorrow's forecast, and a 3-day outlook on the
DMD display. Data is cached for 15 minutes to minimize API calls.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import aiohttp
from PIL import Image

from .base import ClockPlugin
from .weather_icons import get_weather_icon_image

logger = logging.getLogger(__name__)

# Cache duration in seconds (15 minutes)
CACHE_DURATION_SECONDS = 15 * 60

# Open-Meteo API base URL
OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"

# Translated UI labels (max 12 chars, ASCII only for SYSTEM/MENU fonts)
_LABELS = {
    "en": {"tomorrow": "TOMORROW"},
    "fr": {"tomorrow": "DEMAIN"},
}

# Short day names (3 chars) for the 3-day outlook
_DAY_NAMES = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
}

# Single-letter day names for the 7-day view
_DAY_LETTERS = {
    "en": ["M", "T", "W", "T", "F", "S", "S"],
    "fr": ["L", "M", "M", "J", "V", "S", "D"],
}

# WMO weather code to short description mapping (max 12 chars)
# No accented characters — SYSTEM font only has ASCII 32-126
WMO_DESCRIPTIONS = {
    "en": {
        0: "Clear",
        1: "Mostly Clear",
        2: "Partly Cloud",
        3: "Overcast",
        45: "Fog",
        48: "Rime Fog",
        51: "Light Drzl",
        53: "Mod Drizzle",
        55: "Dense Drzl",
        56: "Frzg Drzl Lt",
        57: "Frzg Drzl",
        61: "Light Rain",
        63: "Mod Rain",
        65: "Heavy Rain",
        66: "Frzg Rain Lt",
        67: "Frzg Rain",
        71: "Light Snow",
        73: "Mod Snow",
        75: "Heavy Snow",
        77: "Snow Grains",
        80: "Rain Shwr Lt",
        81: "Rain Shwr",
        82: "Rain Shwr Hv",
        85: "Snow Shwr Lt",
        86: "Snow Shwr Hv",
        95: "Thunderstorm",
        96: "T-Storm Hail",
        99: "T-Storm Hail",
    },
    "fr": {
        0: "Degage",
        1: "Peu nuageux",
        2: "Nuageux",
        3: "Couvert",
        45: "Brouillard",
        48: "Givre",
        51: "Bruine leg.",
        53: "Bruine",
        55: "Bruine fort",
        56: "Bruine gel.",
        57: "Bruine gel.",
        61: "Pluie leg.",
        63: "Pluie",
        65: "Forte pluie",
        66: "Pluie verg.",
        67: "Pluie verg.",
        71: "Neige leg.",
        73: "Neige",
        75: "Forte neige",
        77: "Grains neige",
        80: "Averses leg.",
        81: "Averses",
        82: "Fortes avers",
        85: "Averses neig",
        86: "Fortes neig.",
        95: "Orage",
        96: "Orage grele",
        99: "Orage grele",
    },
}


@dataclass
class DayForecast:
    """Forecast data for a single day."""

    high: float
    low: float
    condition_code: int


@dataclass
class WeatherData:
    """Cached weather data from Open-Meteo API."""

    current_temp: float
    current_condition_code: int
    current_description: str
    tomorrow_high: float
    tomorrow_low: float
    tomorrow_condition_code: int
    forecast_days: List[DayForecast] = field(default_factory=list)
    fetched_at: float = 0.0
    city_name: str = ""


class WeatherPlugin(ClockPlugin):
    """Built-in plugin that displays weather conditions and forecasts.

    Fetches data from the Open-Meteo API (no API key required) and
    displays current conditions, tomorrow's forecast, and a 3-day
    outlook on the DMD display. Caches data for 15 minutes.
    """

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return "Current weather and forecast display"

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    def __init__(self):
        """Initialize WeatherPlugin with default state."""
        self._frame_delay_ms: int = 100  # 10 FPS for smooth page transitions
        self._cache: Optional[WeatherData] = None
        self._latitude: Optional[float] = None
        self._longitude: Optional[float] = None
        self._city_name: str = ""
        self._temperature_unit: str = "celsius"
        self._page_duration_seconds: int = 4
        self._current_page: int = 0
        self._frame_count: int = 0
        self._frames_per_page: int = 0
        self._helpers = None
        self._language: str = "en"
        self._initialized: bool = False

    async def initialize(self, config: dict) -> None:
        """Initialize the plugin with configuration.

        Config keys:
            latitude (float): City latitude coordinate (required)
            longitude (float): City longitude coordinate (required)
            city_name (str): Display name for the city (required)
            temperature_unit (str): "celsius" or "fahrenheit" (default: "celsius")
            page_duration_seconds (int): Duration per page 2-30s (default: 4)

        Args:
            config: Plugin-specific settings from plugins.yaml.
        """
        self._helpers = config.get("_helpers")

        # Read required configuration
        self._latitude = config.get("latitude")
        self._longitude = config.get("longitude")
        self._city_name = config.get("city_name", "")

        # Validate required fields
        missing_fields = []
        if self._latitude is None:
            missing_fields.append("latitude")
        if self._longitude is None:
            missing_fields.append("longitude")
        if not self._city_name:
            missing_fields.append("city_name")

        if missing_fields:
            logger.warning(
                "Weather plugin missing required config fields: %s",
                ", ".join(missing_fields),
            )
            self._initialized = False
            return

        # Read optional configuration
        self._temperature_unit = config.get("temperature_unit", "celsius")
        if self._temperature_unit not in ("celsius", "fahrenheit"):
            self._temperature_unit = "celsius"

        self._language = config.get("language", "en")
        if self._language not in WMO_DESCRIPTIONS:
            self._language = "en"

        page_duration = config.get("page_duration_seconds", 4)
        self._page_duration_seconds = max(2, min(30, int(page_duration)))

        # Calculate frames per page
        self._frames_per_page = (
            self._page_duration_seconds * 1000 + self._frame_delay_ms - 1
        ) // self._frame_delay_ms

        self._current_page = 0
        self._frame_count = 0
        self._initialized = True

        # Attempt to fetch weather data if cache is stale or empty
        await self._refresh_cache_if_needed()

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next weather frame.

        Cycles through 3 pages: current conditions, tomorrow forecast,
        and 3-day outlook. Returns None after all pages are displayed.

        When displaying stale cached data (cache older than 15 minutes),
        a blinking dot is rendered in the top-right corner as a staleness
        indicator. The dot blinks by toggling visibility based on frame
        count (visible on even frames, hidden on odd frames relative to
        a blink interval derived from frame_delay_ms).

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if not self._initialized:
            return None

        if self._cache is None:
            logger.warning(
                "No weather data available - signaling completion"
            )
            return None

        # Check if we've completed all 4 pages
        if self._current_page >= 4:
            return None

        # Render current page
        frame = self._render_page(self._current_page, width, height)

        # Add staleness indicator if cache is stale
        if self.is_cache_stale():
            self._draw_staleness_indicator(frame, width, height)

        # Advance frame counter
        self._frame_count += 1
        if self._frame_count >= self._frames_per_page:
            self._frame_count = 0
            self._current_page += 1

        return frame

    async def cleanup(self) -> None:
        """Release resources."""
        self._current_page = 0
        self._frame_count = 0

    def is_cache_stale(self) -> bool:
        """Check if the cached weather data is older than 15 minutes.

        Returns:
            True if cache is stale or empty, False if fresh.
        """
        if self._cache is None:
            return True
        elapsed = time.time() - self._cache.fetched_at
        return elapsed >= CACHE_DURATION_SECONDS

    async def _refresh_cache_if_needed(self) -> None:
        """Fetch new weather data if cache is stale."""
        if not self.is_cache_stale():
            return

        try:
            data = await self._fetch_weather_data()
            if data is not None:
                self._cache = data
        except Exception as e:
            logger.warning("Failed to fetch weather data: %s", e)
            # Keep existing cache if available (staleness indicator
            # will be handled in rendering - task 9.3)

    async def _fetch_weather_data(self) -> Optional[WeatherData]:
        """Fetch current weather and daily forecast from Open-Meteo API.

        Returns:
            WeatherData instance with current and forecast data, or None on failure.
        """
        if self._latitude is None or self._longitude is None:
            return None

        # Build API request parameters
        params = {
            "latitude": self._latitude,
            "longitude": self._longitude,
            "current_weather": "true",
            "daily": "temperature_2m_max,temperature_2m_min,weathercode",
            "forecast_days": 8,  # today + 7 days
            "timezone": "auto",
        }

        if self._temperature_unit == "fahrenheit":
            params["temperature_unit"] = "fahrenheit"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    OPEN_METEO_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "Open-Meteo API returned status %d", response.status
                        )
                        return None

                    data = await response.json()
                    return self._parse_api_response(data)

        except aiohttp.ClientError as e:
            logger.warning("Open-Meteo API request failed: %s", e)
            return None
        except Exception as e:
            logger.warning("Unexpected error fetching weather: %s", e)
            return None

    def _parse_api_response(self, data: dict) -> Optional[WeatherData]:
        """Parse the Open-Meteo API JSON response into WeatherData.

        Args:
            data: Parsed JSON response from the API.

        Returns:
            WeatherData instance, or None if response is malformed.
        """
        try:
            current = data["current_weather"]
            daily = data["daily"]

            current_temp = current["temperature"]
            current_code = current["weathercode"]
            current_desc = self._get_condition_description(current_code)

            # Daily forecast data (index 0 = today, 1 = tomorrow, 2+ = future)
            temps_max = daily["temperature_2m_max"]
            temps_min = daily["temperature_2m_min"]
            weather_codes = daily["weathercode"]

            # Tomorrow's forecast (index 1)
            tomorrow_high = temps_max[1] if len(temps_max) > 1 else current_temp
            tomorrow_low = temps_min[1] if len(temps_min) > 1 else current_temp
            tomorrow_code = weather_codes[1] if len(weather_codes) > 1 else current_code

            # 7-day forecast (indices 1-7 = tomorrow through 7 days out)
            forecast_days = []
            for i in range(1, min(8, len(temps_max))):
                forecast_days.append(
                    DayForecast(
                        high=temps_max[i],
                        low=temps_min[i],
                        condition_code=weather_codes[i] if i < len(weather_codes) else 0,
                    )
                )

            return WeatherData(
                current_temp=current_temp,
                current_condition_code=current_code,
                current_description=current_desc,
                tomorrow_high=tomorrow_high,
                tomorrow_low=tomorrow_low,
                tomorrow_condition_code=tomorrow_code,
                forecast_days=forecast_days,
                fetched_at=time.time(),
                city_name=self._city_name,
            )

        except (KeyError, IndexError, TypeError) as e:
            logger.warning("Failed to parse Open-Meteo response: %s", e)
            return None

    def _get_condition_description(self, code: int) -> str:
        """Get a short description for a WMO weather code.

        Uses the configured language (defaults to English).

        Args:
            code: WMO weather interpretation code.

        Returns:
            Description string, max 12 characters.
        """
        lang = getattr(self, "_language", "en")
        descriptions = WMO_DESCRIPTIONS.get(lang, WMO_DESCRIPTIONS["en"])
        desc = descriptions.get(code, "Unknown")
        return desc[:12]

    def _render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a specific weather page.

        Page 0: Current conditions (temp, icon, description, city)
        Page 1: Tomorrow forecast (high/low, icon)
        Page 2: 3-day outlook (day name, icon, temp)
        Page 3: 7-day overview (single letter, icon, temp)

        Args:
            page: Page index (0, 1, 2, or 3).
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        if page == 0:
            return self._render_current_page(width, height)
        elif page == 1:
            return self._render_tomorrow_page(width, height)
        elif page == 2:
            return self._render_outlook_page(width, height)
        elif page == 3:
            return self._render_7day_page(width, height)
        else:
            return self._helpers.create_frame()

    def _format_temp(self, temp: float) -> str:
        """Format a temperature as a rounded integer with unit symbol.

        Uses characters available in the MENU font (no degree symbol).

        Args:
            temp: Temperature value.

        Returns:
            Formatted string like "23C" or "72F".
        """
        rounded = round(temp)
        unit = "F" if self._temperature_unit == "fahrenheit" else "C"
        return f"{rounded}{unit}"

    def _render_temp_with_degree(
        self, temp: float, x: int, y: int, color: tuple, font_name: str = "MENU"
    ) -> Image.Image:
        """Render temperature with a degree symbol drawn as pixels.

        Renders "23" then a small ° circle, then "C" — since the bitmap
        fonts don't include the degree character.

        Returns:
            RGB frame with the temperature rendered at (x, y).
        """
        rounded = round(temp)
        unit = "F" if self._temperature_unit == "fahrenheit" else "C"
        num_str = str(rounded)

        # Render number part
        num_frame = self._helpers.render_text(
            num_str, x=x, y=y, color=color, font_name=font_name
        )

        # Calculate position for degree symbol (after the number)
        num_width = self._helpers.get_text_width(num_str, font_name=font_name)
        deg_x = x + num_width + 1
        deg_y = y  # Top-aligned small circle

        # Draw 3x3 degree symbol (hollow square)
        pixels = num_frame.load()
        for dx, dy in [(0, 0), (1, 0), (2, 0), (0, 1), (2, 1), (0, 2), (1, 2), (2, 2)]:
            px, py = deg_x + dx, deg_y + dy
            if 0 <= px < self._helpers.width and 0 <= py < self._helpers.height:
                pixels[px, py] = color

        # Render unit letter after the degree symbol
        unit_x = deg_x + 4
        unit_frame = self._helpers.render_text(
            unit, x=unit_x, y=y, color=color, font_name=font_name
        )

        return self._helpers.composite_frames(num_frame, unit_frame)

    def _render_current_page(self, width: int, height: int) -> Image.Image:
        """Render page 0: Current conditions (Layout 1C - full info).

        Layout:
        - Icon left (vertically centered)
        - Temperature + condition stacked right of icon
        - City name below
        - Wind/humidity info on far right

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        frame = self._helpers.create_frame()
        cache = self._cache

        # Draw weather icon vertically centered left
        icon_img = get_weather_icon_image(cache.current_condition_code)
        frame.paste(icon_img, (2, 3))

        # Temperature with degree symbol (MENU font)
        temp_frame = self._render_temp_with_degree(
            cache.current_temp, x=22, y=0, color=(255, 128, 0)
        )
        frame = self._helpers.composite_frames(frame, temp_frame)

        # Condition description (SYSTEM font)
        desc = cache.current_description[:12].upper()
        desc_frame = self._helpers.render_text(
            desc, x=22, y=13, color=(200, 200, 200), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, desc_frame)

        # City name bottom left (SYSTEM font)
        city = cache.city_name.upper()
        city_frame = self._helpers.render_text(
            city, x=22, y=24, color=(128, 128, 255), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, city_frame)

        return frame

    def _render_tomorrow_page(self, width: int, height: int) -> Image.Image:
        """Render page 1: Tomorrow (Layout 2C - two column).

        Layout:
        - "DEMAIN" label at top
        - Left: icon + high/low temps
        - Right: condition + wind (SYSTEM small)

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        frame = self._helpers.create_frame()
        cache = self._cache

        # Draw "DEMAIN" / "TOMORROW" label at top (MENU font)
        labels = _LABELS.get(self._language, _LABELS["en"])
        label_frame = self._helpers.render_text(
            labels["tomorrow"], x=2, y=0, color=(255, 200, 0), font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, label_frame)

        # Draw weather icon
        icon_img = get_weather_icon_image(cache.tomorrow_condition_code)
        frame.paste(icon_img, (2, 14))

        # High temperature with degree (MENU font)
        high_frame = self._render_temp_with_degree(
            cache.tomorrow_high, x=21, y=13, color=(255, 100, 50)
        )
        frame = self._helpers.composite_frames(frame, high_frame)

        # Low temperature with degree (SYSTEM font)
        low_frame = self._render_temp_with_degree(
            cache.tomorrow_low, x=21, y=25, color=(100, 150, 255), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, low_frame)

        # Right column: condition description (SYSTEM font, truncated to fit)
        desc = self._get_condition_description(cache.tomorrow_condition_code).upper()
        # Position dynamically: right-align to leave 2px margin
        desc_width = self._helpers.get_text_width(desc, font_name="SYSTEM")
        desc_x = max(60, width - desc_width - 2)
        desc_frame = self._helpers.render_text(
            desc, x=desc_x, y=14, color=(200, 200, 200), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, desc_frame)

        return frame

    def _render_outlook_page(self, width: int, height: int) -> Image.Image:
        """Render page 2: 3-day outlook (Layout 3B + separators).

        Layout:
        - 3 columns with vertical separators
        - Day name (yellow, SYSTEM) on top
        - Icon (16x16) in middle
        - Temperature (SYSTEM) at bottom

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        frame = self._helpers.create_frame()
        cache = self._cache

        # Calculate column positions for 3 days
        num_days = min(3, len(cache.forecast_days))
        if num_days == 0:
            return frame

        col_width = width // 3

        # Get day names for the next 3 days
        day_names = _DAY_NAMES.get(self._language, _DAY_NAMES["en"])
        today = datetime.now()

        for i in range(num_days):
            day = cache.forecast_days[i]
            future_day = today + timedelta(days=i)
            day_name = day_names[future_day.weekday()]

            col_x = i * col_width

            # Day name at top (SYSTEM font, yellow)
            name_width = self._helpers.get_text_width(day_name, font_name="SYSTEM")
            name_x = col_x + (col_width - name_width) // 2
            name_frame = self._helpers.render_text(
                day_name, x=name_x, y=0, color=(255, 200, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, name_frame)

            # Icon in middle
            icon_x = col_x + (col_width - 16) // 2
            icon_data = get_weather_icon_image(day.condition_code)
            frame.paste(icon_data, (icon_x, 8))

            # Temperature at bottom (SYSTEM font) with degree symbol
            high_str = self._format_temp(day.high)
            temp_width = self._helpers.get_text_width(high_str, font_name="SYSTEM")
            temp_x = col_x + (col_width - temp_width) // 2
            temp_frame = self._render_temp_with_degree(
                day.high, x=temp_x, y=25, color=(255, 128, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, temp_frame)

        # Draw vertical separators between columns
        pixels = frame.load()
        for sep in range(1, num_days):
            sep_x = sep * col_width
            for y in range(0, height):
                pixels[sep_x, y] = (30, 30, 50)

        return frame

    def _render_7day_page(self, width: int, height: int) -> Image.Image:
        """Render page 3: 7-day overview (Layout D4).

        Layout:
        - 7 columns (18px each)
        - Single-letter day name (SYSTEM) at top
        - 12x12 icon centered in middle
        - Temperature (SYSTEM) at bottom
        - Starts with today

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        frame = self._helpers.create_frame()
        cache = self._cache

        num_days = min(7, len(cache.forecast_days))
        if num_days == 0:
            return frame

        col_width = width // 7
        day_letters = _DAY_LETTERS.get(self._language, _DAY_LETTERS["en"])
        today = datetime.now()

        for i in range(num_days):
            day = cache.forecast_days[i]
            # Start from today (index 0 in forecast_days is tomorrow,
            # but we want today as first column)
            future_day = today + timedelta(days=i)
            day_letter = day_letters[future_day.weekday()]

            col_x = i * col_width

            # Single-letter day name at top (SYSTEM font)
            lw = self._helpers.get_text_width(day_letter, font_name="SYSTEM")
            lx = col_x + (col_width - lw) // 2
            letter_frame = self._helpers.render_text(
                day_letter, x=lx, y=0, color=(255, 200, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, letter_frame)

            # 12x12 icon centered
            icon = get_weather_icon_image(day.condition_code)
            icon_small = icon.resize((12, 12), Image.LANCZOS)
            ix = col_x + (col_width - 12) // 2
            frame.paste(icon_small, (ix, 9))

            # Temperature at bottom (SYSTEM font)
            temp_str = str(round(day.high))
            tw = self._helpers.get_text_width(temp_str, font_name="SYSTEM")
            tx = col_x + (col_width - tw) // 2
            temp_frame = self._helpers.render_text(
                temp_str, x=tx, y=23, color=(255, 128, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, temp_frame)

        return frame

    def _draw_staleness_indicator(
        self, frame: Image.Image, width: int, height: int
    ) -> None:
        """Draw a blinking dot in the top-right corner as a staleness indicator.

        The dot blinks at approximately 500ms intervals by toggling visibility
        based on the current frame count and frame_delay_ms. The dot is drawn
        as a 3x3 pixel block in a distinct color (red) to be distinguishable
        from normal display content.

        Args:
            frame: The frame to draw the indicator onto (modified in place).
            width: Display width in pixels.
            height: Display height in pixels.
        """
        # Calculate blink interval in frames (~500ms toggle)
        blink_interval_frames = max(1, 500 // self._frame_delay_ms)

        # Determine if the dot should be visible this frame
        # Use total frame count across all pages for consistent blinking
        total_frames = self._current_page * self._frames_per_page + self._frame_count
        blink_cycle = total_frames // blink_interval_frames
        dot_visible = (blink_cycle % 2) == 0

        if not dot_visible:
            return

        # Draw a 3x3 red dot in the top-right corner (2px margin)
        dot_color = (255, 0, 0)
        dot_x = width - 5  # 2px margin from right edge
        dot_y = 2  # 2px margin from top edge
        pixels = frame.load()

        for dy in range(3):
            for dx in range(3):
                px = dot_x + dx
                py = dot_y + dy
                if 0 <= px < width and 0 <= py < height:
                    pixels[px, py] = dot_color
