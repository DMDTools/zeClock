"""Property-based tests for temperature formatting.

Feature: plugin-system, Property 16: Temperature Formatting
**Validates: Requirements 6.1, 6.2, 6.11**

Tests that the WeatherPlugin formats temperatures as rounded integers
with the correct unit symbol, and that condition descriptions are
truncated to at most 12 characters.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeclock.plugins.weather_plugin import WeatherPlugin, WMO_DESCRIPTIONS


# --- Property-Based Tests ---


@given(
    temp=st.floats(min_value=-60.0, max_value=60.0, allow_nan=False, allow_infinity=False)
)
@settings(max_examples=200)
def test_temperature_always_rounded_integer_celsius(temp: float):
    """**Validates: Requirements 6.1, 6.2, 6.11**

    For any floating-point temperature value with unit Celsius,
    the Weather_Plugin SHALL display the temperature as a rounded integer
    with C suffix.
    """
    plugin = WeatherPlugin()
    plugin._temperature_unit = "celsius"
    result = plugin._format_temp(temp)

    # Extract the numeric part (everything except last char)
    numeric_part = result[:-1]
    # Should be a valid integer (no decimal point)
    assert "." not in numeric_part
    parsed = int(numeric_part)
    assert parsed == round(temp)
    # Should end with C
    assert result.endswith("C")


@given(
    temp=st.floats(min_value=-60.0, max_value=150.0, allow_nan=False, allow_infinity=False)
)
@settings(max_examples=200)
def test_temperature_always_rounded_integer_fahrenheit(temp: float):
    """**Validates: Requirements 6.1, 6.2, 6.11**

    For any floating-point temperature value with unit Fahrenheit,
    the Weather_Plugin SHALL display the temperature as a rounded integer
    with F suffix.
    """
    plugin = WeatherPlugin()
    plugin._temperature_unit = "fahrenheit"
    result = plugin._format_temp(temp)

    # Extract the numeric part (everything except last char)
    numeric_part = result[:-1]
    # Should be a valid integer (no decimal point)
    assert "." not in numeric_part
    parsed = int(numeric_part)
    assert parsed == round(temp)
    # Should end with F
    assert result.endswith("F")


@given(
    temp=st.floats(min_value=-60.0, max_value=150.0, allow_nan=False, allow_infinity=False),
    unit=st.sampled_from(["celsius", "fahrenheit"]),
)
@settings(max_examples=200)
def test_format_temp_unit_symbol_correct(temp: float, unit: str):
    """**Validates: Requirements 6.11**

    The unit symbol SHALL be C for Celsius and F for Fahrenheit.
    """
    plugin = WeatherPlugin()
    plugin._temperature_unit = unit
    result = plugin._format_temp(temp)

    if unit == "celsius":
        assert result.endswith("C")
    else:
        assert result.endswith("F")


@given(code=st.sampled_from(list(WMO_DESCRIPTIONS.keys())))
@settings(max_examples=100)
def test_condition_description_max_12_chars_known_codes(code: int):
    """**Validates: Requirements 6.1**

    For any known WMO weather code, the condition description
    SHALL be at most 12 characters.
    """
    plugin = WeatherPlugin()
    result = plugin._get_condition_description(code)
    assert len(result) <= 12


@given(code=st.integers(min_value=-100, max_value=200))
@settings(max_examples=200)
def test_condition_description_max_12_chars_any_code(code: int):
    """**Validates: Requirements 6.1**

    For any integer weather code (including unknown ones),
    the description text SHALL be at most 12 characters.
    """
    plugin = WeatherPlugin()
    result = plugin._get_condition_description(code)
    assert len(result) <= 12


# --- Example-Based Tests ---


class TestTemperatureFormatting:
    """Example-based tests for temperature display using the actual plugin method."""

    def test_positive_celsius(self):
        plugin = WeatherPlugin()
        plugin._temperature_unit = "celsius"
        assert plugin._format_temp(23.7) == "24C"
        assert plugin._format_temp(0.0) == "0C"

    def test_negative_celsius(self):
        plugin = WeatherPlugin()
        plugin._temperature_unit = "celsius"
        assert plugin._format_temp(-5.3) == "-5C"
        assert plugin._format_temp(-0.4) == "0C"

    def test_fahrenheit(self):
        plugin = WeatherPlugin()
        plugin._temperature_unit = "fahrenheit"
        assert plugin._format_temp(72.6) == "73F"
        assert plugin._format_temp(32.0) == "32F"

    def test_rounding_half(self):
        """Python rounds 0.5 to nearest even (banker's rounding)."""
        plugin = WeatherPlugin()
        plugin._temperature_unit = "celsius"
        assert plugin._format_temp(23.5) == "24C"
        assert plugin._format_temp(22.5) == "22C"

    def test_extreme_temperatures(self):
        """Extreme but valid temperatures still format correctly."""
        plugin = WeatherPlugin()
        plugin._temperature_unit = "celsius"
        assert plugin._format_temp(-50.9) == "-51C"
        assert plugin._format_temp(56.7) == "57C"

    def test_fahrenheit_extreme(self):
        plugin = WeatherPlugin()
        plugin._temperature_unit = "fahrenheit"
        assert plugin._format_temp(134.1) == "134F"
        assert plugin._format_temp(-58.0) == "-58F"


class TestConditionDescription:
    """Example-based tests for condition description truncation."""

    def test_short_description_unchanged(self):
        plugin = WeatherPlugin()
        assert plugin._get_condition_description(0) == "Clear"
        assert plugin._get_condition_description(45) == "Fog"

    def test_long_description_truncated(self):
        """Descriptions longer than 12 chars are truncated."""
        plugin = WeatherPlugin()
        # "Thunderstorm" is exactly 12 chars - should be kept
        result = plugin._get_condition_description(95)
        assert len(result) <= 12
        assert result == "Thunderstorm"

    def test_unknown_code_returns_unknown(self):
        """Unknown WMO codes return 'Unknown' (7 chars, within limit)."""
        plugin = WeatherPlugin()
        result = plugin._get_condition_description(999)
        assert result == "Unknown"
        assert len(result) <= 12

    def test_all_wmo_descriptions_within_limit(self):
        """All predefined WMO descriptions are at most 12 characters."""
        plugin = WeatherPlugin()
        for code in WMO_DESCRIPTIONS:
            result = plugin._get_condition_description(code)
            assert len(result) <= 12, (
                f"WMO code {code} description '{result}' exceeds 12 chars"
            )
