"""Tests for plugin render duration bounded behavior (Property 10).

Validates: Requirements 3.4, 5.5

Property 10: Plugin Render Duration Bounded
For any active plugin, the Plugin_Manager SHALL stop calling render_frame()
when either the plugin returns None or 30 seconds have elapsed since activation,
whichever occurs first. The plugin SHALL NOT be called for additional frames
after either condition is met.
"""

import time
from typing import Optional
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import ClockPlugin

# --- Test Fixtures ---


class CountingPlugin(ClockPlugin):
    """A plugin that counts render_frame calls and optionally returns None after N frames."""

    def __init__(self, frames_before_none: Optional[int] = None):
        self._frames_before_none = frames_before_none
        self.render_call_count = 0
        self._initialized = False

    @property
    def name(self) -> str:
        return "counting-plugin"

    @property
    def description(self) -> str:
        return "A plugin that counts render calls"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        self._initialized = True
        self.render_call_count = 0

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        self.render_call_count += 1
        if (
            self._frames_before_none is not None
            and self.render_call_count > self._frames_before_none
        ):
            return None
        return Image.new("RGB", (width, height), (255, 128, 0))

    async def cleanup(self) -> None:
        pass


class InfinitePlugin(ClockPlugin):
    """A plugin that never returns None (renders forever)."""

    def __init__(self):
        self.render_call_count = 0

    @property
    def name(self) -> str:
        return "infinite-plugin"

    @property
    def description(self) -> str:
        return "A plugin that renders forever"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        self.render_call_count = 0

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        self.render_call_count += 1
        return Image.new("RGB", (width, height), (0, 255, 0))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager with a temporary config path."""
    config_dir = tmp_path / ".zeclock" / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "plugins.yaml"
    return PluginManager(128, 32, config_path=config_path)


# --- Unit Tests: Plugin stopped after 30 seconds max ---


class TestPluginStoppedAfter30Seconds:
    """Test that should_deactivate() returns True after 30 seconds."""

    @pytest.mark.asyncio
    async def test_should_deactivate_after_30_seconds(self, plugin_manager):
        """Plugin is deactivated when 30 seconds have elapsed."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Simulate 30 seconds elapsed
        plugin_manager.plugin_start_time = time.time() - 30

        assert plugin_manager.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_should_not_deactivate_before_30_seconds(self, plugin_manager):
        """Plugin is NOT deactivated before 30 seconds."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Simulate 29 seconds elapsed
        plugin_manager.plugin_start_time = time.time() - 29

        assert plugin_manager.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_should_deactivate_at_exactly_30_seconds(self, plugin_manager):
        """Plugin is deactivated at exactly 30 seconds boundary."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Simulate exactly 30 seconds elapsed
        plugin_manager.plugin_start_time = time.time() - 30

        assert plugin_manager.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_should_deactivate_well_past_30_seconds(self, plugin_manager):
        """Plugin is deactivated when well past 30 seconds."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Simulate 60 seconds elapsed
        plugin_manager.plugin_start_time = time.time() - 60

        assert plugin_manager.should_deactivate() is True


# --- Unit Tests: Plugin stopped when render_frame returns None ---


class TestPluginStoppedOnNone:
    """Test that render_frame returning None signals completion."""

    @pytest.mark.asyncio
    async def test_get_frame_returns_none_on_completion(self, plugin_manager):
        """get_frame() returns None when plugin signals completion."""
        plugin = CountingPlugin(frames_before_none=3)
        await plugin_manager.activate_plugin(plugin)

        # Render 3 valid frames
        for _ in range(3):
            frame = await plugin_manager.get_frame()
            assert frame is not None

        # 4th call should return None (completion signal)
        frame = await plugin_manager.get_frame()
        assert frame is None

    @pytest.mark.asyncio
    async def test_plugin_returns_none_immediately(self, plugin_manager):
        """Plugin that returns None on first frame signals immediate completion."""
        plugin = CountingPlugin(frames_before_none=0)
        await plugin_manager.activate_plugin(plugin)

        frame = await plugin_manager.get_frame()
        assert frame is None

    @pytest.mark.asyncio
    async def test_render_count_matches_frames_before_none(self, plugin_manager):
        """Plugin render_frame is called exactly frames_before_none + 1 times."""
        plugin = CountingPlugin(frames_before_none=5)
        await plugin_manager.activate_plugin(plugin)

        frames_received = 0
        while True:
            frame = await plugin_manager.get_frame()
            if frame is None:
                break
            frames_received += 1

        assert frames_received == 5
        # render_frame was called 6 times: 5 valid + 1 returning None
        assert plugin.render_call_count == 6


# --- Unit Tests: No additional frames requested after either condition ---


class TestNoAdditionalFramesAfterCondition:
    """Test that no additional frames are requested after deactivation conditions."""

    @pytest.mark.asyncio
    async def test_no_frames_after_deactivation(self, plugin_manager):
        """After deactivate_plugin(), get_frame() returns None without calling plugin."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Get one frame
        frame = await plugin_manager.get_frame()
        assert frame is not None
        assert plugin.render_call_count == 1

        # Deactivate
        await plugin_manager.deactivate_plugin()

        # No more frames should be produced
        frame = await plugin_manager.get_frame()
        assert frame is None
        # render_frame should not have been called again
        assert plugin.render_call_count == 1

    @pytest.mark.asyncio
    async def test_render_loop_stops_on_none(self, plugin_manager):
        """Simulated render loop stops calling render_frame after None."""
        plugin = CountingPlugin(frames_before_none=3)
        await plugin_manager.activate_plugin(plugin)

        # Simulate the render loop
        frames_rendered = 0
        while not plugin_manager.should_deactivate():
            frame = await plugin_manager.get_frame()
            if frame is None:
                break
            frames_rendered += 1

        # Should have rendered exactly 3 frames
        assert frames_rendered == 3
        # Plugin should not be called after None
        call_count_at_stop = plugin.render_call_count
        assert call_count_at_stop == 4  # 3 valid + 1 None

    @pytest.mark.asyncio
    async def test_render_loop_stops_on_time_limit(self, plugin_manager):
        """Simulated render loop stops when 30 seconds elapsed."""
        plugin = InfinitePlugin()
        await plugin_manager.activate_plugin(plugin)

        # Render a few frames
        for _ in range(5):
            frame = await plugin_manager.get_frame()
            assert frame is not None

        # Simulate time passing beyond 30 seconds
        plugin_manager.plugin_start_time = time.time() - 31

        # should_deactivate should now be True
        assert plugin_manager.should_deactivate() is True

        # Record call count before deactivation
        call_count_before = plugin.render_call_count

        # Deactivate
        await plugin_manager.deactivate_plugin()

        # No more frames should be produced
        frame = await plugin_manager.get_frame()
        assert frame is None
        assert plugin.render_call_count == call_count_before

    @pytest.mark.asyncio
    async def test_should_deactivate_false_when_no_active_plugin(self, plugin_manager):
        """should_deactivate() returns False when no plugin is active."""
        assert plugin_manager.should_deactivate() is False


# --- Property-Based Test: Plugin Render Duration Bounded ---
# Feature: plugin-system, Property 10: Plugin Render Duration Bounded


class TestPluginRenderDurationProperty:
    """Property-based tests for plugin render duration bounded behavior.

    **Validates: Requirements 3.4, 5.5**
    """

    @given(
        frames_before_none=st.integers(min_value=0, max_value=50),
        elapsed_seconds=st.floats(
            min_value=0.0, max_value=60.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_plugin_stops_on_none_or_30s(
        self, frames_before_none, elapsed_seconds
    ):
        """For any active plugin, the PluginManager stops calling render_frame()
        when either the plugin returns None or 30 seconds have elapsed since
        activation, whichever occurs first.

        **Validates: Requirements 3.4, 5.5**
        """
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        config_dir = tmp_dir / ".zeclock" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "plugins.yaml"

        pm = PluginManager(128, 32, config_path=config_path)
        plugin = CountingPlugin(frames_before_none=frames_before_none)
        await pm.activate_plugin(plugin)

        # Simulate elapsed time
        pm.plugin_start_time = time.time() - elapsed_seconds

        # Determine expected behavior
        time_expired = elapsed_seconds >= 30.0

        if time_expired:
            # should_deactivate should be True - no more frames should be requested
            assert pm.should_deactivate() is True
        else:
            # Time hasn't expired, so deactivation depends on errors only
            # (not on None return - that's handled by the render loop)
            assert pm.should_deactivate() is False

            # Simulate render loop: get frames until None or should_deactivate
            frames_rendered = 0
            while not pm.should_deactivate():
                frame = await pm.get_frame()
                if frame is None:
                    break
                frames_rendered += 1
                # Safety: prevent infinite loop in test
                if frames_rendered > frames_before_none + 10:
                    break

            # Plugin should have rendered at most frames_before_none frames
            assert frames_rendered <= frames_before_none

    @given(
        elapsed_seconds=st.floats(
            min_value=30.0, max_value=120.0, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_should_deactivate_true_after_30s(self, elapsed_seconds):
        """For any elapsed time >= 30 seconds, should_deactivate() returns True.

        **Validates: Requirements 3.4, 5.5**
        """
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        config_dir = tmp_dir / ".zeclock" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "plugins.yaml"

        pm = PluginManager(128, 32, config_path=config_path)
        plugin = InfinitePlugin()
        await pm.activate_plugin(plugin)

        pm.plugin_start_time = time.time() - elapsed_seconds

        assert pm.should_deactivate() is True

    @given(
        elapsed_seconds=st.floats(
            min_value=0.0, max_value=29.9, allow_nan=False, allow_infinity=False
        ),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_should_deactivate_false_before_30s(self, elapsed_seconds):
        """For any elapsed time < 30 seconds (with no errors), should_deactivate() returns False.

        **Validates: Requirements 3.4, 5.5**
        """
        import tempfile
        from pathlib import Path

        tmp_dir = Path(tempfile.mkdtemp())
        config_dir = tmp_dir / ".zeclock" / "config"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "plugins.yaml"

        pm = PluginManager(128, 32, config_path=config_path)
        plugin = InfinitePlugin()
        await pm.activate_plugin(plugin)

        pm.plugin_start_time = time.time() - elapsed_seconds

        assert pm.should_deactivate() is False
