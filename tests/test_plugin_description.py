"""Property-based tests for plugin description validation.

Feature: plugin-system, Property 4: Description Validation
Validates: Requirements 2.2
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeclock.plugins.base import validate_plugin_description

# --- Property-Based Tests ---


@given(st.text(min_size=1, max_size=256))
@settings(max_examples=200)
def test_non_empty_up_to_256_chars_accepted(desc: str):
    """Any non-empty string of at most 256 characters is valid."""
    assert validate_plugin_description(desc) is True


@given(st.text(min_size=257, max_size=500))
@settings(max_examples=100)
def test_over_256_chars_rejected(desc: str):
    """Strings exceeding 256 characters are always rejected."""
    assert validate_plugin_description(desc) is False


@given(st.text(min_size=0, max_size=300))
@settings(max_examples=200)
def test_description_validation_correctness(desc: str):
    """validate_plugin_description accepts iff 0 < len(desc) <= 256."""
    expected = 0 < len(desc) <= 256
    assert validate_plugin_description(desc) == expected


# --- Example-Based Tests ---


class TestPluginDescriptionValidation:
    """Example-based tests for edge cases."""

    def test_empty_string_rejected(self):
        assert validate_plugin_description("") is False

    def test_single_char_accepted(self):
        assert validate_plugin_description("A") is True

    def test_max_length_accepted(self):
        assert validate_plugin_description("x" * 256) is True

    def test_over_max_length_rejected(self):
        assert validate_plugin_description("x" * 257) is False

    def test_unicode_accepted(self):
        assert validate_plugin_description("Météo plugin 🌤️") is True

    def test_multiline_accepted(self):
        assert validate_plugin_description("Line 1\nLine 2") is True

    def test_non_string_rejected(self):
        assert validate_plugin_description(123) is False  # type: ignore
        assert validate_plugin_description(None) is False  # type: ignore
