"""Property-based tests for frame delay validation.

Feature: plugin-system, Property 6: Frame Delay Range Validation
Validates: Requirements 2.7
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from zeclock.plugins.base import (
    validate_frame_delay_ms,
    FRAME_DELAY_MIN_MS,
    FRAME_DELAY_MAX_MS,
)

# --- Property-Based Tests ---


@given(st.integers(min_value=FRAME_DELAY_MIN_MS, max_value=FRAME_DELAY_MAX_MS))
@settings(max_examples=200)
def test_valid_delays_accepted(delay: int):
    """Any integer in [20, 5000] is a valid frame delay."""
    assert validate_frame_delay_ms(delay) is True


@given(st.integers(min_value=-10000, max_value=FRAME_DELAY_MIN_MS - 1))
@settings(max_examples=100)
def test_below_minimum_rejected(delay: int):
    """Integers below 20 are rejected."""
    assert validate_frame_delay_ms(delay) is False


@given(st.integers(min_value=FRAME_DELAY_MAX_MS + 1, max_value=100000))
@settings(max_examples=100)
def test_above_maximum_rejected(delay: int):
    """Integers above 5000 are rejected."""
    assert validate_frame_delay_ms(delay) is False


@given(st.integers())
@settings(max_examples=200)
def test_frame_delay_validation_correctness(delay: int):
    """validate_frame_delay_ms accepts iff 20 <= delay <= 5000."""
    expected = FRAME_DELAY_MIN_MS <= delay <= FRAME_DELAY_MAX_MS
    assert validate_frame_delay_ms(delay) == expected


# --- Example-Based Tests ---


class TestFrameDelayValidation:
    """Example-based tests for edge cases."""

    def test_minimum_boundary(self):
        assert validate_frame_delay_ms(20) is True
        assert validate_frame_delay_ms(19) is False

    def test_maximum_boundary(self):
        assert validate_frame_delay_ms(5000) is True
        assert validate_frame_delay_ms(5001) is False

    def test_typical_values(self):
        assert validate_frame_delay_ms(40) is True  # 25 FPS
        assert validate_frame_delay_ms(100) is True  # 10 FPS
        assert validate_frame_delay_ms(1000) is True  # 1 FPS
        assert validate_frame_delay_ms(4000) is True  # 0.25 FPS (weather pages)

    def test_zero_rejected(self):
        assert validate_frame_delay_ms(0) is False

    def test_negative_rejected(self):
        assert validate_frame_delay_ms(-1) is False
        assert validate_frame_delay_ms(-100) is False

    def test_non_integer_rejected(self):
        assert validate_frame_delay_ms(40.5) is False  # type: ignore
        assert validate_frame_delay_ms("40") is False  # type: ignore
        assert validate_frame_delay_ms(None) is False  # type: ignore
