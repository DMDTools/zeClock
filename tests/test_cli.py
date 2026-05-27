"""Unit tests for CLI argument handling.

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6

Tests the --list-plugins, --plugins, and --plugin-config CLI arguments
by exercising the helper functions _handle_list_plugins() and
_handle_plugins_override() directly, and using subprocess for exit code tests.
"""

import logging
import subprocess
import sys
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from zeclock.plugin_manager import PluginManager
from zeclock.plugin_registry import PluginRegistry
from tests.conftest import DummyPlugin


# --- Helpers ---


def make_args(list_plugins=False, plugins=None, plugin_config=None):
    """Create a Namespace mimicking parsed CLI arguments."""
    return Namespace(
        list_plugins=list_plugins,
        plugins=plugins,
        plugin_config=plugin_config,
    )


def build_manager_with_plugins(plugin_specs):
    """Create a PluginManager with pre-registered plugins.

    Args:
        plugin_specs: List of (name, description, frequency) tuples.

    Returns:
        Configured PluginManager instance.
    """
    manager = PluginManager(width=128, height=32)
    for name, description, frequency in plugin_specs:
        plugin = DummyPlugin(name=name, description=description)
        manager.registry.register(plugin, "builtin", frequency=frequency)
    return manager


# --- Tests for --list-plugins output format (Requirement 7.1) ---


class TestListPluginsOutput:
    """Test --list-plugins output format: one line per plugin with name, description, status."""

    def test_list_plugins_output_format(self, capsys):
        """Each line contains name, description, and active status separated by tabs."""
        from zeclock.clock import _handle_list_plugins

        args = make_args(list_plugins=True, plugin_config=None)

        # Mock the PluginManager to avoid filesystem access
        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation plugin", 70),
            ("weather", "Weather display plugin", 30),
        ])

        with patch("zeclock.plugin_manager.PluginManager", return_value=manager):
            with patch("asyncio.run"):
                _handle_list_plugins(args)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert len(lines) == 2

        # Each line should have 3 tab-separated fields
        for line in lines:
            parts = line.split("\t")
            assert len(parts) == 3, f"Expected 3 tab-separated fields, got: {line}"

        # Verify content
        assert "pinball" in lines[0]
        assert "Pinball animation plugin" in lines[0]
        assert "active" in lines[0]

        assert "weather" in lines[1]
        assert "Weather display plugin" in lines[1]
        assert "active" in lines[1]

    def test_list_plugins_shows_inactive_for_failed(self, capsys):
        """Failed plugins show 'inactive' status."""
        from zeclock.clock import _handle_list_plugins

        args = make_args(list_plugins=True, plugin_config=None)

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation plugin", 100),
            ("broken", "A broken plugin", 50),
        ])
        manager.registry.mark_failed("broken", "init error")

        with patch("zeclock.plugin_manager.PluginManager", return_value=manager):
            with patch("asyncio.run"):
                _handle_list_plugins(args)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert len(lines) == 2

        # Find the broken plugin line
        broken_line = [l for l in lines if "broken" in l][0]
        assert "inactive" in broken_line

        # Pinball should be active
        pinball_line = [l for l in lines if "pinball" in l][0]
        assert "active" in pinball_line

    def test_list_plugins_no_plugins_discovered(self, capsys):
        """When no plugins are discovered, prints informational message."""
        from zeclock.clock import _handle_list_plugins

        args = make_args(list_plugins=True, plugin_config=None)

        manager = PluginManager(width=128, height=32)
        # No plugins registered

        with patch("zeclock.plugin_manager.PluginManager", return_value=manager):
            with patch("asyncio.run"):
                _handle_list_plugins(args)

        captured = capsys.readouterr()
        assert "No plugins discovered" in captured.out


# --- Tests for --list-plugins exit code (Requirement 7.1) ---


class TestListPluginsExitCode:
    """Test --list-plugins exits with code 0."""

    def test_list_plugins_exits_zero(self):
        """--list-plugins should exit with code 0."""
        # Use subprocess to test the actual exit code
        result = subprocess.run(
            [sys.executable, "-m", "zeclock.clock", "--list-plugins"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0


# --- Tests for --plugins frequency assignment (Requirement 7.2) ---


class TestPluginsFrequencyAssignment:
    """Test --plugins assigns equal frequency (100/N for N plugins)."""

    def test_two_plugins_get_50_each(self):
        """Two plugins via --plugins each get frequency 50."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
            ("weather", "Weather display", 100),
        ])

        args = make_args(plugins="pinball,weather")
        result = _handle_plugins_override(args, manager)

        assert result is True
        assert manager.registry.get_plugin("pinball").frequency == 50
        assert manager.registry.get_plugin("weather").frequency == 50

    def test_three_plugins_get_33_each(self):
        """Three plugins via --plugins each get frequency 33 (100//3)."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("alpha", "Alpha plugin", 100),
            ("beta", "Beta plugin", 100),
            ("gamma", "Gamma plugin", 100),
        ])

        args = make_args(plugins="alpha,beta,gamma")
        result = _handle_plugins_override(args, manager)

        assert result is True
        assert manager.registry.get_plugin("alpha").frequency == 33
        assert manager.registry.get_plugin("beta").frequency == 33
        assert manager.registry.get_plugin("gamma").frequency == 33

    def test_single_plugin_gets_100(self):
        """Single plugin via --plugins gets frequency 100."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 50),
            ("weather", "Weather display", 50),
        ])

        args = make_args(plugins="pinball")
        result = _handle_plugins_override(args, manager)

        assert result is True
        assert manager.registry.get_plugin("pinball").frequency == 100
        # Other plugins should have frequency 0
        assert manager.registry.get_plugin("weather").frequency == 0

    def test_plugins_override_zeroes_out_unspecified(self):
        """Plugins not in --plugins list get frequency 0."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 70),
            ("weather", "Weather display", 30),
            ("custom", "Custom plugin", 50),
        ])

        args = make_args(plugins="pinball,weather")
        result = _handle_plugins_override(args, manager)

        assert result is True
        assert manager.registry.get_plugin("pinball").frequency == 50
        assert manager.registry.get_plugin("weather").frequency == 50
        assert manager.registry.get_plugin("custom").frequency == 0


# --- Tests for --plugin-config with missing file (Requirement 7.6) ---


class TestPluginConfigMissingFile:
    """Test --plugin-config with missing file exits non-zero."""

    def test_missing_config_file_exits_nonzero(self):
        """--plugin-config with non-existent path exits with non-zero code."""
        result = subprocess.run(
            [
                sys.executable, "-m", "zeclock.clock",
                "--plugin-config", "/tmp/nonexistent_zeclock_config_12345.yaml",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    def test_missing_config_file_logs_error(self):
        """--plugin-config with non-existent path outputs error message."""
        result = subprocess.run(
            [
                sys.executable, "-m", "zeclock.clock",
                "--plugin-config", "/tmp/nonexistent_zeclock_config_12345.yaml",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should mention the file path in stderr
        assert "nonexistent_zeclock_config_12345.yaml" in result.stderr


# --- Tests for --plugins with all unrecognized names (Requirement 7.4) ---


class TestPluginsAllUnrecognized:
    """Test --plugins with all unrecognized names falls back to pinball."""

    def test_all_unrecognized_returns_false(self):
        """When all --plugins names are unrecognized, returns False (fallback)."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
        ])

        args = make_args(plugins="nonexistent-a,nonexistent-b")
        result = _handle_plugins_override(args, manager)

        assert result is False

    def test_all_unrecognized_logs_error(self, caplog):
        """When all --plugins names are unrecognized, logs an error."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
        ])

        args = make_args(plugins="ghost,phantom")

        with caplog.at_level(logging.ERROR):
            result = _handle_plugins_override(args, manager)

        assert result is False
        assert any("unrecognized" in r.message.lower() for r in caplog.records)


# --- Tests for --plugins with mix of valid/invalid names (Requirement 7.3) ---


class TestPluginsMixedValidInvalid:
    """Test --plugins with mix of valid/invalid names logs warning for invalid."""

    def test_mixed_names_logs_warning_for_invalid(self, caplog):
        """Invalid names in --plugins produce a warning log."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
            ("weather", "Weather display", 100),
        ])

        args = make_args(plugins="pinball,nonexistent,weather")

        with caplog.at_level(logging.WARNING):
            result = _handle_plugins_override(args, manager)

        assert result is True
        # Warning logged for the unrecognized name
        assert any("nonexistent" in r.message for r in caplog.records)

    def test_mixed_names_only_valid_get_frequency(self):
        """Only valid names from --plugins get frequency assigned."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
            ("weather", "Weather display", 100),
            ("custom", "Custom plugin", 100),
        ])

        args = make_args(plugins="pinball,nonexistent,weather")

        result = _handle_plugins_override(args, manager)

        assert result is True
        # Only 2 valid plugins, so each gets 50
        assert manager.registry.get_plugin("pinball").frequency == 50
        assert manager.registry.get_plugin("weather").frequency == 50
        # Unspecified valid plugin gets 0
        assert manager.registry.get_plugin("custom").frequency == 0

    def test_multiple_invalid_names_all_warned(self, caplog):
        """Multiple invalid names each produce a warning."""
        from zeclock.clock import _handle_plugins_override

        manager = build_manager_with_plugins([
            ("pinball", "Pinball animation", 100),
        ])

        args = make_args(plugins="pinball,ghost,phantom,specter")

        with caplog.at_level(logging.WARNING):
            result = _handle_plugins_override(args, manager)

        assert result is True
        warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ghost" in w for w in warnings)
        assert any("phantom" in w for w in warnings)
        assert any("specter" in w for w in warnings)
