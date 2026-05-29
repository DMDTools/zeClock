"""Unit tests for the ClockPlugin interface contract.

Validates: Requirements 2.1-2.9
"""

import asyncio

import pytest
from PIL import Image

from zeclock.plugins.base import ClockPlugin
from tests.conftest import DummyPlugin, FailingPlugin


class TestClockPluginInterface:
    """Tests that the ClockPlugin ABC enforces the contract."""

    def test_cannot_instantiate_abc_directly(self):
        """ClockPlugin cannot be instantiated without implementing all methods."""
        with pytest.raises(TypeError):
            ClockPlugin()  # type: ignore

    def test_dummy_plugin_implements_interface(self):
        """A properly implemented plugin can be instantiated."""
        plugin = DummyPlugin()
        assert plugin.name == "test-plugin"
        assert plugin.description == "A test plugin"
        assert plugin.frame_delay_ms == 40

    @pytest.mark.asyncio
    async def test_initialize_sets_config(self):
        """initialize() receives and stores config."""
        plugin = DummyPlugin()
        await plugin.initialize({"key": "value"})
        assert plugin._initialized is True
        assert plugin._config == {"key": "value"}

    @pytest.mark.asyncio
    async def test_render_frame_returns_image(self):
        """render_frame() returns a PIL Image in RGB mode."""
        plugin = DummyPlugin(frames_to_render=3)
        await plugin.initialize({})

        frame = await plugin.render_frame(128, 32)
        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    @pytest.mark.asyncio
    async def test_render_frame_signals_completion(self):
        """render_frame() returns None when done."""
        plugin = DummyPlugin(frames_to_render=2)
        await plugin.initialize({})

        frame1 = await plugin.render_frame(128, 32)
        assert frame1 is not None
        frame2 = await plugin.render_frame(128, 32)
        assert frame2 is not None
        frame3 = await plugin.render_frame(128, 32)
        assert frame3 is None

    @pytest.mark.asyncio
    async def test_cleanup_called(self):
        """cleanup() is called and marks the plugin as cleaned up."""
        plugin = DummyPlugin()
        await plugin.initialize({})
        await plugin.cleanup()
        assert plugin._cleaned_up is True

    @pytest.mark.asyncio
    async def test_failing_plugin_raises(self):
        """A failing plugin raises on render_frame."""
        plugin = FailingPlugin()
        await plugin.initialize({})

        with pytest.raises(RuntimeError):
            await plugin.render_frame(128, 32)


class TestPluginSubclassing:
    """Tests that incomplete implementations are caught."""

    def test_missing_name_property(self):
        """Plugin without name property cannot be instantiated."""
        with pytest.raises(TypeError):

            class BadPlugin(ClockPlugin):
                @property
                def description(self) -> str:
                    return "test"

                @property
                def frame_delay_ms(self) -> int:
                    return 40

                async def initialize(self, config: dict) -> None:
                    pass

                async def render_frame(self, width, height):
                    return None

                async def cleanup(self) -> None:
                    pass

            BadPlugin()  # type: ignore

    def test_missing_render_frame(self):
        """Plugin without render_frame cannot be instantiated."""
        with pytest.raises(TypeError):

            class BadPlugin(ClockPlugin):
                @property
                def name(self) -> str:
                    return "bad"

                @property
                def description(self) -> str:
                    return "test"

                @property
                def frame_delay_ms(self) -> int:
                    return 40

                async def initialize(self, config: dict) -> None:
                    pass

                async def cleanup(self) -> None:
                    pass

            BadPlugin()  # type: ignore
