"""Property-based tests for frequency normalization.

Feature: plugin-system, Property 9: Frequency Normalization Invariant
Validates: Requirements 3.2, 3.3, 4.6
"""

import math

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugin_registry import PluginRegistry
from tests.conftest import DummyPlugin


def make_registry_with_plugins(frequencies: list) -> PluginRegistry:
    """Helper to create a registry with plugins at given frequencies."""
    registry = PluginRegistry()
    for i, freq in enumerate(frequencies):
        plugin = DummyPlugin(name=f"plugin-{i}", description=f"Plugin {i}")
        registry.register(plugin, "builtin", frequency=freq)
    return registry


# --- Property-Based Tests ---


@given(
    st.lists(
        st.integers(min_value=0, max_value=100),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=200)
def test_normalized_frequencies_sum_to_one(frequencies: list):
    """For any non-empty list of active plugins, normalized probabilities sum to 1.0."""
    # At least one frequency must be > 0 for meaningful normalization
    assume(sum(frequencies) > 0)

    registry = make_registry_with_plugins(frequencies)
    normalized = registry.get_normalized_frequencies()

    assert len(normalized) == len(frequencies)
    total = sum(weight for _, weight in normalized)
    assert math.isclose(total, 1.0, rel_tol=1e-9)


@given(
    st.lists(
        st.integers(min_value=1, max_value=100),
        min_size=1,
        max_size=1,
    )
)
@settings(max_examples=50)
def test_single_plugin_gets_full_weight(frequencies: list):
    """When only one plugin is active, its normalized frequency is 1.0."""
    registry = make_registry_with_plugins(frequencies)
    normalized = registry.get_normalized_frequencies()

    assert len(normalized) == 1
    _, weight = normalized[0]
    assert math.isclose(weight, 1.0, rel_tol=1e-9)


@given(st.integers(min_value=2, max_value=10))
@settings(max_examples=50)
def test_equal_frequencies_give_equal_weights(n: int):
    """N plugins with equal frequency each get weight 1/N."""
    frequencies = [50] * n
    registry = make_registry_with_plugins(frequencies)
    normalized = registry.get_normalized_frequencies()

    expected_weight = 1.0 / n
    for _, weight in normalized:
        assert math.isclose(weight, expected_weight, rel_tol=1e-9)


@given(
    st.lists(
        st.integers(min_value=0, max_value=0),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=50)
def test_all_zero_frequencies_equal_distribution(frequencies: list):
    """When all frequencies are 0, plugins get equal distribution."""
    registry = make_registry_with_plugins(frequencies)
    normalized = registry.get_normalized_frequencies()

    expected_weight = 1.0 / len(frequencies)
    total = sum(weight for _, weight in normalized)
    assert math.isclose(total, 1.0, rel_tol=1e-9)
    for _, weight in normalized:
        assert math.isclose(weight, expected_weight, rel_tol=1e-9)


# --- Example-Based Tests ---


class TestFrequencyNormalization:
    """Example-based tests for specific scenarios."""

    def test_70_30_split(self):
        registry = make_registry_with_plugins([70, 30])
        normalized = registry.get_normalized_frequencies()
        weights = [w for _, w in normalized]
        assert math.isclose(weights[0], 0.7, rel_tol=1e-9)
        assert math.isclose(weights[1], 0.3, rel_tol=1e-9)

    def test_empty_registry_returns_empty(self):
        registry = PluginRegistry()
        assert registry.get_normalized_frequencies() == []

    def test_failed_plugins_excluded(self):
        registry = make_registry_with_plugins([50, 50])
        registry.mark_failed("plugin-0", "test error")
        normalized = registry.get_normalized_frequencies()
        assert len(normalized) == 1
        _, weight = normalized[0]
        assert math.isclose(weight, 1.0, rel_tol=1e-9)

    def test_three_way_split(self):
        registry = make_registry_with_plugins([50, 30, 20])
        normalized = registry.get_normalized_frequencies()
        weights = [w for _, w in normalized]
        assert math.isclose(weights[0], 0.5, rel_tol=1e-9)
        assert math.isclose(weights[1], 0.3, rel_tol=1e-9)
        assert math.isclose(weights[2], 0.2, rel_tol=1e-9)
