"""ParaglidingPlugin - Paragliding flyability forecast from Paraglidable API.

Displays AI-based paragliding forecasts from paraglidable.com:
- Today's flyability percentage with color-coded indicator
- XC (cross-country) probability
- Multi-day forecast overview (up to 7 days)
- Per-spot breakdown when multiple spots are configured

Data is cached for 30 minutes to respect API rate limits.
"""

import logging
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from PIL import Image, ImageDraw

from .base import ConfigField, PagedPlugin, PluginNotConfiguredError
from .helpers import draw_staleness_indicator

logger = logging.getLogger(__name__)

# Cache duration in seconds (30 minutes)
CACHE_DURATION_SECONDS = 30 * 60

# Paraglidable API base URL
PARAGLIDABLE_API_URL = "https://api.paraglidable.com/"

# Color thresholds for flyability percentage
# Green: >= 70%, Yellow/Orange: 40-69%, Red: < 40%
COLOR_GREEN = (0, 255, 80)
COLOR_YELLOW = (255, 200, 0)
COLOR_ORANGE = (255, 128, 0)
COLOR_RED = (255, 30, 30)
COLOR_CYAN = (0, 200, 255)
COLOR_WHITE = (200, 200, 200)
COLOR_DIM = (80, 80, 80)

# Short day names for forecast pages
_DAY_NAMES_SHORT = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
}


def flyability_color(value: float) -> Tuple[int, int, int]:
    """Return color based on percentage (0.0-1.0).

    >= 80%: green, >= 60%: orange, < 60%: red.

    Args:
        value: Probability between 0.0 and 1.0.

    Returns:
        RGB color tuple.
    """
    if value >= 0.80:
        return COLOR_GREEN
    elif value >= 0.60:
        return COLOR_ORANGE
    else:
        return COLOR_RED


@dataclass
class SpotForecast:
    """Forecast data for a single spot on a single day."""

    name: str
    lat: float
    lon: float
    fly: float  # 0.0 to 1.0
    xc: float  # 0.0 to 1.0
    takeoff: float  # 0.0 to 1.0


@dataclass
class DayData:
    """All spot forecasts for a single day."""

    date: str  # "YYYY-MM-DD"
    spots: List[SpotForecast] = field(default_factory=list)

    @property
    def best_fly(self) -> float:
        """Return the highest flyability among all spots."""
        if not self.spots:
            return 0.0
        return max(s.fly for s in self.spots)

    @property
    def best_xc(self) -> float:
        """Return the highest XC probability among all spots."""
        if not self.spots:
            return 0.0
        return max(s.xc for s in self.spots)

    @property
    def avg_fly(self) -> float:
        """Return average flyability across all spots."""
        if not self.spots:
            return 0.0
        return sum(s.fly for s in self.spots) / len(self.spots)


@dataclass
class ParaglidableData:
    """Cached data from the Paraglidable API."""

    days: List[DayData] = field(default_factory=list)
    fetched_at: float = 0.0


class ParaglidingPlugin(PagedPlugin):
    """Paragliding flyability forecast plugin using Paraglidable API.

    Displays color-coded flyability and XC forecasts for configured spots.
    Pages:
      0 - Today: main flyability + XC for best spot
      1 - Spots: per-spot breakdown for today
      2 - Week: 7-day forecast overview
    """

    @property
    def name(self) -> str:
        return "paragliding"

    @property
    def description(self) -> str:
        return "Paragliding flyability forecast from Paraglidable"

    @property
    def config_schema(self) -> List[ConfigField]:
        """Declare configuration fields for the paragliding plugin."""
        return [
            ConfigField(
                "api_key",
                "API Key",
                "text",
                required=True,
                description="Paraglidable API key (free, get from paraglidable.com)",
            ),
        ]

    def __init__(self) -> None:
        """Initialize ParaglidingPlugin with default state."""
        super().__init__()
        self._cache: Optional[ParaglidableData] = None
        self._api_key: str = ""
        self._language: str = "en"
        self._spot_filter: Optional[List[str]] = None
        self._initialized: bool = False
        self._num_spots: int = 1

    async def initialize(self, config: dict) -> None:
        """Initialize the plugin with configuration.

        Config keys:
            api_key (str): Paraglidable API key (required)
            language (str): "en" or "fr" (default: "en")
            spots (str|list): Comma-separated spot names to filter, or list
            page_duration_seconds (int): Duration per page 2-30s (default: 5)

        Args:
            config: Plugin-specific settings from plugins.yaml.

        Raises:
            PluginNotConfiguredError: If API key is missing.
        """
        self._helpers = config.get("_helpers")

        # Read API key
        self._api_key = config.get("api_key", "")
        if not self._api_key:
            raise PluginNotConfiguredError(
                "Paragliding plugin requires an api_key from paraglidable.com"
            )

        # Language
        self._language = config.get("language", "en")
        if self._language not in ("en", "fr"):
            self._language = "en"

        # Spot filter (optional)
        spots_raw = config.get("spots")
        if isinstance(spots_raw, str) and spots_raw.strip():
            self._spot_filter = [s.strip() for s in spots_raw.split(",") if s.strip()]
        elif isinstance(spots_raw, list):
            self._spot_filter = [str(s).strip() for s in spots_raw if str(s).strip()]
        else:
            self._spot_filter = None

        page_duration = config.get("page_duration_seconds", 5)

        # Initialize paging: one page per spot (cycling through all spots)
        # We'll set total_pages after first fetch; default to 1 for now
        self._page_duration = page_duration
        self._init_paging(
            total_pages=1,
            page_duration_seconds=page_duration,
            frame_delay_ms=200,
        )

        self._initialized = True

        # Force cache invalidation on reconfigure
        self._cache = None

        # Fetch data
        await self._refresh_cache_if_needed()

        # Now that we have data, set correct page count
        # 2 pages per spot: today + 3-day forecast
        # (self._cache may be populated by _refresh_cache_if_needed)
        today = self._get_today()
        if today and today.spots:
            self._num_spots = len(today.spots)
            self._init_paging(
                total_pages=self._num_spots * 2,
                page_duration_seconds=self._page_duration,
                frame_delay_ms=200,
            )

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next paragliding frame with staleness indicator."""
        if not self._initialized:
            return None

        # If cache is empty, attempt to fetch
        if self._cache is None:
            await self._refresh_cache_if_needed()
            if self._cache is None:
                return self._render_loading_frame(width, height)

        # Get total frame index before PagedPlugin advances it
        total_idx = self._total_frame_index()

        frame = await super().render_frame(width, height)
        if frame is None:
            return None

        # Add staleness indicator if cache is stale
        if self._is_cache_stale():
            draw_staleness_indicator(frame, total_idx, self._frame_delay_ms)

        return frame

    def _render_loading_frame(self, width: int, height: int) -> Image.Image:
        """Render a loading placeholder."""
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))
        frame = self._helpers.create_frame()
        text_frame = self._helpers.render_text(
            "PARAGLIDING", centered=True, color=COLOR_CYAN, font_name="MENU"
        )
        return self._helpers.composite_frames(frame, text_frame)

    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a specific paragliding page.

        Pages alternate: even = today for spot N, odd = 3-day forecast for spot N.
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        spot_index = page // 2
        is_forecast = (page % 2) == 1

        if is_forecast:
            return self._render_spot_forecast_page(spot_index, width, height)
        else:
            return self._render_spot_page(spot_index, width, height)

    async def cleanup(self) -> None:
        """Release resources."""
        await super().cleanup()

    def _is_cache_stale(self) -> bool:
        """Check if the cached data is older than 30 minutes."""
        if self._cache is None:
            return True
        elapsed = time.time() - self._cache.fetched_at
        return elapsed >= CACHE_DURATION_SECONDS

    async def _refresh_cache_if_needed(self) -> None:
        """Fetch new data if cache is stale."""
        if not self._is_cache_stale():
            return

        try:
            data = await self._fetch_data()
            if data is not None:
                self._cache = data
        except Exception as e:
            logger.warning("[paragliding] Failed to fetch data: %s", e)

    async def _fetch_data(self) -> Optional[ParaglidableData]:
        """Fetch forecast data from Paraglidable API.

        Returns:
            ParaglidableData instance, or None on failure.
        """
        params: Dict[str, str] = {
            "key": self._api_key,
            "format": "JSON",
            "version": "1",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    PARAGLIDABLE_API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "[paragliding] API returned status %d", response.status
                        )
                        return None

                    data = await response.json()
                    return self._parse_response(data)

        except aiohttp.ClientError as e:
            logger.warning("[paragliding] API request failed: %s", e)
            return None
        except Exception as e:
            logger.warning("[paragliding] Unexpected error: %s", e)
            return None

    def _parse_response(self, data: Any) -> Optional[ParaglidableData]:
        """Parse the Paraglidable API JSON response.

        The API returns a dict keyed by date strings ("YYYY-MM-DD"),
        each containing a list of spot objects with forecast data.

        Args:
            data: Parsed JSON response.

        Returns:
            ParaglidableData instance, or None if malformed.
        """
        if not isinstance(data, dict):
            logger.warning("[paragliding] Unexpected response format")
            return None

        days: List[DayData] = []

        # Sort dates chronologically
        sorted_dates = sorted(data.keys())

        for date_str in sorted_dates:
            spots_raw = data[date_str]
            if not isinstance(spots_raw, list):
                continue

            day = DayData(date=date_str)

            for spot_raw in spots_raw:
                if not isinstance(spot_raw, dict):
                    continue

                forecast = spot_raw.get("forecast", {})
                spot = SpotForecast(
                    name=spot_raw.get("name", "Unknown"),
                    lat=spot_raw.get("lat", 0.0),
                    lon=spot_raw.get("lon", 0.0),
                    fly=forecast.get("fly", 0.0),
                    xc=forecast.get("XC", 0.0),
                    takeoff=forecast.get("takeoff", 0.0),
                )

                # Apply spot filter if configured
                if self._spot_filter:
                    if not any(
                        f.lower() in spot.name.lower() for f in self._spot_filter
                    ):
                        continue

                day.spots.append(spot)

            if day.spots:
                days.append(day)

        if not days:
            logger.warning("[paragliding] No forecast data found in response")
            return None

        return ParaglidableData(days=days, fetched_at=time.time())

    def _get_today(self) -> Optional[DayData]:
        """Get today's forecast data."""
        if not self._cache or not self._cache.days:
            return None
        today_str = datetime.now().strftime("%Y-%m-%d")
        for day in self._cache.days:
            if day.date == today_str:
                return day
        # Fallback: return first available day
        return self._cache.days[0] if self._cache.days else None

    def _render_spot_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render one spot page showing Fly, XC, and Takeoff percentages.

        Each page displays one spot with:
        - Spot name at top
        - FLY percentage (large, color-coded)
        - XC percentage (cyan)
        - Takeoff percentage (white)
        - Color bar on the left

        Args:
            page: Spot index (0-based).
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None

        today = self._get_today()
        if today is None or not today.spots:
            text_frame = self._helpers.render_text(
                "NO DATA", centered=True, color=COLOR_RED, font_name="MENU"
            )
            return self._helpers.composite_frames(frame, text_frame)

        # Get the spot for this page
        if page >= len(today.spots):
            return frame
        spot = today.spots[page]

        sx = width / 128
        sy = height / 32

        fly_pct = int(spot.fly * 100)
        xc_pct = int(spot.xc * 100)
        takeoff_pct = int(spot.takeoff * 100)
        fly_color = flyability_color(spot.fly)

        draw = ImageDraw.Draw(frame)

        # Draw flyability bar on the left (3px wide, proportional height)
        bar_width = max(3, int(3 * sx))
        bar_height = max(1, int(height * spot.fly))
        bar_y = height - bar_height
        draw.rectangle([0, bar_y, bar_width - 1, height - 1], fill=fly_color)

        text_x = int(6 * sx)

        # Spot name at top (SYSTEM font, dimmed yellow)
        spot_name = spot.name[:18].upper()
        name_frame = self._helpers.render_text(
            spot_name, x=text_x, y=0, color=COLOR_YELLOW, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, name_frame)

        # FLY percentage (MENU font, color-coded) — main metric
        fly_str = f"{fly_pct}%"
        fly_y = int(10 * sy)
        fly_frame = self._helpers.render_text(
            fly_str, x=text_x, y=fly_y, color=fly_color, font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, fly_frame)

        # "FLY" label next to the percentage
        fly_label_x = text_x + self._helpers.get_text_width(fly_str, "MENU") + int(3 * sx)
        label_frame = self._helpers.render_text(
            "FLY", x=fly_label_x, y=fly_y + int(2 * sy), color=COLOR_WHITE, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, label_frame)

        # XC and Takeoff on the bottom row (SYSTEM font) — color per value
        bottom_y = int(23 * sy)
        xc_str = f"XC:{xc_pct}%"
        xc_color = flyability_color(spot.xc)
        xc_frame = self._helpers.render_text(
            xc_str, x=text_x, y=bottom_y, color=xc_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, xc_frame)

        # Takeoff right-aligned on the same row
        to_str = f"TO:{takeoff_pct}%"
        to_color = flyability_color(spot.takeoff)
        to_frame = self._helpers.render_text_right_aligned(
            to_str, y=bottom_y, margin=int(2 * sx), color=to_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, to_frame)

        return frame

    def _render_spot_forecast_page(
        self, spot_index: int, width: int, height: int
    ) -> Image.Image:
        """Render 3-day forecast for a specific spot (excluding today).

        Layout (128x32):
          Row 0 (y=0):  Spot name (left, SYSTEM, yellow)
          Row 1 (y=8):  Day names centered in 3 columns (white)
          Row 2 (y=15): FLY values (color-coded)
          Row 3 (y=21): XC values (color-coded)
          Row 4 (y=27): TO values (color-coded)

        Args:
            spot_index: Index of the spot in today's spot list.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        assert self._helpers is not None
        frame = self._helpers.create_frame()
        assert self._cache is not None

        today = self._get_today()
        if today is None or spot_index >= len(today.spots):
            return frame

        spot_name = today.spots[spot_index].name

        # Find this spot's data for the next 3 days (skip today)
        today_str = datetime.now().strftime("%Y-%m-%d")
        future_days: List[DayData] = []
        for day in self._cache.days:
            if day.date > today_str:
                future_days.append(day)
            if len(future_days) >= 3:
                break

        if not future_days:
            text_frame = self._helpers.render_text(
                "NO FORECAST", centered=True, color=COLOR_DIM, font_name="SYSTEM"
            )
            return self._helpers.composite_frames(frame, text_frame)

        num_cols = len(future_days)
        # Reserve left margin for labels (FLY/XC/TO)
        label_width = self._helpers.get_text_width("FLY", font_name="SYSTEM") + 2
        data_x = label_width
        data_width = width - data_x
        col_width = data_width // num_cols
        day_names = _DAY_NAMES_SHORT.get(self._language, _DAY_NAMES_SHORT["en"])

        # Row layout for 32px height:
        #   y=0:  Day names (7px tall)
        #   y=8:  FLY values
        #   y=16: XC values
        #   y=24: TO values

        # Left-side labels (aligned with data rows)
        fly_label = self._helpers.render_text(
            "FLY", x=0, y=8, color=COLOR_DIM, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, fly_label)
        xc_label = self._helpers.render_text(
            "XC", x=0, y=16, color=COLOR_DIM, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, xc_label)
        to_label = self._helpers.render_text(
            "TO", x=0, y=24, color=COLOR_DIM, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, to_label)

        for i, day in enumerate(future_days):
            col_x = data_x + i * col_width
            center_x = col_x + col_width // 2

            # Find this spot in this day's data
            spot_data: Optional[SpotForecast] = None
            for s in day.spots:
                if s.name == spot_name:
                    spot_data = s
                    break

            if spot_data is None:
                continue

            # Day name (e.g. "Jeu")
            try:
                dt = datetime.strptime(day.date, "%Y-%m-%d")
                day_label = day_names[dt.weekday()]
            except (ValueError, IndexError):
                day_label = "?"

            lw = self._helpers.get_text_width(day_label, font_name="SYSTEM")
            lx = center_x - lw // 2
            day_frame = self._helpers.render_text(
                day_label, x=lx, y=0, color=COLOR_WHITE, font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, day_frame)

            # FLY
            fly_str = f"{int(spot_data.fly * 100)}%"
            fw = self._helpers.get_text_width(fly_str, font_name="SYSTEM")
            fly_frame = self._helpers.render_text(
                fly_str, x=center_x - fw // 2, y=8, color=flyability_color(spot_data.fly), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, fly_frame)

            # XC
            xc_str = f"{int(spot_data.xc * 100)}%"
            xw = self._helpers.get_text_width(xc_str, font_name="SYSTEM")
            xc_frame = self._helpers.render_text(
                xc_str, x=center_x - xw // 2, y=16, color=flyability_color(spot_data.xc), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, xc_frame)

            # TO
            to_str = f"{int(spot_data.takeoff * 100)}%"
            tw = self._helpers.get_text_width(to_str, font_name="SYSTEM")
            to_frame = self._helpers.render_text(
                to_str, x=center_x - tw // 2, y=24, color=flyability_color(spot_data.takeoff), font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, to_frame)

        # Vertical separators
        pixels = frame.load()
        assert pixels is not None
        for sep in range(1, num_cols):
            sep_x = data_x + sep * col_width
            for y in range(8, height):
                if 0 <= sep_x < width:
                    pixels[sep_x, y] = (30, 30, 50)

        return frame
