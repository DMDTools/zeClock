"""Unit tests for PluginManager frame rendering with error recovery (task 6.3).

Tests cover:
- get_frame() with 2-second timeout on render_frame()
- Holding last good frame on render errors
- Tracking consecutive errors, deactivating after 5 consecutive failures
- should_deactivate(): 30-second max duration or 5 consecutive errors
- deactivate_plugin() calling cleanup()
- is_plugin_active()
"""

import asyncio
import time
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import ClockPlugin

# --- Test fixtures ---


class SuccessPlugin(ClockPlugin):
    """Plugin that always returns a valid frame."""

    def __init__(self):
        self._frame_count = 0

    @property
    def name(self) -> str:
        return "success-plugin"

    @property
    def description(self) -> str:
        return "Always succeeds"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        self._frame_count += 1
        return Image.new("RGB", (width, height), (self._frame_count, 0, 0))

    async def cleanup(self) -> None:
        self.cleaned_up = True


class FailingRenderPlugin(ClockPlugin):
    """Plugin that always raises on render_frame."""

    def __init__(self):
        self.cleanup_called = False

    @property
    def name(self) -> str:
        return "failing-render"

    @property
    def description(self) -> str:
        return "Always fails on render"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        raise RuntimeError("Render failure")

    async def cleanup(self) -> None:
        self.cleanup_called = True


class SlowRenderPlugin(ClockPlugin):
    """Plugin that takes too long to render."""

    @property
    def name(self) -> str:
        return "slow-render"

    @property
    def description(self) -> str:
        return "Slow render"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        await asyncio.sleep(5.0)  # Exceeds 2-second timeout
        return Image.new("RGB", (width, height), (0, 255, 0))

    async def cleanup(self) -> None:
        pass


class CompletingPlugin(ClockPlugin):
    """Plugin that signals completion after N frames."""

    def __init__(self, frames: int = 3):
        self._frames = frames
        self._count = 0

    @property
    def name(self) -> str:
        return "completing-plugin"

    @property
    def description(self) -> str:
        return "Completes after N frames"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        self._count += 1
        if self._count > self._frames:
            return None
        return Image.new("RGB", (width, height), (0, self._count, 0))

    async def cleanup(self) -> None:
        pass


class IntermittentPlugin(ClockPlugin):
    """Plugin that fails intermittently based on a pattern."""

    def __init__(self, pattern: list):
        """Pattern is a list of booleans: True = success, False = fail."""
        self._pattern = pattern
        self._index = 0

    @property
    def name(self) -> str:
        return "intermittent-plugin"

    @property
    def description(self) -> str:
        return "Fails intermittently"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        if self._index >= len(self._pattern):
            return None
        should_succeed = self._pattern[self._index]
        self._index += 1
        if not should_succeed:
            raise RuntimeError("Intermittent failure")
        return Image.new("RGB", (width, height), (0, 0, self._index))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager with temp config."""
    config_path = tmp_path / "plugins.yaml"
    return PluginManager(128, 32, config_path=config_path, resources_path=tmp_path)


# --- Tests for get_frame() ---


class TestGetFrame:
    """Tests for PluginManager.get_frame()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_plugin(self, plugin_manager):
        """get_frame returns None when no plugin is active."""
        assert plugin_manager.active_plugin is None
        result = await plugin_manager.get_frame()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_frame_on_success(self, plugin_manager):
        """get_frame returns the rendered frame on success."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        frame = await plugin_manager.get_frame()
        assert frame is not None
        assert isinstance(frame, Image.Image)
        assert frame.size == (128, 32)

    @pytest.mark.asyncio
    async def test_stores_last_good_frame(self, plugin_manager):
        """Successful frame is stored as last_good_frame."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        frame = await plugin_manager.get_frame()
        assert plugin_manager.last_good_frame is frame

    @pytest.mark.asyncio
    async def test_resets_error_counter_on_success(self, plugin_manager):
        """Successful frame resets consecutive_errors to 0."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 3

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_returns_last_good_frame_on_error(self, plugin_manager):
        """On render error, returns last_good_frame."""
        plugin = FailingRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        # Set a last good frame
        good_frame = Image.new("RGB", (128, 32), (100, 100, 100))
        plugin_manager.last_good_frame = good_frame

        result = await plugin_manager.get_frame()
        assert result is good_frame

    @pytest.mark.asyncio
    async def test_increments_error_counter_on_exception(self, plugin_manager):
        """Render exception increments consecutive_errors."""
        plugin = FailingRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 1

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 2

    @pytest.mark.asyncio
    async def test_increments_error_counter_on_timeout(self, plugin_manager):
        """Render timeout increments consecutive_errors."""
        plugin = SlowRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        result = await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 1
        # Should return last_good_frame (None if no previous good frame)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_plugin_completion(self, plugin_manager):
        """When render_frame returns None, get_frame returns None."""
        plugin = CompletingPlugin(frames=0)  # Immediately completes
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        result = await plugin_manager.get_frame()
        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_last_good_frame(self, plugin_manager):
        """On timeout, returns the last good frame if available."""
        plugin = SlowRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        good_frame = Image.new("RGB", (128, 32), (50, 50, 50))
        plugin_manager.last_good_frame = good_frame

        result = await plugin_manager.get_frame()
        assert result is good_frame


# --- Tests for should_deactivate() ---


class TestShouldDeactivate:
    """Tests for PluginManager.should_deactivate()."""

    def test_returns_false_when_no_active_plugin(self, plugin_manager):
        """should_deactivate returns False when no plugin is active."""
        assert plugin_manager.should_deactivate() is False

    def test_returns_false_within_time_and_no_errors(self, plugin_manager):
        """Returns False when within 30s and no errors."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        assert plugin_manager.should_deactivate() is False

    def test_returns_true_after_30_seconds(self, plugin_manager):
        """Returns True when 30 seconds have elapsed."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time() - 31  # 31 seconds ago
        plugin_manager.consecutive_errors = 0

        assert plugin_manager.should_deactivate() is True

    def test_returns_true_at_exactly_30_seconds(self, plugin_manager):
        """Returns True when exactly 30 seconds have elapsed."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time() - 30
        plugin_manager.consecutive_errors = 0

        assert plugin_manager.should_deactivate() is True

    def test_returns_true_on_5_consecutive_errors(self, plugin_manager):
        """Returns True when 5 consecutive errors have occurred."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 5

        assert plugin_manager.should_deactivate() is True

    def test_returns_false_on_4_consecutive_errors(self, plugin_manager):
        """Returns False when only 4 consecutive errors have occurred."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 4

        assert plugin_manager.should_deactivate() is False

    def test_returns_true_on_more_than_5_errors(self, plugin_manager):
        """Returns True when more than 5 consecutive errors."""
        plugin_manager.active_plugin = SuccessPlugin()
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 10

        assert plugin_manager.should_deactivate() is True


# --- Tests for deactivate_plugin() ---


class TestDeactivatePlugin:
    """Tests for PluginManager.deactivate_plugin()."""

    @pytest.mark.asyncio
    async def test_calls_cleanup(self, plugin_manager):
        """deactivate_plugin calls the plugin's cleanup method."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()

        await plugin_manager.deactivate_plugin()
        assert plugin.cleaned_up is True

    @pytest.mark.asyncio
    async def test_resets_active_plugin(self, plugin_manager):
        """deactivate_plugin sets active_plugin to None."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin

        await plugin_manager.deactivate_plugin()
        assert plugin_manager.active_plugin is None

    @pytest.mark.asyncio
    async def test_resets_consecutive_errors(self, plugin_manager):
        """deactivate_plugin resets consecutive_errors to 0."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.consecutive_errors = 5

        await plugin_manager.deactivate_plugin()
        assert plugin_manager.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_resets_last_good_frame(self, plugin_manager):
        """deactivate_plugin resets last_good_frame to None."""
        plugin = SuccessPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.last_good_frame = Image.new("RGB", (128, 32))

        await plugin_manager.deactivate_plugin()
        assert plugin_manager.last_good_frame is None

    @pytest.mark.asyncio
    async def test_handles_cleanup_exception(self, plugin_manager, caplog):
        """deactivate_plugin handles exceptions in cleanup gracefully."""

        class BadCleanupPlugin(SuccessPlugin):
            @property
            def name(self) -> str:
                return "bad-cleanup"

            async def cleanup(self) -> None:
                raise RuntimeError("Cleanup failed")

        plugin = BadCleanupPlugin()
        plugin_manager.active_plugin = plugin

        # Should not raise
        await plugin_manager.deactivate_plugin()
        assert plugin_manager.active_plugin is None

    @pytest.mark.asyncio
    async def test_noop_when_no_active_plugin(self, plugin_manager):
        """deactivate_plugin does nothing when no plugin is active."""
        plugin_manager.active_plugin = None
        await plugin_manager.deactivate_plugin()
        # Should not raise
        assert plugin_manager.active_plugin is None


# --- Tests for is_plugin_active() ---


class TestIsPluginActive:
    """Tests for PluginManager.is_plugin_active()."""

    def test_returns_false_when_no_plugin(self, plugin_manager):
        """is_plugin_active returns False when no plugin is active."""
        assert plugin_manager.is_plugin_active() is False

    def test_returns_true_when_plugin_active(self, plugin_manager):
        """is_plugin_active returns True when a plugin is active."""
        plugin_manager.active_plugin = SuccessPlugin()
        assert plugin_manager.is_plugin_active() is True


# --- Integration tests for error recovery flow ---


class TestErrorRecoveryFlow:
    """Integration tests for the error recovery behavior."""

    @pytest.mark.asyncio
    async def test_five_consecutive_errors_triggers_deactivation(self, plugin_manager):
        """5 consecutive render errors should trigger should_deactivate."""
        plugin = FailingRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        for i in range(5):
            await plugin_manager.get_frame()

        assert plugin_manager.consecutive_errors == 5
        assert plugin_manager.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_success_resets_error_counter(self, plugin_manager):
        """A successful frame after errors resets the counter."""
        # Pattern: 4 failures then 1 success
        plugin = IntermittentPlugin([False, False, False, False, True])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        # 4 failures
        for _ in range(4):
            await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 4
        assert plugin_manager.should_deactivate() is False

        # 1 success resets
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0
        assert plugin_manager.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_full_deactivation_flow(self, plugin_manager):
        """Full flow: errors → should_deactivate → deactivate_plugin."""
        plugin = FailingRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        # Accumulate 5 errors
        for _ in range(5):
            await plugin_manager.get_frame()

        assert plugin_manager.should_deactivate() is True

        # Deactivate
        await plugin_manager.deactivate_plugin()
        assert plugin_manager.active_plugin is None
        assert plugin_manager.consecutive_errors == 0
        assert plugin_manager.last_good_frame is None
        assert plugin.cleanup_called is True
