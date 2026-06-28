"""Unit tests for PluginContext and PLUGIN_API_VERSION."""

from typing import Optional
from unittest.mock import MagicMock

import pytest
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import (
    ClockPlugin,
    ConfigField,
    PLUGIN_API_VERSION,
    PluginContext,
)


class FakeContextPlugin(ClockPlugin):
    """A plugin that stores its config for inspection."""

    @property
    def name(self) -> str:
        return "context-test"

    @property
    def description(self) -> str:
        return "A plugin for testing PluginContext"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def initialize(self, config: dict) -> None:
        self._config = config

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager instance for testing."""
    config_path = tmp_path / "plugins.yaml"
    config_path.write_text(
        "plugins:\n"
        "  - name: context-test\n"
        "    frequency: 100\n"
        "    settings:\n"
        "      api_key: test123\n"
        "      city: Paris\n"
    )
    pm = PluginManager(128, 32, config_path=config_path)
    pm.config.load()
    return pm


class TestPluginAPIVersion:
    """Tests for PLUGIN_API_VERSION constant."""

    def test_plugin_api_version_is_string(self):
        """PLUGIN_API_VERSION is a string."""
        assert isinstance(PLUGIN_API_VERSION, str)

    def test_plugin_api_version_value(self):
        """PLUGIN_API_VERSION equals '1.0'."""
        assert PLUGIN_API_VERSION == "1.0"

    def test_plugin_api_version_importable_from_package(self):
        """PLUGIN_API_VERSION can be imported from zeclock.plugins."""
        from zeclock.plugins import PLUGIN_API_VERSION as version
        assert version == "1.0"


class TestPluginContext:
    """Tests for PluginContext dataclass."""

    def test_plugin_context_importable(self):
        """PluginContext can be imported from zeclock.plugins.base."""
        from zeclock.plugins.base import PluginContext as PC
        assert PC is not None

    def test_plugin_context_importable_from_package(self):
        """PluginContext can be imported from zeclock.plugins."""
        from zeclock.plugins import PluginContext as PC
        assert PC is not None

    def test_plugin_context_instantiation(self):
        """PluginContext can be instantiated with required fields."""
        helpers = MagicMock()
        ctx = PluginContext(helpers=helpers)
        assert ctx.helpers is helpers
        assert ctx.upscale_mode == "epx"
        assert ctx.font == "STANDARD"
        assert ctx.settings == {}

    def test_plugin_context_with_all_fields(self):
        """PluginContext can be instantiated with all fields."""
        helpers = MagicMock()
        settings = {"api_key": "abc123", "city": "Paris"}
        ctx = PluginContext(
            helpers=helpers,
            upscale_mode="hq2x",
            font="MENU",
            settings=settings,
        )
        assert ctx.helpers is helpers
        assert ctx.upscale_mode == "hq2x"
        assert ctx.font == "MENU"
        assert ctx.settings == settings

    @pytest.mark.asyncio
    async def test_config_contains_context_key(self, plugin_manager):
        """get_plugin_config_with_helpers() includes '_context' key."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert "_context" in plugin._config

    @pytest.mark.asyncio
    async def test_context_is_plugin_context_instance(self, plugin_manager):
        """config['_context'] is an instance of PluginContext."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert isinstance(plugin._config["_context"], PluginContext)

    @pytest.mark.asyncio
    async def test_context_helpers_matches_helpers_key(self, plugin_manager):
        """PluginContext.helpers is the same object as config['_helpers']."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        ctx = plugin._config["_context"]
        assert ctx.helpers is plugin._config["_helpers"]

    @pytest.mark.asyncio
    async def test_context_settings_matches_yaml(self, plugin_manager):
        """PluginContext.settings matches the YAML settings for the plugin."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        ctx = plugin._config["_context"]
        assert ctx.settings == {"api_key": "test123", "city": "Paris"}

    @pytest.mark.asyncio
    async def test_backward_compat_helpers_key(self, plugin_manager):
        """config['_helpers'] still exists for backward compatibility."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert "_helpers" in plugin._config
        assert plugin._config["_helpers"] is not None

    @pytest.mark.asyncio
    async def test_backward_compat_upscale_mode_key(self, plugin_manager):
        """config['_upscale_mode'] still exists for backward compatibility."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert "_upscale_mode" in plugin._config
        assert plugin._config["_upscale_mode"] == "epx"

    @pytest.mark.asyncio
    async def test_backward_compat_font_key(self, plugin_manager):
        """config['_font'] still exists for backward compatibility."""
        plugin = FakeContextPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert "_font" in plugin._config
        assert plugin._config["_font"] == "STANDARD"
