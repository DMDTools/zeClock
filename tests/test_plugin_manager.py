"""Unit tests for PluginManager discover_and_load functionality."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from zeclock.plugin_manager import PluginManager


@pytest.fixture
def tmp_user_dir(tmp_path):
    """Create a temporary user plugin directory."""
    user_dir = tmp_path / ".zeclock" / "plugins"
    user_dir.mkdir(parents=True)
    return user_dir


@pytest.fixture
def tmp_config_path(tmp_path):
    """Create a temporary config path."""
    config_dir = tmp_path / ".zeclock" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "plugins.yaml"
    return config_path


def write_plugin_file(directory: Path, filename: str, content: str) -> Path:
    """Helper to write a plugin file."""
    filepath = directory / filename
    filepath.write_text(content)
    return filepath


VALID_PLUGIN_TEMPLATE = '''
"""A valid test plugin."""
from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class {class_name}(ClockPlugin):
    """A test plugin."""

    @property
    def name(self) -> str:
        return "{plugin_name}"

    @property
    def description(self) -> str:
        return "A test plugin for unit testing"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        self._config = config

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (255, 0, 0))

    async def cleanup(self) -> None:
        pass
'''

INVALID_NAME_PLUGIN = '''
"""A plugin with an invalid name."""
from typing import Optional
from PIL import Image
from zeclock.plugins.base import ClockPlugin


class BadNamePlugin(ClockPlugin):
    @property
    def name(self) -> str:
        return "INVALID_UPPERCASE"

    @property
    def description(self) -> str:
        return "Plugin with bad name"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return None

    async def cleanup(self) -> None:
        pass
'''

SYNTAX_ERROR_PLUGIN = '''
"""A plugin with a syntax error."""
def this_is_broken(
    # missing closing paren and colon
'''

IMPORT_ERROR_PLUGIN = '''
"""A plugin that imports a non-existent module."""
import nonexistent_module_xyz_12345

from zeclock.plugins.base import ClockPlugin
'''


class TestPluginManagerInit:
    """Tests for PluginManager initialization."""

    def test_init_sets_dimensions(self):
        pm = PluginManager(128, 32)
        assert pm.width == 128
        assert pm.height == 32

    def test_init_creates_registry(self):
        pm = PluginManager(128, 32)
        assert pm.registry is not None

    def test_init_creates_config(self):
        pm = PluginManager(128, 32)
        assert pm.config is not None

    def test_init_creates_helpers(self):
        pm = PluginManager(128, 32)
        assert pm._helpers is not None
        assert pm._helpers.width == 128
        assert pm._helpers.height == 32

    def test_init_with_custom_config_path(self, tmp_path):
        config_path = tmp_path / "custom.yaml"
        pm = PluginManager(128, 32, config_path=config_path)
        assert pm.config.path == config_path

    def test_init_with_custom_resources_path(self, tmp_path):
        resources = tmp_path / "resources"
        pm = PluginManager(128, 32, resources_path=resources)
        assert pm._resources_path == resources


class TestDiscoverAndLoad:
    """Tests for the discover_and_load method."""

    @pytest.mark.asyncio
    async def test_creates_user_plugin_dir_if_missing(self, tmp_path, tmp_config_path):
        """User plugin directory is created if it doesn't exist."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        assert not user_dir.exists()

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            await pm.discover_and_load()

        assert user_dir.exists()

    @pytest.mark.asyncio
    async def test_loads_valid_user_plugin(self, tmp_path, tmp_config_path):
        """A valid plugin file in user directory is discovered and registered."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        content = VALID_PLUGIN_TEMPLATE.format(
            class_name="MyTestPlugin", plugin_name="my-test-plugin"
        )
        write_plugin_file(user_dir, "my_test_plugin.py", content)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            await pm.discover_and_load()

        assert pm.registry.has_plugin("my-test-plugin")

    @pytest.mark.asyncio
    async def test_skips_syntax_error_file(self, tmp_path, tmp_config_path, caplog):
        """Files with syntax errors are skipped with a WARNING log."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        write_plugin_file(user_dir, "broken_plugin.py", SYNTAX_ERROR_PLUGIN)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            with caplog.at_level(logging.WARNING):
                await pm.discover_and_load()

        assert not pm.registry.has_plugin("broken")
        assert any("Failed to import" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_skips_import_error_file(self, tmp_path, tmp_config_path, caplog):
        """Files with import errors are skipped with a WARNING log."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        write_plugin_file(user_dir, "bad_import_plugin.py", IMPORT_ERROR_PLUGIN)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            with caplog.at_level(logging.WARNING):
                await pm.discover_and_load()

        assert any("Failed to import" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_skips_invalid_plugin_name(self, tmp_path, tmp_config_path, caplog):
        """Plugins with invalid names are skipped with a WARNING log."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        write_plugin_file(user_dir, "bad_name_plugin.py", INVALID_NAME_PLUGIN)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            with caplog.at_level(logging.WARNING):
                await pm.discover_and_load()

        assert not pm.registry.has_plugin("INVALID_UPPERCASE")
        assert any("invalid name" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_user_plugin_overrides_builtin(self, tmp_path, tmp_config_path, caplog):
        """User plugin with same name as built-in overrides it."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        # Create a "builtin" directory with a plugin
        builtin_dir = tmp_path / "builtin_plugins"
        builtin_dir.mkdir()
        builtin_content = VALID_PLUGIN_TEMPLATE.format(
            class_name="BuiltinPlugin", plugin_name="shared-name"
        )
        write_plugin_file(builtin_dir, "shared_plugin.py", builtin_content)

        # Create a user plugin with the same name
        user_content = VALID_PLUGIN_TEMPLATE.format(
            class_name="UserPlugin", plugin_name="shared-name"
        )
        write_plugin_file(user_dir, "shared_plugin.py", user_content)

        pm = PluginManager(128, 32, config_path=tmp_config_path)

        # Manually load from builtin dir first, then user dir
        pm.config.load()
        pm._load_plugins_from_directory(builtin_dir, source="builtin")
        pm._load_plugins_from_directory(user_dir, source="user")

        assert pm.registry.has_plugin("shared-name")
        entry = pm.registry.get_plugin("shared-name")
        assert entry.source == "user"

    @pytest.mark.asyncio
    async def test_skips_init_and_helper_files(self, tmp_path, tmp_config_path):
        """__init__.py, base.py, helpers.py are not loaded as plugins."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        # Write files that should be skipped
        write_plugin_file(user_dir, "__init__.py", "# init")
        write_plugin_file(user_dir, "_private.py", "# private")

        # Write a valid plugin
        content = VALID_PLUGIN_TEMPLATE.format(
            class_name="RealPlugin", plugin_name="real-plugin"
        )
        write_plugin_file(user_dir, "real_plugin.py", content)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            await pm.discover_and_load()

        assert pm.registry.has_plugin("real-plugin")
        # __init__.py and _private.py should NOT be loaded as plugins
        all_names = {e.name for e in pm.registry.get_all_plugins()}
        assert "real-plugin" in all_names
        # No plugin named after the skipped files
        assert "init" not in all_names
        assert "_private" not in all_names

    @pytest.mark.asyncio
    async def test_multiple_plugins_loaded(self, tmp_path, tmp_config_path):
        """Multiple valid plugins in the same directory are all loaded."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        for i in range(3):
            content = VALID_PLUGIN_TEMPLATE.format(
                class_name=f"Plugin{i}", plugin_name=f"plugin-{i}"
            )
            write_plugin_file(user_dir, f"plugin_{i}.py", content)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            await pm.discover_and_load()

        for i in range(3):
            assert pm.registry.has_plugin(f"plugin-{i}")

    @pytest.mark.asyncio
    async def test_continues_loading_after_error(self, tmp_path, tmp_config_path):
        """Loading continues even if one file has errors."""
        user_dir = tmp_path / ".zeclock" / "plugins"
        user_dir.mkdir(parents=True)

        # Write a broken file first (alphabetically)
        write_plugin_file(user_dir, "aaa_broken.py", SYNTAX_ERROR_PLUGIN)

        # Write a valid plugin after
        content = VALID_PLUGIN_TEMPLATE.format(
            class_name="GoodPlugin", plugin_name="good-plugin"
        )
        write_plugin_file(user_dir, "zzz_good.py", content)

        pm = PluginManager(128, 32, config_path=tmp_config_path)
        with patch("zeclock.plugin_manager.Path.home", return_value=tmp_path):
            await pm.discover_and_load()

        assert pm.registry.has_plugin("good-plugin")


class TestPluginConfigWithHelpers:
    """Tests for get_plugin_config_with_helpers."""

    def test_injects_helpers_key(self, tmp_config_path):
        """The _helpers key is injected into plugin config."""
        pm = PluginManager(128, 32, config_path=tmp_config_path)
        config = pm.get_plugin_config_with_helpers("any-plugin")
        assert "_helpers" in config
        assert config["_helpers"] is pm._helpers

    def test_preserves_existing_settings(self, tmp_path):
        """Existing plugin settings are preserved alongside _helpers."""
        import yaml

        config_dir = tmp_path / ".zeclock" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "plugins.yaml"

        config_data = {
            "clock_display_seconds": 5,
            "plugins": [
                {
                    "name": "weather",
                    "frequency": 50,
                    "settings": {"latitude": 48.85, "longitude": 2.35},
                }
            ],
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        pm = PluginManager(128, 32, config_path=config_path)
        pm.config.load()

        config = pm.get_plugin_config_with_helpers("weather")
        assert config["_helpers"] is pm._helpers
        assert config["latitude"] == 48.85
        assert config["longitude"] == 2.35
