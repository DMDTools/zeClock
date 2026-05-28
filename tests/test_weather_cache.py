"""Tests for weather cache refresh interval (task 9.4).

Tests cover:
- API called only when cache older than 15 minutes
- Cached data reused within 15 minutes (no API call)
- Cache invalidation after 15 minutes
- Mock time.time() to control cache expiry

**Property 14: Weather Cache Refresh Interval**
**Validates: Requirements 6.5**
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugins.weather_plugin import (
    CACHE_DURATION_SECONDS,
    WeatherData,
    WeatherPlugin,
)

# --- Helpers ---


def make_weather_data(fetched_at: float, city_name: str = "Paris") -> WeatherData:
    """Create a WeatherData instance with a specific fetch timestamp."""
    return WeatherData(
        current_temp=20.0,
        current_condition_code=0,
        current_description="Clear",
        tomorrow_high=24.0,
        tomorrow_low=15.0,
        tomorrow_condition_code=1,
        forecast_days=[],
        fetched_at=fetched_at,
        city_name=city_name,
    )


def make_valid_config() -> dict:
    """Create a valid weather plugin config."""
    return {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "city_name": "Paris",
        "temperature_unit": "celsius",
    }


# --- Unit Tests ---


class TestCacheStaleDetection:
    """Tests for is_cache_stale() method."""

    def test_cache_stale_when_none(self):
        """Cache should be considered stale when no data is cached."""
        plugin = WeatherPlugin()
        assert plugin.is_cache_stale() is True

    def test_cache_fresh_within_15_minutes(self):
        """Cache should be fresh when data was fetched less than 15 minutes ago."""
        plugin = WeatherPlugin()
        plugin._cache = make_weather_data(fetched_at=time.time() - 60)  # 1 minute ago
        assert plugin.is_cache_stale() is False

    def test_cache_stale_after_15_minutes(self):
        """Cache should be stale when data was fetched more than 15 minutes ago."""
        plugin = WeatherPlugin()
        plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 1
        )
        assert plugin.is_cache_stale() is True

    def test_cache_stale_at_exactly_15_minutes(self):
        """Cache should be stale at exactly 15 minutes (>= comparison)."""
        plugin = WeatherPlugin()
        now = time.time()
        with patch("zeclock.plugins.weather_plugin.time.time", return_value=now):
            plugin._cache = make_weather_data(fetched_at=now - CACHE_DURATION_SECONDS)
            assert plugin.is_cache_stale() is True

    def test_cache_fresh_just_before_15_minutes(self):
        """Cache should be fresh just before the 15-minute boundary."""
        plugin = WeatherPlugin()
        now = time.time()
        with patch("zeclock.plugins.weather_plugin.time.time", return_value=now):
            plugin._cache = make_weather_data(
                fetched_at=now - CACHE_DURATION_SECONDS + 1
            )
            assert plugin.is_cache_stale() is False


class TestCacheRefreshBehavior:
    """Tests for _refresh_cache_if_needed() API call behavior."""

    @pytest.mark.asyncio
    async def test_api_called_when_cache_stale(self):
        """API should be called when cache is older than 15 minutes."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Set stale cache
        plugin._cache = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )

        new_data = make_weather_data(fetched_at=time.time())

        with patch.object(
            plugin, "_fetch_weather_data", new_callable=AsyncMock, return_value=new_data
        ) as mock_fetch:
            await plugin._refresh_cache_if_needed()
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_not_called_when_cache_fresh(self):
        """API should NOT be called when cache is less than 15 minutes old."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Set fresh cache (just fetched)
        plugin._cache = make_weather_data(fetched_at=time.time())

        with patch.object(
            plugin, "_fetch_weather_data", new_callable=AsyncMock
        ) as mock_fetch:
            await plugin._refresh_cache_if_needed()
            mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_called_when_no_cache(self):
        """API should be called when there is no cached data at all."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"
        plugin._cache = None

        new_data = make_weather_data(fetched_at=time.time())

        with patch.object(
            plugin, "_fetch_weather_data", new_callable=AsyncMock, return_value=new_data
        ) as mock_fetch:
            await plugin._refresh_cache_if_needed()
            mock_fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_updated_after_successful_fetch(self):
        """Cache should be updated with new data after a successful API call."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Set stale cache
        old_data = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )
        plugin._cache = old_data

        new_data = make_weather_data(fetched_at=time.time())

        with patch.object(
            plugin, "_fetch_weather_data", new_callable=AsyncMock, return_value=new_data
        ):
            await plugin._refresh_cache_if_needed()

        assert plugin._cache is new_data
        assert plugin._cache is not old_data

    @pytest.mark.asyncio
    async def test_cache_preserved_on_fetch_failure(self):
        """Existing cache should be preserved when API fetch fails."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Set stale cache
        old_data = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )
        plugin._cache = old_data

        with patch.object(
            plugin,
            "_fetch_weather_data",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            await plugin._refresh_cache_if_needed()

        # Old cache should still be there
        assert plugin._cache is old_data

    @pytest.mark.asyncio
    async def test_cache_preserved_when_fetch_returns_none(self):
        """Existing cache should be preserved when API returns None."""
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        old_data = make_weather_data(
            fetched_at=time.time() - CACHE_DURATION_SECONDS - 60
        )
        plugin._cache = old_data

        with patch.object(
            plugin, "_fetch_weather_data", new_callable=AsyncMock, return_value=None
        ):
            await plugin._refresh_cache_if_needed()

        assert plugin._cache is old_data


class TestCacheInvalidationTiming:
    """Tests using mocked time to verify exact cache invalidation timing."""

    @pytest.mark.asyncio
    async def test_cache_valid_at_14_minutes_59_seconds(self):
        """Cache should still be valid at 14 minutes 59 seconds."""
        plugin = WeatherPlugin()
        base_time = 1000000.0

        with patch("zeclock.plugins.weather_plugin.time.time", return_value=base_time):
            plugin._cache = make_weather_data(fetched_at=base_time)

        # Advance time to 14:59
        check_time = base_time + (14 * 60 + 59)
        with patch("zeclock.plugins.weather_plugin.time.time", return_value=check_time):
            assert plugin.is_cache_stale() is False

    @pytest.mark.asyncio
    async def test_cache_invalid_at_15_minutes(self):
        """Cache should be invalid at exactly 15 minutes."""
        plugin = WeatherPlugin()
        base_time = 1000000.0

        plugin._cache = make_weather_data(fetched_at=base_time)

        # Advance time to exactly 15 minutes
        check_time = base_time + CACHE_DURATION_SECONDS
        with patch("zeclock.plugins.weather_plugin.time.time", return_value=check_time):
            assert plugin.is_cache_stale() is True

    @pytest.mark.asyncio
    async def test_cache_invalid_at_16_minutes(self):
        """Cache should be invalid at 16 minutes."""
        plugin = WeatherPlugin()
        base_time = 1000000.0

        plugin._cache = make_weather_data(fetched_at=base_time)

        check_time = base_time + 16 * 60
        with patch("zeclock.plugins.weather_plugin.time.time", return_value=check_time):
            assert plugin.is_cache_stale() is True

    @pytest.mark.asyncio
    async def test_multiple_activations_within_15_minutes_no_api_call(self):
        """Multiple activations within 15 minutes should not trigger API calls."""
        plugin = WeatherPlugin()
        config = make_valid_config()

        base_time = 1000000.0
        new_data = make_weather_data(fetched_at=base_time)

        with patch("zeclock.plugins.weather_plugin.time.time", return_value=base_time):
            with patch.object(
                plugin,
                "_fetch_weather_data",
                new_callable=AsyncMock,
                return_value=new_data,
            ) as mock_fetch:
                # First activation - should fetch (no cache)
                await plugin._refresh_cache_if_needed()
                assert mock_fetch.call_count == 1

        # Simulate multiple activations within 15 minutes
        for minutes_later in [1, 5, 10, 14]:
            check_time = base_time + minutes_later * 60
            with patch(
                "zeclock.plugins.weather_plugin.time.time", return_value=check_time
            ):
                with patch.object(
                    plugin, "_fetch_weather_data", new_callable=AsyncMock
                ) as mock_fetch:
                    await plugin._refresh_cache_if_needed()
                    mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_called_after_cache_expires(self):
        """API should be called again after cache expires (>15 minutes)."""
        plugin = WeatherPlugin()

        base_time = 1000000.0
        first_data = make_weather_data(fetched_at=base_time)
        plugin._cache = first_data
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Advance time past 15 minutes
        expired_time = base_time + CACHE_DURATION_SECONDS + 1
        second_data = make_weather_data(fetched_at=expired_time)

        with patch(
            "zeclock.plugins.weather_plugin.time.time", return_value=expired_time
        ):
            with patch.object(
                plugin,
                "_fetch_weather_data",
                new_callable=AsyncMock,
                return_value=second_data,
            ) as mock_fetch:
                await plugin._refresh_cache_if_needed()
                mock_fetch.assert_called_once()

        assert plugin._cache is second_data


# --- Property-Based Test ---
# Feature: plugin-system, Property 14: Weather Cache Refresh Interval


class TestWeatherCacheRefreshProperty:
    """Property-based test for weather cache refresh interval.

    **Validates: Requirements 6.5**

    Property 14: For any sequence of Weather_Plugin activations with timestamps,
    the plugin SHALL call the Open-Meteo API only when the cached data is older
    than 15 minutes. Activations within 15 minutes of the last successful fetch
    SHALL use cached data without making an API call.
    """

    @settings(max_examples=100)
    @given(
        fetch_time=st.floats(min_value=1_000_000, max_value=2_000_000),
        elapsed_seconds=st.floats(min_value=0, max_value=3600),
    )
    def test_cache_staleness_property(self, fetch_time: float, elapsed_seconds: float):
        """For any fetch time and elapsed duration, cache staleness is determined
        solely by whether elapsed time >= CACHE_DURATION_SECONDS (900s).

        **Validates: Requirements 6.5**
        """
        plugin = WeatherPlugin()
        plugin._cache = make_weather_data(fetched_at=fetch_time)

        current_time = fetch_time + elapsed_seconds

        with patch(
            "zeclock.plugins.weather_plugin.time.time", return_value=current_time
        ):
            is_stale = plugin.is_cache_stale()

        if elapsed_seconds >= CACHE_DURATION_SECONDS:
            assert is_stale is True, (
                f"Cache should be stale after {elapsed_seconds}s "
                f"(threshold: {CACHE_DURATION_SECONDS}s)"
            )
        else:
            assert is_stale is False, (
                f"Cache should be fresh after {elapsed_seconds}s "
                f"(threshold: {CACHE_DURATION_SECONDS}s)"
            )

    @settings(max_examples=100)
    @given(
        base_time=st.floats(min_value=1_000_000, max_value=2_000_000),
        activation_offsets=st.lists(
            st.floats(min_value=0, max_value=3600),
            min_size=1,
            max_size=10,
        ),
    )
    @pytest.mark.asyncio
    async def test_api_call_frequency_property(
        self, base_time: float, activation_offsets: list
    ):
        """For any sequence of activations, API is called only when cache is stale.

        **Validates: Requirements 6.5**
        """
        plugin = WeatherPlugin()
        plugin._latitude = 48.8566
        plugin._longitude = 2.3522
        plugin._city_name = "Paris"
        plugin._temperature_unit = "celsius"

        # Sort offsets to simulate chronological activations
        activation_offsets = sorted(activation_offsets)

        last_fetch_time = None
        total_api_calls = 0
        expected_api_calls = 0

        for offset in activation_offsets:
            current_time = base_time + offset

            # Determine if we expect an API call
            if last_fetch_time is None:
                # No cache - should call API
                should_call_api = True
            else:
                elapsed = current_time - last_fetch_time
                should_call_api = elapsed >= CACHE_DURATION_SECONDS

            if should_call_api:
                expected_api_calls += 1

            new_data = make_weather_data(fetched_at=current_time)

            with patch(
                "zeclock.plugins.weather_plugin.time.time", return_value=current_time
            ):
                with patch.object(
                    plugin,
                    "_fetch_weather_data",
                    new_callable=AsyncMock,
                    return_value=new_data,
                ) as mock_fetch:
                    await plugin._refresh_cache_if_needed()

                    if should_call_api:
                        mock_fetch.assert_called_once()
                        last_fetch_time = current_time
                        total_api_calls += 1
                    else:
                        mock_fetch.assert_not_called()

        assert total_api_calls == expected_api_calls
