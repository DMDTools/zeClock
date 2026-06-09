"""Unit tests for PluginManager unconfigured plugin handling (Task 2)."""

import asyncio
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import ClockPlugin, PluginNotConfiguredError


class FakeUnconfiguredPlugin(ClockPlugin):
    """A plugin that raises PluginNotConfiguredError during initialize."""

    @property
    def name(self) -> str:
        return "unconfigured-plugin"

    @property
    def description(self) -> str:
        return "A plugin that is not configured"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def initialize(self, config: dict) -> None:
        raise PluginNotConfiguredError("API key not set")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


class FakeFailingPlugin(ClockPlugin):
    """A plugin that raises a generic Exception during initialize."""

    @property
    def name(self) -> str:
        return "failing-plugin"

    @property
    def description(self) -> str:
        return "A plugin that fails to initialize"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def initialize(self, config: dict) -> None:
        raise RuntimeError("Something went wrong")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


class FakeWorkingPlugin(ClockPlugin):
    """A plugin that initializes successfully."""

    @property
    def name(self) -> str:
        return "working-plugin"

    @property
    def description(self) -> str:
        return "A plugin that works fine"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (255, 0, 0))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager instance for testing."""
    config_path = tmp_path / "plugins.yaml"
    pm = PluginManager(128, 32, config_path=config_path)
    return pm


class TestActivatePluginUnconfigured:
    """Tests for activate_plugin() handling PluginNotConfiguredError."""

    @pytest.mark.asyncio
    async def test_unconfigured_plugin_not_marked_as_failed(self, plugin_manager):
        """A plugin raising PluginNotConfiguredError is NOT marked as failed."""
        plugin = FakeUnconfiguredPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        result = await plugin_manager.activate_plugin(plugin)

        assert result is True
        # Should NOT be marked as failed
        entry = plugin_manager.registry.get_plugin("unconfigured-plugin")
        assert entry.state != "failed"

    @pytest.mark.asyncio
    async def test_unconfigured_plugin_sets_unconfigured_flag(self, plugin_manager):
        """A plugin raising PluginNotConfiguredError gets _unconfigured = True."""
        plugin = FakeUnconfiguredPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert plugin._unconfigured is True

    @pytest.mark.asyncio
    async def test_unconfigured_plugin_returns_true(self, plugin_manager):
        """activate_plugin() returns True for unconfigured plugins (kept in rotation)."""
        plugin = FakeUnconfiguredPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        result = await plugin_manager.activate_plugin(plugin)

        assert result is True

    @pytest.mark.asyncio
    async def test_unconfigured_plugin_set_as_active(self, plugin_manager):
        """An unconfigured plugin is set as the active plugin."""
        plugin = FakeUnconfiguredPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        await plugin_manager.activate_plugin(plugin)

        assert plugin_manager.active_plugin is plugin

    @pytest.mark.asyncio
    async def test_generic_exception_marks_as_failed(self, plugin_manager):
        """A plugin raising a generic Exception IS marked as failed."""
        plugin = FakeFailingPlugin()
        plugin_manager.registry.register(plugin, "builtin")

        result = await plugin_manager.activate_plugin(plugin)

        assert result is False
        entry = plugin_manager.registry.get_plugin("failing-plugin")
        assert entry.state == "failed"


class TestGetFrameUnconfigured:
    """Tests for get_frame() with unconfigured plugins."""

    @pytest.mark.asyncio
    async def test_get_frame_returns_image_for_unconfigured(self, plugin_manager):
        """get_frame() returns a configure message image for unconfigured plugins."""
        plugin = FakeUnconfiguredPlugin()
        plugin_manager.registry.register(plugin, "builtin")
        await plugin_manager.activate_plugin(plugin)

        frame = await plugin_manager.get_frame()

        assert frame is not None
        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    @pytest.mark.asyncio
    async def test_get_frame_does_not_call_render_frame_for_unconfigured(
        self, plugin_manager
    ):
        """get_frame() does NOT call plugin.render_frame() if plugin is unconfigured."""
        plugin = FakeUnconfiguredPlugin()
        plugin.render_frame = AsyncMock()
        plugin_manager.registry.register(plugin, "builtin")
        await plugin_manager.activate_plugin(plugin)

        await plugin_manager.get_frame()

        plugin.render_frame.assert_not_called()


class TestRenderConfigureMessage:
    """Tests for _render_configure_message()."""

    def test_truncates_long_names(self, plugin_manager):
        """Plugin names longer than 12 chars are truncated."""
        frame = plugin_manager._render_configure_message(
            "very-long-plugin-name-here"
        )

        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    def test_short_name_not_truncated(self, plugin_manager):
        """Plugin names 12 chars or shorter are NOT truncated."""
        # This just verifies it produces a valid image without error
        frame = plugin_manager._render_configure_message("short")

        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    def test_returns_valid_pil_image(self, plugin_manager):
        """_render_configure_message() always returns a valid PIL Image."""
        frame = plugin_manager._render_configure_message("test-plugin")

        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    def test_exactly_12_chars_not_truncated(self, plugin_manager):
        """A name exactly 12 characters long is not truncated."""
        name = "abcdefghijkl"  # exactly 12 chars
        assert len(name) == 12
        frame = plugin_manager._render_configure_message(name)

        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
