"""Tests for weather plugin error handling and configuration (task 9.3).

Tests cover:
- Staleness indicator blinking when cache is stale
- Signal completion when no cache and API unreachable
- Config field reading (latitude, longitude, city_name)
- Signal completion when required config fields missing
- Temperature unit config support (celsius/fahrenheit)

Requirements: 6.6, 6.7, 6.9, 6.11, 6.12
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from PIL import Image

from zeclock.plugins.weather_plugin import (
    CACHE_DURATION_SECONDS,
    WeatherData,
    WeatherPlugin,
)


@pytest.fixture
def weather_plugin():
    """Create a fresh WeatherPlugin instance."""
    return WeatherPlugin()


def make_weather_data(fetched_at: float = None, city_name: str = "Paris"):
    """Create a WeatherData instance for testing."""
    if fetched_at is None:
        fetched_at = time.time()
    return WeatherData(
        current_temp=22.5,
        current_condition_code=0,
        current_description="Clear",
        tomorrow_high=25.0,
        tomorrow_low=18.0,
        tomorrow_condition_code=1,
        forecast_days=[],
        fetched_at=fetched_at,
        city_name=city_name,
    )


class TestStalenessIndicator:
    """Tests for the blinking staleness indicator (Requirement 6.6)."""

    @pytest.mark.asyncio
    async def test_staleness_indicator_shown_when_cache_stale(self, weather_plugin):
        """When cache is stale, frames should contain red pixels (staleness dot)."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
            "temperature_unit": "celsius",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Set stale cache (older than 15 minutes)
        weather_plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )

        # Render a frame - the staleness indicator should be present on some frames
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is not None

        # Check that the frame has red pixels in the top-right corner area
        # The dot is at (width-5, 2) with 3x3 size
        pixels = frame.load()
        # On the first frame (frame_count=0), blink_cycle=0, dot should be visible
        dot_x = 128 - 5
        dot_y = 2
        assert pixels[dot_x, dot_y] == (255, 0, 0), (
            "Staleness indicator dot should be visible on first frame"
        )

    @pytest.mark.asyncio
    async def test_staleness_indicator_blinks(self, weather_plugin):
        """The staleness indicator should toggle visibility (blink)."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
            "temperature_unit": "celsius",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Set stale cache
        weather_plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )

        # With frame_delay_ms=100, blink_interval_frames = 500 // 100 = 5
        # So the dot should be visible for frames 0-4, hidden for frames 5-9, etc.
        dot_x = 128 - 5
        dot_y = 2

        visible_frames = []
        hidden_frames = []

        # Render enough frames to see at least one full blink cycle
        for i in range(12):
            frame = await weather_plugin.render_frame(128, 32)
            if frame is None:
                break
            pixels = frame.load()
            if pixels[dot_x, dot_y] == (255, 0, 0):
                visible_frames.append(i)
            else:
                hidden_frames.append(i)

        # Both visible and hidden frames should exist (blinking)
        assert len(visible_frames) > 0, "Dot should be visible on some frames"
        assert len(hidden_frames) > 0, "Dot should be hidden on some frames (blinking)"

    @pytest.mark.asyncio
    async def test_no_staleness_indicator_when_cache_fresh(self, weather_plugin):
        """When cache is fresh, no staleness indicator should be drawn."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
            "temperature_unit": "celsius",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Set fresh cache (just fetched)
        weather_plugin._cache = make_weather_data(fetched_at=time.time())

        frame = await weather_plugin.render_frame(128, 32)
        assert frame is not None

        # Check that there are no red pixels in the dot area
        pixels = frame.load()
        dot_x = 128 - 5
        dot_y = 2
        assert pixels[dot_x, dot_y] != (255, 0, 0), (
            "No staleness indicator should be shown when cache is fresh"
        )


class TestSignalCompletionNoCache:
    """Tests for signaling completion when no cache and API unreachable (Requirement 6.7)."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_cache(self, weather_plugin):
        """Plugin should return None immediately if no cache is available."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Ensure no cache
        weather_plugin._cache = None

        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None, "Should signal completion when no cache available"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_initialized(self, weather_plugin):
        """Plugin should return None if not properly initialized."""
        # Don't initialize - _initialized remains False
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None


class TestConfigReading:
    """Tests for reading config fields (Requirements 6.9, 6.11, 6.12)."""

    @pytest.mark.asyncio
    async def test_reads_latitude_longitude_city_name(self, weather_plugin):
        """Plugin should read latitude, longitude, city_name from config."""
        config = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "city_name": "New York",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._latitude == 40.7128
        assert weather_plugin._longitude == -74.0060
        assert weather_plugin._city_name == "New York"
        assert weather_plugin._initialized is True

    @pytest.mark.asyncio
    async def test_signal_completion_missing_latitude(self, weather_plugin):
        """Plugin should not initialize if latitude is missing."""
        config = {
            "longitude": 2.3522,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._initialized is False
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None

    @pytest.mark.asyncio
    async def test_signal_completion_missing_longitude(self, weather_plugin):
        """Plugin should not initialize if longitude is missing."""
        config = {
            "latitude": 48.8566,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._initialized is False
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None

    @pytest.mark.asyncio
    async def test_signal_completion_missing_city_name(self, weather_plugin):
        """Plugin should not initialize if city_name is missing."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._initialized is False
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None

    @pytest.mark.asyncio
    async def test_signal_completion_empty_city_name(self, weather_plugin):
        """Plugin should not initialize if city_name is empty string."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._initialized is False

    @pytest.mark.asyncio
    async def test_signal_completion_all_fields_missing(self, weather_plugin):
        """Plugin should not initialize if all required fields are missing."""
        config = {}

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._initialized is False
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None

    @pytest.mark.asyncio
    async def test_logs_warning_for_missing_fields(self, weather_plugin, caplog):
        """Plugin should log a warning identifying missing config fields."""
        import logging

        config = {
            "latitude": 48.8566,
            # longitude and city_name missing
        }

        with caplog.at_level(logging.WARNING):
            with patch.object(
                weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
            ):
                await weather_plugin.initialize(config)

        assert "longitude" in caplog.text
        assert "city_name" in caplog.text


class TestTemperatureUnitConfig:
    """Tests for temperature_unit configuration (Requirement 6.11)."""

    @pytest.mark.asyncio
    async def test_default_temperature_unit_celsius(self, weather_plugin):
        """Default temperature unit should be celsius."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._temperature_unit == "celsius"

    @pytest.mark.asyncio
    async def test_temperature_unit_fahrenheit(self, weather_plugin):
        """Plugin should accept fahrenheit as temperature unit."""
        config = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "city_name": "New York",
            "temperature_unit": "fahrenheit",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._temperature_unit == "fahrenheit"

    @pytest.mark.asyncio
    async def test_temperature_unit_celsius_explicit(self, weather_plugin):
        """Plugin should accept explicit celsius setting."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
            "temperature_unit": "celsius",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._temperature_unit == "celsius"

    @pytest.mark.asyncio
    async def test_invalid_temperature_unit_defaults_to_celsius(self, weather_plugin):
        """Invalid temperature unit should default to celsius."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
            "temperature_unit": "kelvin",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        assert weather_plugin._temperature_unit == "celsius"

    @pytest.mark.asyncio
    async def test_fahrenheit_passed_to_api(self, weather_plugin):
        """When fahrenheit is configured, it should be passed to the API params."""
        config = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "city_name": "New York",
            "temperature_unit": "fahrenheit",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Verify the unit is stored correctly for API calls
        assert weather_plugin._temperature_unit == "fahrenheit"
        assert weather_plugin._initialized is True


class TestCachedDataWithStaleness:
    """Tests for displaying cached data when API is unreachable (Requirement 6.6)."""

    @pytest.mark.asyncio
    async def test_displays_cached_data_when_stale(self, weather_plugin):
        """Plugin should still render frames using stale cached data."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Set stale cache
        weather_plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )

        # Should still render frames (not return None)
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is not None
        assert isinstance(frame, Image.Image)
        assert frame.size == (128, 32)
        assert frame.mode == "RGB"

    @pytest.mark.asyncio
    async def test_staleness_indicator_distinguishable(self, weather_plugin):
        """Staleness indicator should be distinguishable from normal content."""
        config = {
            "latitude": 48.8566,
            "longitude": 2.3522,
            "city_name": "Paris",
        }

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Set stale cache
        weather_plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )

        frame = await weather_plugin.render_frame(128, 32)
        assert frame is not None

        # The staleness indicator is a red dot - red is distinct from
        # the typical orange/white weather display colors
        pixels = frame.load()
        dot_x = 128 - 5
        dot_y = 2
        # Red dot should be pure red (255, 0, 0)
        assert pixels[dot_x, dot_y] == (255, 0, 0)
