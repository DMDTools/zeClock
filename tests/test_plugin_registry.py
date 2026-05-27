"""Unit tests for PluginRegistry.

Feature: plugin-system, Property 3: User Plugin Override
Validates: Requirements 1.5, 3.2, 3.3
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugin_registry import PluginRegistry, PluginEntry
from zeclock.plugins.base import validate_plugin_name
from tests.conftest import DummyPlugin


# Strategy for valid plugin names: 1-64 chars of lowercase alphanumeric, hyphens, underscores
valid_plugin_name_chars = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyz0123456789_-"
)
valid_plugin_names = st.text(
    alphabet=valid_plugin_name_chars, min_size=1, max_size=64
).filter(lambda n: validate_plugin_name(n))


class TestPluginRegistry:
    """Tests for PluginRegistry operations."""

    def test_register_plugin(self):
        registry = PluginRegistry()
        plugin = DummyPlugin(name="test-plugin")
        registry.register(plugin, "builtin", frequency=70)

        assert len(registry) == 1
        assert registry.has_plugin("test-plugin")
        entry = registry.get_plugin("test-plugin")
        assert entry.name == "test-plugin"
        assert entry.source == "builtin"
        assert entry.state == "available"
        assert entry.frequency == 70

    def test_override_plugin(self):
        """User plugin overrides built-in with same name (Property 3)."""
        registry = PluginRegistry()
        builtin = DummyPlugin(name="pinball", description="Built-in pinball")
        user = DummyPlugin(name="pinball", description="User pinball")

        registry.register(builtin, "builtin", frequency=100)
        registry.override_plugin("pinball", user, "user")

        assert len(registry) == 1
        entry = registry.get_plugin("pinball")
        assert entry.source == "user"
        assert entry.plugin is user
        assert entry.plugin.description == "User pinball"

    def test_override_preserves_frequency(self):
        """Override keeps the original frequency setting."""
        registry = PluginRegistry()
        builtin = DummyPlugin(name="pinball")
        user = DummyPlugin(name="pinball")

        registry.register(builtin, "builtin", frequency=70)
        registry.override_plugin("pinball", user, "user")

        entry = registry.get_plugin("pinball")
        assert entry.frequency == 70

    def test_mark_failed_excludes_from_active(self):
        registry = PluginRegistry()
        plugin = DummyPlugin(name="broken")
        registry.register(plugin, "builtin")

        registry.mark_failed("broken", "test error")

        assert registry.get_plugin("broken").state == "failed"
        active = registry.get_active_plugins()
        assert len(active) == 0

    def test_get_active_plugins_excludes_failed(self):
        registry = PluginRegistry()
        p1 = DummyPlugin(name="good")
        p2 = DummyPlugin(name="bad")
        registry.register(p1, "builtin")
        registry.register(p2, "builtin")
        registry.mark_failed("bad", "error")

        active = registry.get_active_plugins()
        assert len(active) == 1
        assert active[0].name == "good"

    def test_set_frequency(self):
        registry = PluginRegistry()
        plugin = DummyPlugin(name="test")
        registry.register(plugin, "builtin", frequency=50)

        registry.set_frequency("test", 80)
        assert registry.get_plugin("test").frequency == 80

    def test_get_all_plugins_includes_failed(self):
        registry = PluginRegistry()
        p1 = DummyPlugin(name="good")
        p2 = DummyPlugin(name="bad")
        registry.register(p1, "builtin")
        registry.register(p2, "builtin")
        registry.mark_failed("bad", "error")

        all_plugins = registry.get_all_plugins()
        assert len(all_plugins) == 2

    def test_has_plugin_false_for_unknown(self):
        registry = PluginRegistry()
        assert registry.has_plugin("nonexistent") is False

    def test_get_plugin_returns_none_for_unknown(self):
        registry = PluginRegistry()
        assert registry.get_plugin("nonexistent") is None


class TestUserPluginOverrideProperty:
    """Property 3: User Plugin Override.

    For any plugin name that exists in both the built-in and user plugin
    directories, the Plugin_Registry SHALL contain only the user plugin
    instance for that name, and the built-in version SHALL be replaced.

    **Validates: Requirements 1.5**
    """

    @given(name=valid_plugin_names, frequency=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_user_override_replaces_builtin(self, name, frequency):
        """For any valid plugin name, overriding with a user plugin replaces the built-in."""
        # Feature: plugin-system, Property 3: User Plugin Override
        registry = PluginRegistry()
        builtin = DummyPlugin(name=name, description="Built-in version")
        user = DummyPlugin(name=name, description="User version")

        registry.register(builtin, "builtin", frequency=frequency)
        registry.override_plugin(name, user, "user")

        # Registry contains only one entry for this name
        assert len(registry) == 1
        entry = registry.get_plugin(name)
        # The user plugin instance is stored, not the built-in
        assert entry.plugin is user
        assert entry.source == "user"
        # Built-in is no longer accessible
        assert entry.plugin is not builtin

    @given(name=valid_plugin_names, frequency=st.integers(min_value=0, max_value=100))
    @settings(max_examples=100)
    def test_override_preserves_original_frequency(self, name, frequency):
        """For any override, the original frequency is preserved."""
        # Feature: plugin-system, Property 3: User Plugin Override
        registry = PluginRegistry()
        builtin = DummyPlugin(name=name)
        user = DummyPlugin(name=name)

        registry.register(builtin, "builtin", frequency=frequency)
        registry.override_plugin(name, user, "user")

        entry = registry.get_plugin(name)
        assert entry.frequency == frequency

    @given(
        names=st.lists(valid_plugin_names, min_size=2, max_size=10, unique=True),
        override_index=st.integers(min_value=0),
    )
    @settings(max_examples=100)
    def test_override_only_affects_target_plugin(self, names, override_index):
        """Overriding one plugin does not affect other registered plugins."""
        # Feature: plugin-system, Property 3: User Plugin Override
        override_index = override_index % len(names)
        registry = PluginRegistry()

        # Register all as built-in
        plugins = {}
        for n in names:
            p = DummyPlugin(name=n, description=f"builtin-{n}")
            plugins[n] = p
            registry.register(p, "builtin", frequency=50)

        # Override one plugin
        target_name = names[override_index]
        user_plugin = DummyPlugin(name=target_name, description=f"user-{target_name}")
        registry.override_plugin(target_name, user_plugin, "user")

        # Verify only the target was replaced
        for n in names:
            entry = registry.get_plugin(n)
            if n == target_name:
                assert entry.plugin is user_plugin
                assert entry.source == "user"
            else:
                assert entry.plugin is plugins[n]
                assert entry.source == "builtin"

    @given(name=valid_plugin_names)
    @settings(max_examples=100)
    def test_overridden_plugin_remains_in_active_list(self, name):
        """After override, the plugin is still available (not failed)."""
        # Feature: plugin-system, Property 3: User Plugin Override
        registry = PluginRegistry()
        builtin = DummyPlugin(name=name)
        user = DummyPlugin(name=name)

        registry.register(builtin, "builtin")
        registry.override_plugin(name, user, "user")

        active = registry.get_active_plugins()
        assert len(active) == 1
        assert active[0].plugin is user
        assert active[0].state == "available"
