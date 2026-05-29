"""Property-based tests for plugin name validation.

Feature: plugin-system, Property 1: Plugin Name Validation
Validates: Requirements 1.7, 2.1
"""

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeclock.plugins.base import validate_plugin_name

# --- Property-Based Tests ---


@given(
    st.text(
        alphabet=string.ascii_lowercase + string.digits + "_-",
        min_size=1,
        max_size=64,
    )
)
@settings(max_examples=200)
def test_valid_names_always_accepted(name: str):
    """Any string of 1-64 lowercase alphanumeric/hyphen/underscore chars is valid."""
    assert validate_plugin_name(name) is True


@given(st.text(min_size=0, max_size=100))
@settings(max_examples=200)
def test_name_validation_matches_regex(name: str):
    """validate_plugin_name accepts iff name matches ^[a-z0-9_-]{1,64}$."""
    import re

    expected = bool(re.match(r"^[a-z0-9_-]{1,64}$", name))
    assert validate_plugin_name(name) == expected


@given(
    st.text(
        alphabet=string.ascii_lowercase + string.digits + "_-",
        min_size=65,
        max_size=200,
    )
)
@settings(max_examples=50)
def test_names_exceeding_64_chars_rejected(name: str):
    """Names longer than 64 characters are always rejected."""
    assert validate_plugin_name(name) is False


# --- Example-Based Tests ---


class TestPluginNameValidation:
    """Example-based tests for edge cases."""

    def test_empty_string_rejected(self):
        assert validate_plugin_name("") is False

    def test_single_char_accepted(self):
        assert validate_plugin_name("a") is True
        assert validate_plugin_name("0") is True
        assert validate_plugin_name("-") is True
        assert validate_plugin_name("_") is True

    def test_max_length_accepted(self):
        assert validate_plugin_name("a" * 64) is True

    def test_over_max_length_rejected(self):
        assert validate_plugin_name("a" * 65) is False

    def test_uppercase_rejected(self):
        assert validate_plugin_name("MyPlugin") is False
        assert validate_plugin_name("PLUGIN") is False

    def test_spaces_rejected(self):
        assert validate_plugin_name("my plugin") is False

    def test_special_chars_rejected(self):
        assert validate_plugin_name("my.plugin") is False
        assert validate_plugin_name("my@plugin") is False
        assert validate_plugin_name("my/plugin") is False

    def test_valid_examples(self):
        assert validate_plugin_name("weather") is True
        assert validate_plugin_name("pinball") is True
        assert validate_plugin_name("my-custom-plugin") is True
        assert validate_plugin_name("plugin_v2") is True
        assert validate_plugin_name("aws-cost-monitor") is True

    def test_non_string_rejected(self):
        assert validate_plugin_name(123) is False  # type: ignore
        assert validate_plugin_name(None) is False  # type: ignore
        assert validate_plugin_name([]) is False  # type: ignore
