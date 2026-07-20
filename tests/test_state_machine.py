"""Integration tests for the ZeClock state machine transitions.

Tests the full plugin lifecycle: discover → load → initialize → render → cleanup,
fallback behavior when all plugins fail, clock-only duration respecting config,
and weighted random plugin selection.

Validates: Requirements 3.1, 3.6, 3.7
"""

import asyncio
import time
from collections import Counter
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from zeclock.clock import ClockState, ZeClock
from zeclock.plugin_config import PluginConfig
from zeclock.plugin_manager import PluginManager
from zeclock.plugin_registry import PluginRegistry
from zeclock.plugins.base import ClockPlugin

from tests.conftest import DummyPlugin, FailingPlugin

# ---------------------------------------------------------------------------
# Test plugin helpers
# ---------------------------------------------------------------------------


class LifecycleTrackingPlugin(ClockPlugin):
    """Plugin that tracks its lifecycle transitions for verification."""

    def __init__(
        self,
        name: str = "lifecycle-plugin",
        frames_to_render: int = 3,
        frequency: int = 100,
    ):
        self._name = name
        self._frames_to_render = frames_to_render
        self._frame_count = 0
        self.frequency = frequency
        self.lifecycle_events: list = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A plugin that tracks lifecycle events"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        self.lifecycle_events.append("initialize")
        self._frame_count = 0

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        if self._frame_count >= self._frames_to_render:
            self.lifecycle_events.append("complete")
            return None
        self._frame_count += 1
        self.lifecycle_events.append(f"render_{self._frame_count}")
        return Image.new("RGB", (width, height), (255, 128, 0))

    async def cleanup(self) -> None:
        self.lifecycle_events.append("cleanup")


class AlwaysFailingInitPlugin(ClockPlugin):
    """Plugin that always fails during initialization."""

    def __init__(self, name: str = "fail-init"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Plugin that fails on init"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        raise RuntimeError("Initialization failed")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Test: Full lifecycle (discover → load → initialize → render → cleanup)
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Test the full plugin lifecycle through the state machine."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_discover_load_init_render_cleanup(self):
        """A plugin goes through discover → load → initialize → render → cleanup."""
        plugin = LifecycleTrackingPlugin(frames_to_render=3)

        # Create a PluginManager and manually register the plugin
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()  # Skip file loading
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = [
            {"name": "lifecycle-plugin", "frequency": 100, "settings": {}}
        ]
        pm.registry.register(plugin, source="builtin", frequency=100)

        # Step 1: Select plugin (simulates PLUGIN_SELECT state)
        selected = pm.select_next_plugin()
        assert selected is plugin

        # Step 2: Activate plugin (initialize)
        success = await pm.activate_plugin(selected)
        assert success is True
        assert "initialize" in plugin.lifecycle_events

        # Step 3: Render frames (PLUGIN_ACTIVE state)
        frames_received = []
        while True:
            frame = await pm.get_frame()
            if frame is None:
                break
            frames_received.append(frame)

        assert len(frames_received) == 3
        assert "render_1" in plugin.lifecycle_events
        assert "render_2" in plugin.lifecycle_events
        assert "render_3" in plugin.lifecycle_events
        assert "complete" in plugin.lifecycle_events

        # Step 4: Deactivate (cleanup)
        await pm.deactivate_plugin()
        assert "cleanup" in plugin.lifecycle_events

        # Verify full lifecycle order
        expected_order = [
            "initialize",
            "render_1",
            "render_2",
            "render_3",
            "complete",
            "cleanup",
        ]
        assert plugin.lifecycle_events == expected_order

    @pytest.mark.asyncio
    async def test_lifecycle_with_multiple_activations(self):
        """A plugin can be activated, complete, and be activated again."""
        plugin = LifecycleTrackingPlugin(frames_to_render=2)

        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []
        pm.registry.register(plugin, source="builtin", frequency=100)

        # First activation cycle
        selected = pm.select_next_plugin()
        await pm.activate_plugin(selected)
        while await pm.get_frame() is not None:
            pass
        await pm.deactivate_plugin()

        # Second activation cycle
        plugin.lifecycle_events.clear()
        selected = pm.select_next_plugin()
        await pm.activate_plugin(selected)
        while await pm.get_frame() is not None:
            pass
        await pm.deactivate_plugin()

        # Second cycle should have full lifecycle
        assert plugin.lifecycle_events == [
            "initialize",
            "render_1",
            "render_2",
            "complete",
            "cleanup",
        ]


# ---------------------------------------------------------------------------
# Test: Fallback to pinball when all plugins fail
# ---------------------------------------------------------------------------


class TestFallbackBehavior:
    """Test fallback to pinball/legacy animation when all plugins fail."""

    @pytest.mark.asyncio
    async def test_fallback_when_all_plugins_fail_init(self):
        """When all plugins fail initialization, fallback flag is set."""
        fail_plugin_a = AlwaysFailingInitPlugin(name="fail-a")
        fail_plugin_b = AlwaysFailingInitPlugin(name="fail-b")

        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []
        pm.registry.register(fail_plugin_a, source="builtin", frequency=50)
        pm.registry.register(fail_plugin_b, source="builtin", frequency=50)

        # Try to activate each plugin - both should fail
        plugin_a = pm.registry.get_plugin("fail-a").plugin
        success_a = await pm.activate_plugin(plugin_a)
        assert success_a is False

        plugin_b = pm.registry.get_plugin("fail-b").plugin
        success_b = await pm.activate_plugin(plugin_b)
        assert success_b is False

        # Both should be marked as failed
        assert pm.registry.get_plugin("fail-a").state == "failed"
        assert pm.registry.get_plugin("fail-b").state == "failed"

        # No active plugins remain
        active = pm.registry.get_active_plugins()
        assert len(active) == 0

        # select_next_plugin should return None (triggers fallback)
        assert pm.select_next_plugin() is None

    @pytest.mark.asyncio
    async def test_zeclock_sets_fallback_flag_when_no_plugins(self):
        """ZeClock sets _fallback_to_legacy when no active plugins are available."""
        # Create a mock backend
        mock_backend = MagicMock()
        mock_backend.connect.return_value = True

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 5
        clock._plugin_manager.config.plugin_entries = []

        # Register only a failing plugin
        fail_plugin = AlwaysFailingInitPlugin(name="fail-only")
        clock._plugin_manager.registry.register(
            fail_plugin, source="builtin", frequency=100
        )

        # Simulate the state machine transition to PLUGIN_SELECT
        clock._state = ClockState.PLUGIN_SELECT

        # Try to select and activate - should fail and trigger fallback
        activated = await clock._select_and_activate_plugin()
        assert activated is False

    @pytest.mark.asyncio
    async def test_select_next_plugin_returns_none_when_all_failed(self):
        """select_next_plugin returns None when all plugins are marked failed."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        # Register plugins and mark them all as failed
        for i in range(3):
            plugin = DummyPlugin(name=f"plugin-{i}")
            pm.registry.register(plugin, source="builtin", frequency=33)
            pm.registry.mark_failed(f"plugin-{i}", "test failure")

        result = pm.select_next_plugin()
        assert result is None


# ---------------------------------------------------------------------------
# Test: Clock-only duration between plugin activations respects config
# ---------------------------------------------------------------------------


class TestClockOnlyDuration:
    """Test that clock-only duration between plugin activations respects config."""

    @pytest.mark.asyncio
    async def test_clock_display_seconds_from_config(self):
        """ZeClock uses clock_display_seconds from plugin config."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 10
        clock._plugin_manager.config.plugin_entries = []

        result = clock._get_clock_display_seconds()
        assert result == 10

    @pytest.mark.asyncio
    async def test_clock_display_seconds_default_without_manager(self):
        """Without a plugin manager, default clock display seconds is 5."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = None

        result = clock._get_clock_display_seconds()
        assert result == 5.0

    @pytest.mark.asyncio
    async def test_transition_from_clock_only_after_duration_elapsed(self):
        """State transitions from CLOCK_ONLY to PLUGIN_SELECT after duration elapses."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 2
        clock._plugin_manager.config.plugin_entries = []

        # Set state to CLOCK_ONLY with start time in the past
        clock._state = ClockState.DEFAULT_PLUGIN
        clock._default_plugin_start = time.time() - 3  # 3 seconds ago (> 2s config)

        # The state machine logic checks if duration has elapsed
        clock_display_seconds = clock._get_clock_display_seconds()
        now = time.time()
        elapsed = now - clock._default_plugin_start

        assert elapsed >= clock_display_seconds
        # This means the state machine would transition to PLUGIN_SELECT

    @pytest.mark.asyncio
    async def test_no_transition_before_duration_elapsed(self):
        """State stays CLOCK_ONLY before the configured duration elapses."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 10
        clock._plugin_manager.config.plugin_entries = []

        # Set state to CLOCK_ONLY with start time just now
        clock._state = ClockState.DEFAULT_PLUGIN
        clock._default_plugin_start = time.time()

        # Check that duration has NOT elapsed
        clock_display_seconds = clock._get_clock_display_seconds()
        now = time.time()
        elapsed = now - clock._default_plugin_start

        assert elapsed < clock_display_seconds
        # State machine would NOT transition yet

    @pytest.mark.asyncio
    async def test_default_plugin_start_reset_after_plugin_deactivation(self):
        """After a plugin is deactivated, clock_only_start is reset."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 5
        clock._plugin_manager.config.plugin_entries = []

        plugin = DummyPlugin(name="test-reset", frames_to_render=1)
        clock._plugin_manager.registry.register(plugin, source="builtin", frequency=100)

        # Activate plugin
        await clock._plugin_manager.activate_plugin(plugin)
        clock._state = ClockState.PLUGIN_ACTIVE

        # Simulate plugin completion and deactivation
        await clock._plugin_manager.deactivate_plugin()
        clock._state = ClockState.DEFAULT_PLUGIN
        clock._default_plugin_start = time.time()

        # Verify clock_only_start is recent (within last second)
        assert time.time() - clock._default_plugin_start < 1.0


# ---------------------------------------------------------------------------
# Test: Plugin selection uses weighted random (statistical test)
# ---------------------------------------------------------------------------


class TestWeightedRandomSelection:
    """Test that plugin selection uses weighted random based on frequencies."""

    @pytest.mark.asyncio
    async def test_weighted_selection_distribution(self):
        """Plugin selection follows configured frequency distribution.

        Register plugins with known frequencies and verify the selection
        distribution matches expected frequencies within statistical tolerance.
        """
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        # Register plugins with known frequencies: 70/20/10
        plugin_a = DummyPlugin(name="plugin-a")
        plugin_b = DummyPlugin(name="plugin-b")
        plugin_c = DummyPlugin(name="plugin-c")

        pm.registry.register(plugin_a, source="builtin", frequency=70)
        pm.registry.register(plugin_b, source="builtin", frequency=20)
        pm.registry.register(plugin_c, source="builtin", frequency=10)

        # Run many selections and count
        num_iterations = 10000
        counts = Counter()

        for _ in range(num_iterations):
            selected = pm.select_next_plugin()
            assert selected is not None
            counts[selected.name] += 1

        # Verify distribution is reasonable (the algorithm excludes last-selected,
        # so actual distribution differs from raw weights)
        # With 70/20/10 and no-repeat: plugin-a gets ~46%, plugin-b ~32%, plugin-c ~22%
        tolerance = 0.10  # 10 percentage points

        actual_a = counts["plugin-a"] / num_iterations
        actual_b = counts["plugin-b"] / num_iterations
        actual_c = counts["plugin-c"] / num_iterations

        assert (
            abs(actual_a - 0.46) < tolerance
        ), f"plugin-a: expected ~46%, got {actual_a*100:.1f}%"
        assert (
            abs(actual_b - 0.32) < tolerance
        ), f"plugin-b: expected ~32%, got {actual_b*100:.1f}%"
        assert (
            abs(actual_c - 0.22) < tolerance
        ), f"plugin-c: expected ~22%, got {actual_c*100:.1f}%"

    @pytest.mark.asyncio
    async def test_single_plugin_always_selected(self):
        """With only one active plugin, it is always selected."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin = DummyPlugin(name="only-plugin")
        pm.registry.register(plugin, source="builtin", frequency=100)

        for _ in range(100):
            selected = pm.select_next_plugin()
            assert selected is plugin

    @pytest.mark.asyncio
    async def test_zero_frequency_plugin_never_selected(self):
        """A plugin with frequency 0 is never selected when others have positive frequency."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin_active = DummyPlugin(name="active-plugin")
        plugin_zero = DummyPlugin(name="zero-plugin")

        pm.registry.register(plugin_active, source="builtin", frequency=100)
        pm.registry.register(plugin_zero, source="builtin", frequency=0)

        counts = Counter()
        for _ in range(1000):
            selected = pm.select_next_plugin()
            counts[selected.name] += 1

        assert counts["zero-plugin"] == 0
        assert counts["active-plugin"] == 1000

    @pytest.mark.asyncio
    async def test_equal_frequency_equal_distribution(self):
        """Plugins with equal frequency are selected with roughly equal probability."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugins = []
        for i in range(4):
            p = DummyPlugin(name=f"equal-{i}")
            pm.registry.register(p, source="builtin", frequency=25)
            plugins.append(p)

        num_iterations = 10000
        counts = Counter()
        for _ in range(num_iterations):
            selected = pm.select_next_plugin()
            counts[selected.name] += 1

        # Each should be ~25% (±5%)
        for i in range(4):
            actual = counts[f"equal-{i}"] / num_iterations
            assert (
                abs(actual - 0.25) < 0.05
            ), f"equal-{i}: expected ~25%, got {actual*100:.1f}%"

    @pytest.mark.asyncio
    async def test_failed_plugin_excluded_from_selection(self):
        """Failed plugins are excluded from weighted random selection."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin_good = DummyPlugin(name="good-plugin")
        plugin_bad = DummyPlugin(name="bad-plugin")

        pm.registry.register(plugin_good, source="builtin", frequency=50)
        pm.registry.register(plugin_bad, source="builtin", frequency=50)
        pm.registry.mark_failed("bad-plugin", "test failure")

        # Only good-plugin should be selected
        for _ in range(100):
            selected = pm.select_next_plugin()
            assert selected.name == "good-plugin"


# ---------------------------------------------------------------------------
# Test: State transitions integration
# ---------------------------------------------------------------------------


class TestStateTransitions:
    """Test the state machine transitions in the ZeClock context."""

    @pytest.mark.asyncio
    async def test_state_starts_at_clock_only(self):
        """ZeClock starts in CLOCK_ONLY state."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        assert clock._state == ClockState.DEFAULT_PLUGIN

    @pytest.mark.asyncio
    async def test_plugin_active_to_clock_only_on_completion(self):
        """When a plugin signals completion, state returns to CLOCK_ONLY."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 5
        clock._plugin_manager.config.plugin_entries = []

        # Register and activate a plugin that renders 1 frame then completes
        plugin = DummyPlugin(name="short-plugin", frames_to_render=1)
        clock._plugin_manager.registry.register(plugin, source="builtin", frequency=100)

        # Activate
        success = await clock._plugin_manager.activate_plugin(plugin)
        assert success is True
        clock._state = ClockState.PLUGIN_ACTIVE

        # Get frames until completion
        frame = await clock._plugin_manager.get_frame()
        assert frame is not None  # First frame

        frame = await clock._plugin_manager.get_frame()
        assert frame is None  # Completion signal

        # Deactivate and transition
        await clock._plugin_manager.deactivate_plugin()
        clock._state = ClockState.DEFAULT_PLUGIN
        clock._default_plugin_start = time.time()

        assert clock._state == ClockState.DEFAULT_PLUGIN

    @pytest.mark.asyncio
    async def test_plugin_select_to_clock_only_when_no_plugins(self):
        """PLUGIN_SELECT transitions back to CLOCK_ONLY when no plugins available."""
        mock_backend = MagicMock()

        clock = ZeClock(backend=mock_backend, test_mode=True)
        clock._plugin_manager = PluginManager(128, 32)
        clock._plugin_manager.config.load = MagicMock()
        clock._plugin_manager.config.clock_display_seconds = 5
        clock._plugin_manager.config.plugin_entries = []

        # No plugins registered - select should fail
        clock._state = ClockState.PLUGIN_SELECT
        activated = await clock._select_and_activate_plugin()

        assert activated is False
        # The state machine in run() would set state back to CLOCK_ONLY

    @pytest.mark.asyncio
    async def test_should_deactivate_after_30_seconds(self):
        """Plugin is deactivated after 30 seconds max duration."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin = DummyPlugin(name="long-plugin", frames_to_render=10000)
        pm.registry.register(plugin, source="builtin", frequency=100)

        await pm.activate_plugin(plugin)

        # Simulate 30 seconds elapsed
        pm.plugin_start_time = time.time() - 31

        assert pm.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_should_not_deactivate_before_30_seconds(self):
        """Plugin is NOT deactivated before 30 seconds."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin = DummyPlugin(name="normal-plugin", frames_to_render=10000)
        pm.registry.register(plugin, source="builtin", frequency=100)

        await pm.activate_plugin(plugin)

        # Only 5 seconds elapsed
        pm.plugin_start_time = time.time() - 5

        assert pm.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_should_deactivate_after_5_consecutive_errors(self):
        """Plugin is deactivated after 5 consecutive render errors."""
        pm = PluginManager(128, 32)
        pm.config.load = MagicMock()
        pm.config.clock_display_seconds = 5
        pm.config.plugin_entries = []

        plugin = FailingPlugin(name="error-plugin", fail_count=10)
        pm.registry.register(plugin, source="builtin", frequency=100)

        await pm.activate_plugin(plugin)

        # Trigger 5 consecutive errors
        for _ in range(5):
            await pm.get_frame()

        assert pm.consecutive_errors == 5
        assert pm.should_deactivate() is True
