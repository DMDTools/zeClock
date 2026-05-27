"""Property-based tests for configuration value clamping.

Feature: plugin-system, Property 13: Configuration Value Clamping
Validates: Requirements 4.5, 4.8
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeclock.plugin_config import (
    PluginConfig,
    clamp,
    CLOCK_DISPLAY_SECONDS_MIN,
    CLOCK_DISPLAY_SECONDS_MAX,
    FREQUENCY_MIN,
    FREQUENCY_MAX,
)

# --- Property-Based Tests: clamp function ---


@given(st.integers(min_value=-1000, max_value=0))
@settings(max_examples=100)
def test_clock_seconds_below_min_clamped_to_1(value: int):
    """Values below 1 are clamped to 1.

    **Validates: Requirements 4.5**
    """
    result = clamp(value, CLOCK_DISPLAY_SECONDS_MIN, CLOCK_DISPLAY_SECONDS_MAX)
    assert result == CLOCK_DISPLAY_SECONDS_MIN


@given(st.integers(min_value=301, max_value=10000))
@settings(max_examples=100)
def test_clock_seconds_above_max_clamped_to_300(value: int):
    """Values above 300 are clamped to 300.

    **Validates: Requirements 4.5**
    """
    result = clamp(value, CLOCK_DISPLAY_SECONDS_MIN, CLOCK_DISPLAY_SECONDS_MAX)
    assert result == CLOCK_DISPLAY_SECONDS_MAX


@given(
    st.integers(
        min_value=CLOCK_DISPLAY_SECONDS_MIN, max_value=CLOCK_DISPLAY_SECONDS_MAX
    )
)
@settings(max_examples=100)
def test_clock_seconds_in_range_unchanged(value: int):
    """Values in [1, 300] are returned unchanged.

    **Validates: Requirements 4.5**
    """
    result = clamp(value, CLOCK_DISPLAY_SECONDS_MIN, CLOCK_DISPLAY_SECONDS_MAX)
    assert result == value


@given(st.integers(min_value=-1000, max_value=-1))
@settings(max_examples=100)
def test_frequency_below_min_clamped_to_0(value: int):
    """Frequency values below 0 are clamped to 0.

    **Validates: Requirements 4.8**
    """
    result = clamp(value, FREQUENCY_MIN, FREQUENCY_MAX)
    assert result == FREQUENCY_MIN


@given(st.integers(min_value=101, max_value=10000))
@settings(max_examples=100)
def test_frequency_above_max_clamped_to_100(value: int):
    """Frequency values above 100 are clamped to 100.

    **Validates: Requirements 4.8**
    """
    result = clamp(value, FREQUENCY_MIN, FREQUENCY_MAX)
    assert result == FREQUENCY_MAX


@given(st.integers(min_value=FREQUENCY_MIN, max_value=FREQUENCY_MAX))
@settings(max_examples=100)
def test_frequency_in_range_unchanged(value: int):
    """Frequency values in [0, 100] are returned unchanged.

    **Validates: Requirements 4.8**
    """
    result = clamp(value, FREQUENCY_MIN, FREQUENCY_MAX)
    assert result == value


@given(st.integers())
@settings(max_examples=200)
def test_clamp_always_within_bounds(value: int):
    """Clamp always returns a value within [min, max].

    **Validates: Requirements 4.5, 4.8**
    """
    result = clamp(value, CLOCK_DISPLAY_SECONDS_MIN, CLOCK_DISPLAY_SECONDS_MAX)
    assert CLOCK_DISPLAY_SECONDS_MIN <= result <= CLOCK_DISPLAY_SECONDS_MAX


# --- Property-Based Tests: PluginConfig._parse_config integration ---


@given(st.integers())
@settings(max_examples=200)
def test_plugin_config_clock_seconds_always_clamped(value: int):
    """PluginConfig._parse_config clamps clock_display_seconds to [1, 300].

    **Validates: Requirements 4.5**
    """
    config = PluginConfig(config_path=None)
    data = {
        "clock_display_seconds": value,
        "plugins": [{"name": "pinball", "frequency": 100}],
    }
    config._parse_config(data)
    assert CLOCK_DISPLAY_SECONDS_MIN <= config.clock_display_seconds <= CLOCK_DISPLAY_SECONDS_MAX


@given(st.integers())
@settings(max_examples=200)
def test_plugin_config_frequency_always_clamped(value: int):
    """PluginConfig._parse_config clamps plugin frequency to [0, 100].

    **Validates: Requirements 4.8**
    """
    config = PluginConfig(config_path=None)
    data = {
        "clock_display_seconds": 5,
        "plugins": [{"name": "test_plugin", "frequency": value}],
    }
    config._parse_config(data)
    assert len(config.plugin_entries) == 1
    assert FREQUENCY_MIN <= config.plugin_entries[0]["frequency"] <= FREQUENCY_MAX


# --- Example-Based Boundary Tests ---


class TestConfigClamping:
    """Example-based tests for boundary conditions."""

    def test_clock_seconds_boundaries(self):
        assert clamp(0, 1, 300) == 1
        assert clamp(1, 1, 300) == 1
        assert clamp(150, 1, 300) == 150
        assert clamp(300, 1, 300) == 300
        assert clamp(301, 1, 300) == 300

    def test_frequency_boundaries(self):
        assert clamp(-1, 0, 100) == 0
        assert clamp(0, 0, 100) == 0
        assert clamp(50, 0, 100) == 50
        assert clamp(100, 0, 100) == 100
        assert clamp(101, 0, 100) == 100

    def test_plugin_config_clock_seconds_boundary_values(self):
        """Test PluginConfig clamps clock_display_seconds at boundaries."""
        config = PluginConfig(config_path=None)

        # Below minimum
        config._parse_config({"clock_display_seconds": 0, "plugins": []})
        assert config.clock_display_seconds == 1

        # At minimum
        config._parse_config({"clock_display_seconds": 1, "plugins": []})
        assert config.clock_display_seconds == 1

        # At maximum
        config._parse_config({"clock_display_seconds": 300, "plugins": []})
        assert config.clock_display_seconds == 300

        # Above maximum
        config._parse_config({"clock_display_seconds": 301, "plugins": []})
        assert config.clock_display_seconds == 300

        # Negative value
        config._parse_config({"clock_display_seconds": -100, "plugins": []})
        assert config.clock_display_seconds == 1

    def test_plugin_config_frequency_boundary_values(self):
        """Test PluginConfig clamps frequency at boundaries."""
        config = PluginConfig(config_path=None)

        # Below minimum
        config._parse_config({
            "clock_display_seconds": 5,
            "plugins": [{"name": "p", "frequency": -1}],
        })
        assert config.plugin_entries[0]["frequency"] == 0

        # At minimum
        config._parse_config({
            "clock_display_seconds": 5,
            "plugins": [{"name": "p", "frequency": 0}],
        })
        assert config.plugin_entries[0]["frequency"] == 0

        # At maximum
        config._parse_config({
            "clock_display_seconds": 5,
            "plugins": [{"name": "p", "frequency": 100}],
        })
        assert config.plugin_entries[0]["frequency"] == 100

        # Above maximum
        config._parse_config({
            "clock_display_seconds": 5,
            "plugins": [{"name": "p", "frequency": 101}],
        })
        assert config.plugin_entries[0]["frequency"] == 100

        # Large negative
        config._parse_config({
            "clock_display_seconds": 5,
            "plugins": [{"name": "p", "frequency": -9999}],
        })
        assert config.plugin_entries[0]["frequency"] == 0
