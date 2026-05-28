"""Unit and property tests for unknown plugin name exclusion.

Feature: plugin-system, Property 12: Unknown Plugin Names Excluded
Validates: Requirements 4.4, 7.3

For any set of plugin names referenced in configuration or CLI arguments,
only those names that match a plugin in the Plugin_Registry SHALL be included
in scheduling. Names not found in the registry SHALL be excluded without
affecting the scheduling of valid plugins.
"""

import logging
from pathlib import Path
from typing import List, Set
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugin_config import PluginConfig
from zeclock.plugin_manager import PluginManager
from zeclock.plugin_registry import PluginRegistry
from zeclock.plugins.base import validate_plugin_name
from tests.conftest import DummyPlugin

# --- Strategies ---

valid_plugin_name_chars = st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_-")
valid_plugin_names = st.text(
    alphabet=valid_plugin_name_chars, min_size=1, max_size=64
).filter(lambda n: validate_plugin_name(n))

# Strategy for names that are valid format but won't be in the registry
unknown_plugin_names = st.text(
    alphabet=valid_plugin_name_chars, min_size=1, max_size=64
).filter(lambda n: validate_plugin_name(n))


# --- Helper functions ---


def build_registry_with_plugins(names: List[str]) -> PluginRegistry:
    """Create a registry with DummyPlugins registered under the given names."""
    registry = PluginRegistry()
    for name in names:
        plugin = DummyPlugin(name=name)
        registry.register(plugin, "builtin", frequency=50)
    return registry


def filter_cli_plugins(
    requested_names: List[str], registry: PluginRegistry
) -> List[str]:
    """Filter CLI-provided plugin names against the registry.

    This simulates the behavior described in Requirements 7.3:
    names not found in the registry are excluded with a warning.
    """
    valid = []
    for name in requested_names:
        if registry.has_plugin(name):
            valid.append(name)
    return valid


# --- Unit Tests: Unknown names in config excluded from scheduling ---


class TestUnknownPluginsInConfig:
    """Test that unknown plugin names in config are excluded from scheduling."""

    def test_unknown_name_not_scheduled(self):
        """A plugin name in config that isn't registered gets excluded."""
        registry = PluginRegistry()
        plugin = DummyPlugin(name="pinball")
        registry.register(plugin, "builtin", frequency=100)

        # "weather" is not registered
        # Applying config with unknown name should not affect scheduling
        assert not registry.has_plugin("weather")
        active = registry.get_active_plugins()
        assert len(active) == 1
        assert active[0].name == "pinball"

    def test_apply_config_frequencies_warns_on_unknown(self, caplog):
        """PluginManager logs a warning for unknown plugin names in config."""
        manager = PluginManager(width=128, height=32)
        # Register only "pinball"
        pinball = DummyPlugin(name="pinball")
        manager.registry.register(pinball, "builtin", frequency=100)

        # Config references "unknown-plugin"
        manager.config.plugin_entries = [
            {"name": "pinball", "frequency": 70, "settings": {}},
            {"name": "unknown-plugin", "frequency": 30, "settings": {}},
        ]

        with caplog.at_level(logging.WARNING):
            manager._apply_config_frequencies()

        # Warning logged for unknown plugin
        assert any("unknown-plugin" in record.message for record in caplog.records)
        # Only pinball is schedulable
        active = manager.registry.get_active_plugins()
        assert len(active) == 1
        assert active[0].name == "pinball"

    def test_multiple_unknown_names_all_excluded(self, caplog):
        """Multiple unknown names in config are all excluded."""
        manager = PluginManager(width=128, height=32)
        pinball = DummyPlugin(name="pinball")
        manager.registry.register(pinball, "builtin", frequency=100)

        manager.config.plugin_entries = [
            {"name": "pinball", "frequency": 50, "settings": {}},
            {"name": "ghost-plugin", "frequency": 25, "settings": {}},
            {"name": "phantom-plugin", "frequency": 25, "settings": {}},
        ]

        with caplog.at_level(logging.WARNING):
            manager._apply_config_frequencies()

        # Both unknown plugins warned about
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ghost-plugin" in w for w in warnings)
        assert any("phantom-plugin" in w for w in warnings)

        # Only pinball is active
        active = manager.registry.get_active_plugins()
        assert len(active) == 1
        assert active[0].name == "pinball"

    def test_all_config_names_unknown_results_in_empty_scheduling(self, caplog):
        """If all config names are unknown, no plugins are scheduled."""
        manager = PluginManager(width=128, height=32)
        # No plugins registered at all

        manager.config.plugin_entries = [
            {"name": "nonexistent-a", "frequency": 50, "settings": {}},
            {"name": "nonexistent-b", "frequency": 50, "settings": {}},
        ]

        with caplog.at_level(logging.WARNING):
            manager._apply_config_frequencies()

        active = manager.registry.get_active_plugins()
        assert len(active) == 0

    def test_valid_plugin_frequency_applied_despite_unknown_names(self):
        """Valid plugins get their frequency applied even when unknown names present."""
        manager = PluginManager(width=128, height=32)
        pinball = DummyPlugin(name="pinball")
        weather = DummyPlugin(name="weather")
        manager.registry.register(pinball, "builtin", frequency=100)
        manager.registry.register(weather, "builtin", frequency=100)

        manager.config.plugin_entries = [
            {"name": "pinball", "frequency": 70, "settings": {}},
            {"name": "weather", "frequency": 30, "settings": {}},
            {"name": "unknown-x", "frequency": 50, "settings": {}},
        ]

        manager._apply_config_frequencies()

        assert manager.registry.get_plugin("pinball").frequency == 70
        assert manager.registry.get_plugin("weather").frequency == 30


# --- Unit Tests: Unknown names in --plugins CLI excluded ---


class TestUnknownPluginsInCLI:
    """Test that unknown plugin names in --plugins CLI are excluded."""

    def test_unknown_cli_name_excluded(self):
        """Unknown names in CLI plugin list are filtered out."""
        registry = build_registry_with_plugins(["pinball", "weather"])

        requested = ["pinball", "nonexistent"]
        valid = filter_cli_plugins(requested, registry)

        assert valid == ["pinball"]
        assert "nonexistent" not in valid

    def test_all_cli_names_unknown(self):
        """If all CLI names are unknown, result is empty."""
        registry = build_registry_with_plugins(["pinball"])

        requested = ["ghost", "phantom", "specter"]
        valid = filter_cli_plugins(requested, registry)

        assert valid == []

    def test_valid_plugins_still_scheduled_with_unknown_mixed(self):
        """Valid plugins are correctly included when mixed with unknown names."""
        registry = build_registry_with_plugins(["pinball", "weather", "custom"])

        requested = ["pinball", "unknown-a", "weather", "unknown-b"]
        valid = filter_cli_plugins(requested, registry)

        assert valid == ["pinball", "weather"]

    def test_empty_cli_list(self):
        """Empty CLI plugin list results in empty valid list."""
        registry = build_registry_with_plugins(["pinball"])

        valid = filter_cli_plugins([], registry)
        assert valid == []

    def test_duplicate_valid_names_preserved(self):
        """Duplicate valid names in CLI are preserved (dedup is caller's job)."""
        registry = build_registry_with_plugins(["pinball"])

        requested = ["pinball", "pinball"]
        valid = filter_cli_plugins(requested, registry)

        assert valid == ["pinball", "pinball"]


# --- Unit Tests: Valid plugins still scheduled when mixed with unknown ---


class TestValidPluginsScheduledWithUnknown:
    """Test that valid plugins are still correctly scheduled when unknown names present."""

    def test_normalized_frequencies_only_include_registered(self):
        """Normalized frequencies only include registered plugins."""
        registry = PluginRegistry()
        p1 = DummyPlugin(name="alpha")
        p2 = DummyPlugin(name="beta")
        registry.register(p1, "builtin", frequency=60)
        registry.register(p2, "builtin", frequency=40)

        # Unknown names don't affect normalization
        normalized = registry.get_normalized_frequencies()
        assert len(normalized) == 2
        plugins_in_schedule = {p.name for p, _ in normalized}
        assert plugins_in_schedule == {"alpha", "beta"}

    def test_select_next_plugin_only_picks_registered(self):
        """select_next_plugin only picks from registered plugins."""
        manager = PluginManager(width=128, height=32)
        p1 = DummyPlugin(name="pinball")
        manager.registry.register(p1, "builtin", frequency=100)

        # Config has unknown plugin too
        manager.config.plugin_entries = [
            {"name": "pinball", "frequency": 100, "settings": {}},
            {"name": "unknown-plugin", "frequency": 100, "settings": {}},
        ]
        manager._apply_config_frequencies()

        # Selection should only return pinball
        selected = manager.select_next_plugin()
        assert selected is not None
        assert selected.name == "pinball"

    def test_scheduling_unaffected_by_unknown_names_in_config(self):
        """Multiple valid plugins are all schedulable despite unknown names in config."""
        manager = PluginManager(width=128, height=32)
        p1 = DummyPlugin(name="alpha")
        p2 = DummyPlugin(name="beta")
        manager.registry.register(p1, "builtin", frequency=50)
        manager.registry.register(p2, "builtin", frequency=50)

        manager.config.plugin_entries = [
            {"name": "alpha", "frequency": 50, "settings": {}},
            {"name": "beta", "frequency": 50, "settings": {}},
            {"name": "ghost", "frequency": 100, "settings": {}},
        ]
        manager._apply_config_frequencies()

        # Both valid plugins should be schedulable
        normalized = manager.registry.get_normalized_frequencies()
        assert len(normalized) == 2
        names = {p.name for p, _ in normalized}
        assert names == {"alpha", "beta"}


# --- Property-Based Test: Property 12 ---


class TestUnknownPluginNamesExcludedProperty:
    """Property 12: Unknown Plugin Names Excluded.

    For any set of plugin names referenced in configuration or CLI arguments,
    only those names that match a plugin in the Plugin_Registry SHALL be
    included in scheduling. Names not found in the registry SHALL be excluded
    without affecting the scheduling of valid plugins.

    **Validates: Requirements 4.4, 7.3**
    """

    @given(
        registered_names=st.lists(
            valid_plugin_names, min_size=1, max_size=5, unique=True
        ),
        unknown_names=st.lists(valid_plugin_names, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=100)
    def test_unknown_names_excluded_from_config_scheduling(
        self, registered_names, unknown_names
    ):
        """Unknown names in config never appear in scheduling.

        # Feature: plugin-system, Property 12: Unknown Plugin Names Excluded
        """
        # Ensure unknown names are truly not in registered set
        unknown_names = [n for n in unknown_names if n not in registered_names]
        assume(len(unknown_names) > 0)

        manager = PluginManager(width=128, height=32)

        # Register only the known plugins
        for name in registered_names:
            plugin = DummyPlugin(name=name)
            manager.registry.register(plugin, "builtin", frequency=50)

        # Config references both known and unknown
        all_entries = []
        for name in registered_names:
            all_entries.append({"name": name, "frequency": 50, "settings": {}})
        for name in unknown_names:
            all_entries.append({"name": name, "frequency": 50, "settings": {}})
        manager.config.plugin_entries = all_entries

        manager._apply_config_frequencies()

        # Only registered plugins appear in scheduling
        active = manager.registry.get_active_plugins()
        active_names = {e.name for e in active}
        assert active_names == set(registered_names)

        # No unknown name appears in scheduling
        for unknown in unknown_names:
            assert unknown not in active_names

    @given(
        registered_names=st.lists(
            valid_plugin_names, min_size=1, max_size=5, unique=True
        ),
        requested_names=st.lists(
            valid_plugin_names, min_size=1, max_size=8, unique=True
        ),
    )
    @settings(max_examples=100)
    def test_unknown_names_excluded_from_cli_filtering(
        self, registered_names, requested_names
    ):
        """Unknown names in CLI plugin list are excluded from activation.

        # Feature: plugin-system, Property 12: Unknown Plugin Names Excluded
        """
        registry = build_registry_with_plugins(registered_names)

        valid = filter_cli_plugins(requested_names, registry)

        # Every name in valid must be in the registry
        for name in valid:
            assert registry.has_plugin(name)

        # Every requested name that IS in the registry must be in valid
        for name in requested_names:
            if registry.has_plugin(name):
                assert name in valid

        # No unknown name appears in valid
        for name in requested_names:
            if not registry.has_plugin(name):
                assert name not in valid

    @given(
        registered_names=st.lists(
            valid_plugin_names, min_size=1, max_size=5, unique=True
        ),
        unknown_names=st.lists(valid_plugin_names, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=100)
    def test_valid_plugins_unaffected_by_unknown_names(
        self, registered_names, unknown_names
    ):
        """Valid plugins remain schedulable regardless of unknown names present.

        # Feature: plugin-system, Property 12: Unknown Plugin Names Excluded
        """
        unknown_names = [n for n in unknown_names if n not in registered_names]
        assume(len(unknown_names) > 0)

        manager = PluginManager(width=128, height=32)

        # Register known plugins
        for name in registered_names:
            plugin = DummyPlugin(name=name)
            manager.registry.register(plugin, "builtin", frequency=50)

        # Config with mix of known and unknown
        all_entries = []
        for name in registered_names:
            all_entries.append({"name": name, "frequency": 50, "settings": {}})
        for name in unknown_names:
            all_entries.append({"name": name, "frequency": 50, "settings": {}})
        manager.config.plugin_entries = all_entries

        manager._apply_config_frequencies()

        # All registered plugins are still active and schedulable
        normalized = manager.registry.get_normalized_frequencies()
        scheduled_names = {p.name for p, _ in normalized}
        assert set(registered_names) == scheduled_names

        # Frequencies sum to 1.0
        total_weight = sum(w for _, w in normalized)
        assert abs(total_weight - 1.0) < 1e-9
