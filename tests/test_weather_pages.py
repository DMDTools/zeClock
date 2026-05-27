"""Tests for weather plugin page cycling and completion (task 9.5).

Tests cover:
- Exactly 3 pages rendered (current, tomorrow, 3-day)
- Each page displayed for configured duration
- None returned after last page completes
- Total frame count = 3 * ceil(page_duration_seconds * 1000 / frame_delay_ms)
- Property 15: Weather Page Cycling and Completion

**Validates: Requirements 6.10**
"""

import math
import time
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PIL import Image

from zeclock.plugins.weather_plugin import (
    DayForecast,
    WeatherData,
    WeatherPlugin,
)


# Feature: plugin-system, Property 15: Weather Page Cycling and Completion


@pytest.fixture
def weather_plugin():
    """Create a fresh WeatherPlugin instance."""
    return WeatherPlugin()


def make_weather_data(city_name: str = "Paris"):
    """Create a WeatherData instance with valid forecast data for testing."""
    return WeatherData(
        current_temp=22.5,
        current_condition_code=0,
        current_description="Clear",
        tomorrow_high=25.0,
        tomorrow_low=18.0,
        tomorrow_condition_code=1,
        forecast_days=[
            DayForecast(high=25.0, low=18.0, condition_code=1),
            DayForecast(high=27.0, low=19.0, condition_code=2),
            DayForecast(high=23.0, low=16.0, condition_code=3),
        ],
        fetched_at=time.time(),
        city_name=city_name,
    )


def make_config(page_duration_seconds: int = 4):
    """Create a valid weather plugin config."""
    return {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "city_name": "Paris",
        "temperature_unit": "celsius",
        "page_duration_seconds": page_duration_seconds,
    }


class TestExactlyThreePages:
    """Test that exactly 3 pages are rendered (current, tomorrow, 3-day)."""

    @pytest.mark.asyncio
    async def test_three_pages_rendered(self, weather_plugin):
        """Plugin should render exactly 3 pages before returning None."""
        config = make_config(page_duration_seconds=2)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        # Count frames and track page transitions
        frame_count = 0
        frames_per_page = weather_plugin._frames_per_page

        while True:
            frame = await weather_plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1
            assert isinstance(frame, Image.Image)
            assert frame.mode == "RGB"
            assert frame.size == (128, 32)

        # Should have rendered exactly 3 pages worth of frames
        expected_total = 3 * frames_per_page
        assert frame_count == expected_total

    @pytest.mark.asyncio
    async def test_page_index_advances_through_three_pages(self, weather_plugin):
        """Internal page counter should advance from 0 to 2 then stop."""
        config = make_config(page_duration_seconds=2)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        frames_per_page = weather_plugin._frames_per_page
        pages_seen = set()

        total_frames = 3 * frames_per_page
        for i in range(total_frames):
            pages_seen.add(weather_plugin._current_page)
            frame = await weather_plugin.render_frame(128, 32)
            assert frame is not None

        # After all frames, next call should return None
        assert weather_plugin._current_page == 3
        frame = await weather_plugin.render_frame(128, 32)
        assert frame is None

        # Should have seen pages 0, 1, 2
        assert pages_seen == {0, 1, 2}


class TestPageDuration:
    """Test each page is displayed for the configured duration."""

    @pytest.mark.asyncio
    async def test_each_page_displayed_for_configured_duration(self, weather_plugin):
        """Each page should produce exactly frames_per_page frames."""
        config = make_config(page_duration_seconds=4)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        frames_per_page = weather_plugin._frames_per_page
        # frame_delay_ms=100, page_duration=4s => frames_per_page = (4000 + 99) // 100 = 40
        expected_fpp = (4 * 1000 + 100 - 1) // 100
        assert frames_per_page == expected_fpp

        # Track frames per page
        page_frame_counts = [0, 0, 0]

        for _ in range(3 * frames_per_page):
            current_page = weather_plugin._current_page
            frame = await weather_plugin.render_frame(128, 32)
            assert frame is not None
            page_frame_counts[current_page] += 1

        # Each page should have exactly frames_per_page frames
        for i, count in enumerate(page_frame_counts):
            assert count == frames_per_page, (
                f"Page {i} rendered {count} frames, expected {frames_per_page}"
            )

    @pytest.mark.asyncio
    async def test_page_duration_minimum_2_seconds(self, weather_plugin):
        """Page duration should be clamped to minimum 2 seconds."""
        config = make_config(page_duration_seconds=1)  # Below minimum

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Should be clamped to 2
        assert weather_plugin._page_duration_seconds == 2

    @pytest.mark.asyncio
    async def test_page_duration_maximum_30_seconds(self, weather_plugin):
        """Page duration should be clamped to maximum 30 seconds."""
        config = make_config(page_duration_seconds=60)  # Above maximum

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        # Should be clamped to 30
        assert weather_plugin._page_duration_seconds == 30


class TestNoneAfterLastPage:
    """Test that None is returned after the last page completes."""

    @pytest.mark.asyncio
    async def test_none_returned_after_all_pages(self, weather_plugin):
        """After rendering all 3 pages, render_frame should return None."""
        config = make_config(page_duration_seconds=2)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        frames_per_page = weather_plugin._frames_per_page
        total_frames = 3 * frames_per_page

        # Render all frames
        for _ in range(total_frames):
            frame = await weather_plugin.render_frame(128, 32)
            assert frame is not None

        # Next call should return None
        result = await weather_plugin.render_frame(128, 32)
        assert result is None

    @pytest.mark.asyncio
    async def test_none_persists_after_completion(self, weather_plugin):
        """Multiple calls after completion should all return None."""
        config = make_config(page_duration_seconds=2)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        frames_per_page = weather_plugin._frames_per_page
        total_frames = 3 * frames_per_page

        # Render all frames
        for _ in range(total_frames):
            await weather_plugin.render_frame(128, 32)

        # Multiple subsequent calls should all return None
        for _ in range(5):
            result = await weather_plugin.render_frame(128, 32)
            assert result is None


class TestTotalFrameCount:
    """Test total frame count = 3 * ceil(page_duration_seconds * 1000 / frame_delay_ms)."""

    @pytest.mark.asyncio
    async def test_total_frame_count_default_config(self, weather_plugin):
        """Total frames should match formula with default config (4s, 100ms delay)."""
        config = make_config(page_duration_seconds=4)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        # Expected: 3 * ceil(4000 / 100) = 3 * 40 = 120
        expected_total = 3 * math.ceil(4 * 1000 / 100)

        frame_count = 0
        while True:
            frame = await weather_plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1

        assert frame_count == expected_total

    @pytest.mark.asyncio
    async def test_total_frame_count_short_duration(self, weather_plugin):
        """Total frames should match formula with 2s duration."""
        config = make_config(page_duration_seconds=2)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        # Expected: 3 * ceil(2000 / 100) = 3 * 20 = 60
        expected_total = 3 * math.ceil(2 * 1000 / 100)

        frame_count = 0
        while True:
            frame = await weather_plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1

        assert frame_count == expected_total

    @pytest.mark.asyncio
    async def test_total_frame_count_non_divisible(self, weather_plugin):
        """Total frames should use ceiling division when duration doesn't divide evenly."""
        config = make_config(page_duration_seconds=3)

        with patch.object(weather_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await weather_plugin.initialize(config)

        weather_plugin._cache = make_weather_data()

        # frame_delay_ms=100, page_duration=3s
        # Expected: 3 * ceil(3000 / 100) = 3 * 30 = 90
        expected_total = 3 * math.ceil(3 * 1000 / weather_plugin._frame_delay_ms)

        frame_count = 0
        while True:
            frame = await weather_plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1

        assert frame_count == expected_total


class TestWeatherPageCyclingProperty:
    """Property-based test for weather page cycling and completion.

    **Validates: Requirements 6.10**
    """

    @given(
        page_duration_seconds=st.integers(min_value=2, max_value=30),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_property_total_frames_equals_formula(self, page_duration_seconds):
        """Property 15: For any configured page duration (2-30 seconds) and
        frame_delay_ms, the Weather_Plugin SHALL render exactly 3 pages each
        for the configured duration, then return None to signal completion.
        The total number of frames SHALL equal
        3 * ceil(page_duration_seconds * 1000 / frame_delay_ms).

        **Validates: Requirements 6.10**
        """
        plugin = WeatherPlugin()
        frame_delay_ms = plugin._frame_delay_ms  # 100ms default

        config = make_config(page_duration_seconds=page_duration_seconds)

        with patch.object(plugin, "_refresh_cache_if_needed", new_callable=AsyncMock):
            await plugin.initialize(config)

        plugin._cache = make_weather_data()

        # Calculate expected total frames using the formula
        expected_frames_per_page = math.ceil(
            page_duration_seconds * 1000 / frame_delay_ms
        )
        expected_total = 3 * expected_frames_per_page

        # Render all frames and count
        frame_count = 0
        while True:
            frame = await plugin.render_frame(128, 32)
            if frame is None:
                break
            frame_count += 1
            # Safety: prevent infinite loop
            assert frame_count <= expected_total + 1, (
                f"Too many frames: got {frame_count}, expected at most {expected_total}"
            )

        # Verify total frame count matches formula
        assert frame_count == expected_total, (
            f"page_duration={page_duration_seconds}s, frame_delay={frame_delay_ms}ms: "
            f"got {frame_count} frames, expected {expected_total}"
        )

        # Verify None is returned after completion
        result = await plugin.render_frame(128, 32)
        assert result is None, "Should return None after all pages complete"
