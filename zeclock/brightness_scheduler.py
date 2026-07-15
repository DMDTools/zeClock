"""Brightness scheduling for zeClock.

Supports:
- Day-of-week time ranges with brightness percentages
- Sunrise/sunset-based automatic brightness adjustment
- Software dimming for ultra-low brightness (below HW minimum)
- "Time only" mode that disables plugins during configured hours

Brightness percentage mapping (user-facing 0-100%):
- 100% = max_hw_brightness (configurable, default 7), no SW dimming
- ~7%  = HW 1, no SW dimming
- 2-7% = HW 1, progressive SW dimming
- 0%   = screen off (all black)

The scheduler checks once per minute and caches the result.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

import aiohttp

logger = logging.getLogger(__name__)

# Sunrise/sunset cache duration (30 minutes)
_SUN_CACHE_SECONDS = 30 * 60

# Days of the week (lowercase)
DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


@dataclass
class TimeRange:
    """A time range with an associated brightness percentage."""

    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int
    brightness_percent: int

    def contains(self, hour: int, minute: int) -> bool:
        """Check if a given time falls within this range.

        Handles overnight ranges (e.g., 22:00-08:00).
        """
        start = self.start_hour * 60 + self.start_minute
        end = self.end_hour * 60 + self.end_minute
        current = hour * 60 + minute

        if start <= end:
            # Normal range (e.g., 08:00-16:00)
            return start <= current < end
        else:
            # Overnight range (e.g., 22:00-08:00)
            return current >= start or current < end


@dataclass
class BrightnessResult:
    """Result of a brightness calculation."""

    hw_brightness: int  # Hardware brightness 0-15
    sw_dimming_percent: int  # Software dimming 0-100 (0 = no dimming)
    is_screen_off: bool  # True if brightness is 0% (all black)
    is_time_only: bool  # True if in "time only" mode (no plugins)


@dataclass
class SunData:
    """Cached sunrise/sunset data."""

    sunrise_hour: int
    sunrise_minute: int
    sunset_hour: int
    sunset_minute: int
    fetched_at: float = 0.0


class BrightnessScheduler:
    """Manages brightness scheduling based on time, day, and sunrise/sunset.

    Configuration is loaded from the [brightness_schedule] and [location]
    sections of zeclock.ini.
    """

    def __init__(
        self,
        max_brightness: int = 7,
        schedule: Optional[Dict[str, List[TimeRange]]] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        sunrise_brightness: Optional[int] = None,
        sunset_brightness: Optional[int] = None,
        time_only: Optional[str] = None,
    ):
        """Initialize the brightness scheduler.

        Args:
            max_brightness: Maximum HW brightness for 100% (0-15, default 7).
            schedule: Dict mapping day names / "default" to list of TimeRange.
            latitude: Location latitude for sunrise/sunset.
            longitude: Location longitude for sunrise/sunset.
            sunrise_brightness: Brightness % to use at sunrise (ramp up).
            sunset_brightness: Brightness % to use at sunset (ramp down).
            time_only: Time range "HH:MM-HH:MM" for time-only mode.
        """
        self._max_brightness = max(1, min(15, max_brightness))
        self._schedule = schedule or {}
        self._latitude = latitude
        self._longitude = longitude
        self._sunrise_brightness = sunrise_brightness
        self._sunset_brightness = sunset_brightness
        self._time_only_start, self._time_only_end = _parse_time_range_str(time_only)

        # Cached state
        self._sun_data: Optional[SunData] = None
        self._last_check_minute: int = -1
        self._cached_result: Optional[BrightnessResult] = None

    @property
    def has_schedule(self) -> bool:
        """Whether any schedule rules are configured."""
        return bool(self._schedule) or self._has_sun_config

    @property
    def _has_sun_config(self) -> bool:
        """Whether sunrise/sunset config is available."""
        return (
            self._latitude is not None
            and self._longitude is not None
            and (
                self._sunrise_brightness is not None
                or self._sunset_brightness is not None
            )
        )

    def get_brightness(self, now: Optional[datetime] = None) -> BrightnessResult:
        """Get the current brightness based on schedule and time.

        Checks once per minute and caches the result.

        Args:
            now: Override current time (for testing). Uses system time if None.

        Returns:
            BrightnessResult with HW brightness, SW dimming, and mode flags.
        """
        if now is None:
            now = datetime.now()

        current_minute = now.hour * 60 + now.minute
        if (
            current_minute == self._last_check_minute
            and self._cached_result is not None
        ):
            return self._cached_result

        self._last_check_minute = current_minute
        result = self._compute_brightness(now)
        self._cached_result = result
        return result

    def _compute_brightness(self, now: datetime) -> BrightnessResult:
        """Compute brightness for the given time."""
        hour = now.hour
        minute = now.minute
        day_name = DAYS_OF_WEEK[now.weekday()]

        # Determine brightness percentage from schedule
        brightness_percent: Optional[int] = None

        # Check day-specific schedule first
        if day_name in self._schedule:
            for time_range in self._schedule[day_name]:
                if time_range.contains(hour, minute):
                    brightness_percent = time_range.brightness_percent
                    break

        # Fall back to "default" schedule
        if brightness_percent is None and "default" in self._schedule:
            for time_range in self._schedule["default"]:
                if time_range.contains(hour, minute):
                    brightness_percent = time_range.brightness_percent
                    break

        # Fall back to sunrise/sunset if configured and no schedule matched
        if brightness_percent is None and self._has_sun_config and self._sun_data:
            brightness_percent = self._compute_sun_brightness(hour, minute)

        # If still no match, use 100%
        if brightness_percent is None:
            brightness_percent = 100

        # Clamp
        brightness_percent = max(0, min(100, brightness_percent))

        # Determine time-only mode
        is_time_only = self._is_in_time_range(
            hour, minute, self._time_only_start, self._time_only_end
        )

        # Convert percentage to HW brightness + SW dimming
        hw_brightness, sw_dimming = self._percent_to_hw_sw(brightness_percent)

        return BrightnessResult(
            hw_brightness=hw_brightness,
            sw_dimming_percent=sw_dimming,
            is_screen_off=(brightness_percent == 0),
            is_time_only=is_time_only,
        )

    def _percent_to_hw_sw(self, percent: int) -> Tuple[int, int]:
        """Convert a brightness percentage to HW brightness + SW dimming.

        Mapping:
        - 0% = HW 0, SW 0 (screen off — send black frame)
        - 1% = HW 1, SW 70% (minimum visible from testing)
        - 2-6% = HW 1, SW dimming linearly from 70% to 0%
        - 7-100% = HW 1-max_brightness, SW 0%

        Args:
            percent: Brightness percentage 0-100.

        Returns:
            Tuple of (hw_brightness 0-15, sw_dimming_percent 0-100).
        """
        if percent <= 0:
            return (0, 0)

        # Threshold where HW brightness = 1 with no SW dimming
        # This is approximately (1 / max_brightness) * 100
        hw1_threshold = max(1, int(100 / self._max_brightness))

        if percent < hw1_threshold:
            # Ultra-low brightness: HW 1 + SW dimming
            # Map percent 1..(hw1_threshold-1) to SW dimming 70%..0%
            # At percent=1: SW dimming = 70%
            # At percent=(hw1_threshold-1): SW dimming = 0%
            range_size = hw1_threshold - 1
            if range_size <= 0:
                return (1, 0)
            # Linear interpolation: higher percent = less dimming
            progress = (percent - 1) / range_size  # 0.0 to 1.0
            sw_dimming = int(70 * (1.0 - progress))
            return (1, sw_dimming)
        else:
            # Normal range: map percent to HW brightness 1..max_brightness
            # percent=hw1_threshold -> HW 1
            # percent=100 -> HW max_brightness
            range_size = 100 - hw1_threshold
            if range_size <= 0:
                return (self._max_brightness, 0)
            progress = (percent - hw1_threshold) / range_size  # 0.0 to 1.0
            hw = 1 + int(progress * (self._max_brightness - 1))
            hw = max(1, min(self._max_brightness, hw))
            return (hw, 0)

    def _compute_sun_brightness(self, hour: int, minute: int) -> Optional[int]:
        """Compute brightness based on sunrise/sunset times.

        Simple model:
        - Before sunrise: sunset_brightness (night)
        - After sunrise: sunrise_brightness (day)
        - After sunset: sunset_brightness (night)

        Args:
            hour: Current hour.
            minute: Current minute.

        Returns:
            Brightness percentage, or None if sun data unavailable.
        """
        if not self._sun_data:
            return None

        current = hour * 60 + minute
        sunrise = self._sun_data.sunrise_hour * 60 + self._sun_data.sunrise_minute
        sunset = self._sun_data.sunset_hour * 60 + self._sun_data.sunset_minute

        if current < sunrise:
            # Before sunrise — night brightness
            return self._sunset_brightness
        elif current < sunset:
            # Daytime — day brightness
            return self._sunrise_brightness
        else:
            # After sunset — night brightness
            return self._sunset_brightness

    async def update_sun_data(self) -> None:
        """Fetch sunrise/sunset times from the sunrise-sunset.org API.

        Caches the result for 30 minutes. Uses the free API at
        https://api.sunrise-sunset.org/json which requires no API key.
        """
        if self._latitude is None or self._longitude is None:
            return

        # Check cache
        if (
            self._sun_data
            and (time.time() - self._sun_data.fetched_at) < _SUN_CACHE_SECONDS
        ):
            return

        url = (
            f"https://api.sunrise-sunset.org/json"
            f"?lat={self._latitude}&lng={self._longitude}&formatted=0"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Sunrise/sunset API returned status %d", resp.status
                        )
                        return
                    data = await resp.json()

            if data.get("status") != "OK":
                logger.warning("Sunrise/sunset API error: %s", data.get("status"))
                return

            results = data["results"]
            # Parse ISO 8601 timestamps (UTC) and convert to local time
            sunrise_utc = datetime.fromisoformat(
                results["sunrise"].replace("Z", "+00:00")
            )
            sunset_utc = datetime.fromisoformat(
                results["sunset"].replace("Z", "+00:00")
            )

            # Convert to local time
            sunrise_local = sunrise_utc.astimezone()
            sunset_local = sunset_utc.astimezone()

            self._sun_data = SunData(
                sunrise_hour=sunrise_local.hour,
                sunrise_minute=sunrise_local.minute,
                sunset_hour=sunset_local.hour,
                sunset_minute=sunset_local.minute,
                fetched_at=time.time(),
            )
            # Invalidate brightness cache so next get_brightness() recomputes
            # using the fresh sun data
            self._last_check_minute = -1
            self._cached_result = None
            logger.info(
                "Sunrise/sunset updated: sunrise=%02d:%02d, sunset=%02d:%02d",
                self._sun_data.sunrise_hour,
                self._sun_data.sunrise_minute,
                self._sun_data.sunset_hour,
                self._sun_data.sunset_minute,
            )

        except Exception as e:
            logger.warning("Failed to fetch sunrise/sunset data: %s", e)

    @staticmethod
    def _is_in_time_range(
        hour: int,
        minute: int,
        start: Optional[Tuple[int, int]],
        end: Optional[Tuple[int, int]],
    ) -> bool:
        """Check if current time is within a start-end range.

        Handles overnight ranges (start > end).
        """
        if start is None or end is None:
            return False

        current = hour * 60 + minute
        start_min = start[0] * 60 + start[1]
        end_min = end[0] * 60 + end[1]

        if start_min <= end_min:
            return start_min <= current < end_min
        else:
            # Overnight range
            return current >= start_min or current < end_min


def _parse_time_str(time_str: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse a time string "HH:MM" into (hour, minute) tuple.

    Returns None if the string is None or invalid.
    """
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            return None
        hour = int(parts[0])
        minute = int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return (hour, minute)
        return None
    except (ValueError, IndexError):
        return None


def _parse_time_range_str(
    range_str: Optional[str],
) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """Parse a time range string "HH:MM-HH:MM" into (start, end) tuples.

    Returns (None, None) if the string is None or invalid.
    """
    if not range_str:
        return (None, None)
    try:
        parts = range_str.strip().split("-")
        if len(parts) != 2:
            return (None, None)
        start = _parse_time_str(parts[0])
        end = _parse_time_str(parts[1])
        if start is None or end is None:
            return (None, None)
        return (start, end)
    except (ValueError, IndexError):
        return (None, None)


def parse_schedule_line(line: str) -> List[TimeRange]:
    """Parse a schedule line into a list of TimeRange objects.

    Format: "HH:MM-HH:MM brightness%, HH:MM-HH:MM brightness%, ..."

    Args:
        line: Schedule line string.

    Returns:
        List of TimeRange objects parsed from the line.
    """
    ranges = []
    parts = [p.strip() for p in line.split(",")]

    for part in parts:
        if not part:
            continue
        try:
            # Split "HH:MM-HH:MM brightness%"
            tokens = part.split()
            if len(tokens) != 2:
                logger.warning(
                    "Invalid schedule entry (expected 'HH:MM-HH:MM N%%'): %s", part
                )
                continue

            time_part = tokens[0]
            brightness_part = tokens[1]

            # Parse time range
            time_tokens = time_part.split("-")
            if len(time_tokens) != 2:
                logger.warning("Invalid time range: %s", time_part)
                continue

            start_parts = time_tokens[0].split(":")
            end_parts = time_tokens[1].split(":")
            if len(start_parts) != 2 or len(end_parts) != 2:
                logger.warning("Invalid time format: %s", time_part)
                continue

            start_h, start_m = int(start_parts[0]), int(start_parts[1])
            end_h, end_m = int(end_parts[0]), int(end_parts[1])

            # Parse brightness percentage
            brightness_str = brightness_part.rstrip("%")
            brightness = int(brightness_str)

            ranges.append(
                TimeRange(
                    start_hour=start_h,
                    start_minute=start_m,
                    end_hour=end_h,
                    end_minute=end_m,
                    brightness_percent=max(0, min(100, brightness)),
                )
            )

        except (ValueError, IndexError) as e:
            logger.warning("Failed to parse schedule entry '%s': %s", part, e)
            continue

    return ranges


def parse_schedule_config(config_dict: Dict[str, str]) -> Dict[str, List[TimeRange]]:
    """Parse the full [brightness_schedule] config section.

    Args:
        config_dict: Dict of key=value pairs from the INI section.
            Keys are day names or "default".
            Values are schedule line strings.

    Returns:
        Dict mapping day names / "default" to lists of TimeRange.
    """
    schedule: Dict[str, List[TimeRange]] = {}

    for key, value in config_dict.items():
        key_lower = key.lower().strip()
        if key_lower in DAYS_OF_WEEK or key_lower == "default":
            ranges = parse_schedule_line(value)
            if ranges:
                schedule[key_lower] = ranges
        else:
            logger.warning(
                "Unknown schedule key '%s' (expected day name or 'default')", key
            )

    return schedule


def apply_sw_dimming(image: "Image.Image", dim_percent: int) -> "Image.Image":
    """Apply software dimming to an RGB image.

    Uses Pillow's point() with a LUT for fast C-native processing.

    Args:
        image: RGB PIL Image.
        dim_percent: Dimming level 0-100. 0 = no dimming, 100 = black.

    Returns:
        Dimmed RGB PIL Image.
    """
    from PIL import Image as PILImage

    if dim_percent <= 0:
        return image
    if dim_percent >= 100:
        return PILImage.new("RGB", image.size, (0, 0, 0))

    # Build LUT: scale all channel values by the factor
    factor = (100 - dim_percent) / 100.0
    lut = [int(i * factor) for i in range(256)] * 3  # R, G, B channels
    return image.point(lut)
