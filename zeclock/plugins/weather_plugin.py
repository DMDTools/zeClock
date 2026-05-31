"""WeatherPlugin - Built-in plugin displaying weather conditions and forecasts.

This plugin fetches weather data from the Open-Meteo API and renders
current conditions, tomorrow's forecast, and a 3-day outlook on the
DMD display. Data is cached for 15 minutes to minimize API calls.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp
from PIL import Image

from .base import PagedPlugin
from .helpers import draw_staleness_indicator
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


class WeatherPlugin(PagedPlugin):
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

    def __init__(self) -> None:
        """Initialize WeatherPlugin with default state."""
        super().__init__()
        self._cache: Optional[WeatherData] = None
        self._latitude: Optional[float] = None
        self._longitude: Optional[float] = None
        self._city_name: str = ""
        self._temperature_unit: str = "celsius"
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
                "[weather] Missing required config fields: %s",
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

        # Initialize paging (4 pages: current, tomorrow, 3-day, 7-day)
        self._init_paging(
            total_pages=4,
            page_duration_seconds=page_duration,
            frame_delay_ms=100,
        )

        self._initialized = True

        # Attempt to fetch weather data if cache is stale or empty
        await self._refresh_cache_if_needed()

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next weather frame with staleness indicator."""
        if not self._initialized or self._cache is None:
            return None

        # Get total frame index before PagedPlugin advances it
        total_idx = self._total_frame_index()

        frame = await super().render_frame(width, height)
        if frame is None:
            return None

        # Add staleness indicator if cache is stale
        if self.is_cache_stale():
            draw_staleness_indicator(frame, total_idx, self._frame_delay_ms)

        return frame

    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a specific weather page."""
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

    async def cleanup(self) -> None:
        """Release resources."""
        await super().cleanup()

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
            logger.warning("[weather] Failed to fetch weather data: %s", e)
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
        params: dict[str, str] = {
            "latitude": str(self._latitude),
            "longitude": str(self._longitude),
            "current_weather": "true",
            "daily": "temperature_2m_max,temperature_2m_min,weathercode",
            "forecast_days": "8",
            "timezone": "auto",
        }

        if self._temperature_unit == "fahrenheit":
            params["temperature_unit"] = "fahrenheit"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    OPEN_METEO_API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "[weather] Open-Meteo API returned status %d",
                            response.status,
                        )
                        return None

                    data = await response.json()
                    return self._parse_api_response(data)

        except aiohttp.ClientError as e:
            logger.warning("[weather] Open-Meteo API request failed: %s", e)
            return None
        except Exception as e:
            logger.warning("[weather] Unexpected error fetching weather: %s", e)
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
                        condition_code=(
                            weather_codes[i] if i < len(weather_codes) else 0
                        ),
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

        # Draw 3x3 degree symbol (hollow square) — fixed size, looks good at any scale
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

        Layout scales proportionally for both SD (128x32) and HD (256x64).

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None
        cache = self._cache

        # Scale factor relative to standard 128x32
        sx = width / 128
        sy = height / 32

        # Draw weather icon vertically centered left
        is_hd = width >= 256 and height >= 64
        icon_img = get_weather_icon_image(cache.current_condition_code, hd=is_hd)
        frame.paste(icon_img, (int(2 * sx), int(3 * sy)))

        # Text X offset after icon
        text_x = int(22 * sx)

        # Temperature with degree symbol (MENU font)
        temp_frame = self._render_temp_with_degree(
            cache.current_temp, x=text_x, y=0, color=(255, 128, 0)
        )
        frame = self._helpers.composite_frames(frame, temp_frame)

        # Condition description (SYSTEM font)
        desc = cache.current_description[:12].upper()
        desc_frame = self._helpers.render_text(
            desc, x=text_x, y=int(13 * sy), color=(200, 200, 200), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, desc_frame)

        # City name bottom left (SYSTEM font)
        city = cache.city_name.upper()
        city_frame = self._helpers.render_text(
            city, x=text_x, y=int(24 * sy), color=(128, 128, 255), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, city_frame)

        return frame

    def _render_tomorrow_page(self, width: int, height: int) -> Image.Image:
        """Render page 1: Tomorrow (Layout 2C - two column).

        Layout scales proportionally for both SD (128x32) and HD (256x64).

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None
        cache = self._cache

        # Scale factor relative to standard 128x32
        sx = width / 128
        sy = height / 32

        # Draw "DEMAIN" / "TOMORROW" label at top (MENU font)
        labels = _LABELS.get(self._language, _LABELS["en"])
        label_frame = self._helpers.render_text(
            labels["tomorrow"],
            x=int(2 * sx),
            y=0,
            color=(255, 200, 0),
            font_name="MENU",
        )
        frame = self._helpers.composite_frames(frame, label_frame)

        # Draw weather icon
        is_hd = width >= 256 and height >= 64
        icon_img = get_weather_icon_image(cache.tomorrow_condition_code, hd=is_hd)
        frame.paste(icon_img, (int(2 * sx), int(14 * sy)))

        text_x = int(21 * sx)

        # High temperature with degree (MENU font)
        high_frame = self._render_temp_with_degree(
            cache.tomorrow_high, x=text_x, y=int(13 * sy), color=(255, 100, 50)
        )
        frame = self._helpers.composite_frames(frame, high_frame)

        # Low temperature with degree (SYSTEM font)
        low_frame = self._render_temp_with_degree(
            cache.tomorrow_low,
            x=text_x,
            y=int(25 * sy),
            color=(100, 150, 255),
            font_name="SYSTEM",
        )
        frame = self._helpers.composite_frames(frame, low_frame)

        # Right column: condition description (SYSTEM font, truncated to fit)
        desc = self._get_condition_description(cache.tomorrow_condition_code).upper()
        desc_width = self._helpers.get_text_width(desc, font_name="SYSTEM")
        desc_x = max(int(60 * sx), width - desc_width - int(2 * sx))
        desc_frame = self._helpers.render_text(
            desc, x=desc_x, y=int(14 * sy), color=(200, 200, 200), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, desc_frame)

        return frame

    def _render_outlook_page(self, width: int, height: int) -> Image.Image:
        """Render page 2: 3-day outlook (Layout 3B + separators).

        Layout scales proportionally for SD and HD:
        - 3 columns with vertical separators
        - Day name (yellow, SYSTEM) on top
        - Icon (scaled) in middle
        - Temperature (SYSTEM) at bottom

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None
        cache = self._cache

        # Scale factor
        sx = width / 128
        sy = height / 32

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

            # Icon in middle (scaled for HD)
            is_hd = width >= 256 and height >= 64
            icon_data = get_weather_icon_image(day.condition_code, hd=is_hd)
            icon_size = icon_data.size[0]  # Already correct size (16 or 32)
            icon_x = col_x + (col_width - icon_size) // 2
            icon_y = int(8 * sy)
            frame.paste(icon_data, (icon_x, icon_y))

            # Temperature at bottom (SYSTEM font) with degree symbol
            high_str = self._format_temp(day.high)
            temp_width = self._helpers.get_text_width(high_str, font_name="SYSTEM")
            temp_x = col_x + (col_width - temp_width) // 2
            temp_y = int(25 * sy)
            temp_frame = self._render_temp_with_degree(
                day.high, x=temp_x, y=temp_y, color=(255, 128, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, temp_frame)

        # Draw vertical separators between columns
        pixels = frame.load()
        assert pixels is not None
        for sep in range(1, num_days):
            sep_x = sep * col_width
            for y in range(0, height):
                pixels[sep_x, y] = (30, 30, 50)

        return frame

    def _render_7day_page(self, width: int, height: int) -> Image.Image:
        """Render page 3: 7-day overview (Layout D4).

        Layout scales proportionally:
        - 7 columns
        - Single-letter day name (SYSTEM) at top
        - Icon (scaled) centered in middle
        - Temperature (SYSTEM) at bottom

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None
        cache = self._cache

        sx = width / 128
        sy = height / 32

        num_days = min(7, len(cache.forecast_days))
        if num_days == 0:
            return frame

        col_width = width // 7
        day_letters = _DAY_LETTERS.get(self._language, _DAY_LETTERS["en"])
        today = datetime.now()

        icon_size = int(12 * min(sx, sy))
        is_hd = width >= 256 and height >= 64

        for i in range(num_days):
            day = cache.forecast_days[i]
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

            # Icon centered (HD-native when available)
            icon = get_weather_icon_image(day.condition_code, hd=is_hd)
            icon_small = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            ix = col_x + (col_width - icon_size) // 2
            iy = int(9 * sy)
            frame.paste(icon_small, (ix, iy))

            # Temperature at bottom (SYSTEM font)
            temp_str = str(round(day.high))
            tw = self._helpers.get_text_width(temp_str, font_name="SYSTEM")
            tx = col_x + (col_width - tw) // 2
            ty = int(23 * sy)
            temp_frame = self._helpers.render_text(
                temp_str, x=tx, y=ty, color=(255, 128, 0), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, temp_frame)

        return frame
