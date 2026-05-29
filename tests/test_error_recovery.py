"""Tests for error recovery (Property 7) and consecutive error deactivation (Property 8).

# Feature: plugin-system, Property 7: Error Recovery Holds Last Good Frame

For any sequence of render_frame() calls where some calls raise exceptions
or time out, the Plugin_Manager SHALL return the last successfully rendered
frame for each failed call, rather than returning None or an error frame.

**Validates: Requirements 2.8**

# Feature: plugin-system, Property 8: Consecutive Error Deactivation

For any sequence of render_frame() results, if exactly 5 consecutive calls
raise exceptions or time out (without any successful frame in between), the
Plugin_Manager SHALL deactivate that plugin. Fewer than 5 consecutive errors
SHALL NOT trigger deactivation, and a successful frame SHALL reset the
consecutive error counter to zero.

**Validates: Requirements 2.9**
"""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import ClockPlugin

# --- Test plugin fixtures ---


class ConfigurablePlugin(ClockPlugin):
    """Plugin that follows a configurable success/failure pattern.

    Each call to render_frame() consumes the next item from the pattern list:
    - True means success (returns a frame)
    - False means failure (raises RuntimeError)
    """

    def __init__(self, pattern: list):
        self._pattern = pattern
        self._index = 0
        self._cleanup_called = False

    @property
    def name(self) -> str:
        return "configurable-plugin"

    @property
    def description(self) -> str:
        return "Plugin with configurable success/failure pattern"

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
            raise RuntimeError(f"Simulated failure at index {self._index - 1}")
        return Image.new("RGB", (width, height), (0, self._index, 0))

    async def cleanup(self) -> None:
        self._cleanup_called = True


@pytest.fixture
def plugin_manager(tmp_path):
    """Create a PluginManager with temp config."""
    config_path = tmp_path / "plugins.yaml"
    return PluginManager(128, 32, config_path=config_path, resources_path=tmp_path)


# --- Unit Tests: Error Recovery Holds Last Good Frame (Property 7) ---


class TestErrorRecoveryReturnsLastGoodFrame:
    """Test that render errors return the last good frame (not None).

    **Validates: Requirements 2.8**
    """

    @pytest.mark.asyncio
    async def test_error_returns_last_good_frame(self, plugin_manager):
        """After a successful frame, a render error returns the last good frame."""
        # Pattern: 2 successes, then failures
        plugin = ConfigurablePlugin([True, True, False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # Get two good frames
        frame1 = await plugin_manager.get_frame()
        assert frame1 is not None

        frame2 = await plugin_manager.get_frame()
        assert frame2 is not None

        # Third call errors but returns last good frame
        frame3 = await plugin_manager.get_frame()
        assert frame3 is not None
        assert frame3 == frame2  # Should be the last good frame

    @pytest.mark.asyncio
    async def test_multiple_errors_keep_returning_last_good_frame(self, plugin_manager):
        """Multiple consecutive errors all return the same last good frame."""
        # Pattern: 1 success, then 4 failures
        plugin = ConfigurablePlugin([True, False, False, False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # Get one good frame
        good_frame = await plugin_manager.get_frame()
        assert good_frame is not None

        # Multiple errors should all return the same last good frame
        for _ in range(4):
            error_frame = await plugin_manager.get_frame()
            assert error_frame is not None
            assert error_frame == good_frame

    @pytest.mark.asyncio
    async def test_first_error_with_no_good_frame_returns_none(self, plugin_manager):
        """If no good frame has been rendered yet, error returns None."""
        plugin = ConfigurablePlugin([False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # First call errors with no prior good frame
        frame = await plugin_manager.get_frame()
        # last_good_frame is None since no frame was ever rendered successfully
        assert frame is None

    @pytest.mark.asyncio
    async def test_timeout_returns_last_good_frame(self, plugin_manager):
        """A render_frame timeout returns the last good frame."""

        class SlowRenderPlugin(ClockPlugin):
            def __init__(self):
                self._call_count = 0

            @property
            def name(self) -> str:
                return "slow-render"

            @property
            def description(self) -> str:
                return "Plugin with slow render"

            @property
            def frame_delay_ms(self) -> int:
                return 40

            async def initialize(self, config: dict) -> None:
                self._call_count = 0

            async def render_frame(
                self, width: int, height: int
            ) -> Optional[Image.Image]:
                self._call_count += 1
                if self._call_count > 1:
                    await asyncio.sleep(10)
                return Image.new("RGB", (width, height), (100, 100, 100))

            async def cleanup(self) -> None:
                pass

        plugin = SlowRenderPlugin()
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # First call succeeds
        good_frame = await plugin_manager.get_frame()
        assert good_frame is not None

        # Second call times out, should return last good frame
        timeout_frame = await plugin_manager.get_frame()
        assert timeout_frame is not None
        assert timeout_frame == good_frame


class TestSuccessfulFrameResetsErrorCounter:
    """Test that a successful frame resets the consecutive error counter.

    **Validates: Requirements 2.8**
    """

    @pytest.mark.asyncio
    async def test_success_resets_error_counter(self, plugin_manager):
        """A successful render_frame resets consecutive_errors to 0."""
        plugin = ConfigurablePlugin([True, False, False, True])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # First call succeeds
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

        # Two errors
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 1
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 2

        # Success resets counter
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

    @pytest.mark.asyncio
    async def test_error_counter_increments_on_each_error(self, plugin_manager):
        """Each consecutive error increments the counter by 1."""
        plugin = ConfigurablePlugin([True, False, False, False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        # First call succeeds
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

        # Each error increments
        for expected_count in range(1, 5):
            await plugin_manager.get_frame()
            assert plugin_manager.consecutive_errors == expected_count

    @pytest.mark.asyncio
    async def test_interleaved_success_and_errors(self, plugin_manager):
        """Interleaved successes and errors properly track the counter."""
        # Pattern: success, error, error, success, error, success
        plugin = ConfigurablePlugin([True, False, False, True, False, True])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0
        plugin_manager.last_good_frame = None

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 1

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 2

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 1

        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0


# --- Property-Based Test: Property 7 ---
# Feature: plugin-system, Property 7: Error Recovery Holds Last Good Frame


class TestErrorRecoveryProperty:
    """Property-based tests for error recovery.

    **Validates: Requirements 2.8**

    Property 7: For any sequence of render_frame() calls where some calls
    raise exceptions or time out, the Plugin_Manager SHALL return the last
    successfully rendered frame for each failed call, rather than returning
    None or an error frame.
    """

    @given(
        sequence=st.lists(
            st.booleans(),
            min_size=2,
            max_size=50,
        )
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_error_recovery_holds_last_good_frame(self, sequence):
        """For any sequence with at least one success before a failure,
        failed calls return the last good frame, not None.

        **Validates: Requirements 2.8**
        """
        # Ensure at least one True (success) before a False (failure)
        assume(True in sequence)
        first_true_idx = sequence.index(True)
        # Ensure there's at least one failure after the first success
        assume(any(not s for s in sequence[first_true_idx + 1 :]))

        pm = PluginManager(
            128,
            32,
            config_path=Path(tempfile.mkdtemp()) / "plugins.yaml",
            resources_path=Path(tempfile.mkdtemp()),
        )

        plugin = ConfigurablePlugin(sequence)
        pm.active_plugin = plugin
        pm.plugin_start_time = time.time()
        pm.consecutive_errors = 0
        pm.last_good_frame = None

        last_good_frame = None

        for should_succeed in sequence:
            frame = await pm.get_frame()

            if should_succeed:
                # Successful frame: should be a valid image
                assert frame is not None
                assert isinstance(frame, Image.Image)
                last_good_frame = frame
            else:
                # Failed frame: should return last good frame
                if last_good_frame is not None:
                    # After at least one success, errors must return last good frame
                    assert (
                        frame is not None
                    ), "Error recovery must return last good frame, not None"
                    assert (
                        frame == last_good_frame
                    ), "Error recovery must return the last successfully rendered frame"


# --- Unit Tests: Consecutive Error Deactivation (Property 8) ---


class TestConsecutiveErrorDeactivation:
    """Unit tests for 5 consecutive errors triggering deactivation."""

    @pytest.mark.asyncio
    async def test_five_consecutive_errors_triggers_deactivation(self, plugin_manager):
        """5 consecutive render errors should trigger should_deactivate."""
        plugin = ConfigurablePlugin([False, False, False, False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        for _ in range(5):
            await plugin_manager.get_frame()

        assert plugin_manager.consecutive_errors == 5
        assert plugin_manager.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_four_errors_plus_one_success_does_not_deactivate(
        self, plugin_manager
    ):
        """4 errors followed by 1 success does NOT trigger deactivation."""
        # Pattern: 4 failures then 1 success
        plugin = ConfigurablePlugin([False, False, False, False, True])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        # 4 failures
        for _ in range(4):
            await plugin_manager.get_frame()

        assert plugin_manager.consecutive_errors == 4
        assert plugin_manager.should_deactivate() is False

        # 1 success resets the counter
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0
        assert plugin_manager.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_error_counter_resets_on_success(self, plugin_manager):
        """A successful frame resets the consecutive error counter to zero."""
        # Pattern: 3 failures, 1 success, 3 failures
        plugin = ConfigurablePlugin([False, False, False, True, False, False, False])
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        # 3 failures
        for _ in range(3):
            await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 3

        # 1 success resets
        await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 0

        # 3 more failures
        for _ in range(3):
            await plugin_manager.get_frame()
        assert plugin_manager.consecutive_errors == 3
        assert plugin_manager.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_exactly_five_errors_needed(self, plugin_manager):
        """Fewer than 5 consecutive errors never triggers deactivation."""
        for error_count in range(1, 5):
            plugin = ConfigurablePlugin([False] * error_count)
            plugin_manager.active_plugin = plugin
            plugin_manager.plugin_start_time = time.time()
            plugin_manager.consecutive_errors = 0

            for _ in range(error_count):
                await plugin_manager.get_frame()

            assert plugin_manager.consecutive_errors == error_count
            assert plugin_manager.should_deactivate() is False

    @pytest.mark.asyncio
    async def test_more_than_five_errors_still_deactivates(self, plugin_manager):
        """More than 5 consecutive errors also triggers deactivation."""
        plugin = ConfigurablePlugin([False] * 10)
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        for _ in range(7):
            await plugin_manager.get_frame()

        assert plugin_manager.consecutive_errors == 7
        assert plugin_manager.should_deactivate() is True

    @pytest.mark.asyncio
    async def test_success_between_error_groups_prevents_deactivation(
        self, plugin_manager
    ):
        """Success frames interspersed between errors prevent reaching threshold."""
        # 4 errors, 1 success, 4 errors - never reaches 5 consecutive
        pattern = [False, False, False, False, True, False, False, False, False]
        plugin = ConfigurablePlugin(pattern)
        plugin_manager.active_plugin = plugin
        plugin_manager.plugin_start_time = time.time()
        plugin_manager.consecutive_errors = 0

        for _ in range(len(pattern)):
            await plugin_manager.get_frame()

        # After the success at index 4, counter resets; then 4 more errors
        assert plugin_manager.consecutive_errors == 4
        assert plugin_manager.should_deactivate() is False


# --- Property-Based Tests ---


# Strategy: generate a list of booleans representing success (True) / failure (False)
# for render_frame calls
render_sequence = st.lists(st.booleans(), min_size=1, max_size=50)


def _make_plugin_manager() -> PluginManager:
    """Create a PluginManager with a temporary config path for property tests."""
    tmp_dir = Path(tempfile.mkdtemp())
    config_path = tmp_dir / "plugins.yaml"
    return PluginManager(128, 32, config_path=config_path, resources_path=tmp_dir)


class TestConsecutiveErrorDeactivationProperty:
    """Property-based tests for consecutive error deactivation (Property 8).

    **Validates: Requirements 2.9**
    """

    @given(sequence=render_sequence)
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_deactivation_iff_five_consecutive_errors(self, sequence):
        """Property 8: Deactivation occurs if and only if 5+ consecutive errors exist.

        For any sequence of render_frame() results, should_deactivate() returns
        True if and only if the sequence contains 5 or more consecutive failures
        (without any success in between).

        **Validates: Requirements 2.9**
        """
        pm = _make_plugin_manager()

        plugin = ConfigurablePlugin(sequence)
        pm.active_plugin = plugin
        pm.plugin_start_time = time.time()
        pm.consecutive_errors = 0

        # Execute the sequence
        for _ in range(len(sequence)):
            await pm.get_frame()

        # Compute expected: the current trailing streak of failures
        current_streak = 0
        for success in sequence:
            if not success:
                current_streak += 1
            else:
                current_streak = 0

        assert pm.consecutive_errors == current_streak

        # should_deactivate should be True iff current_streak >= 5
        expected_deactivate = current_streak >= 5
        assert pm.should_deactivate() == expected_deactivate

    @given(sequence=render_sequence)
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_success_always_resets_counter(self, sequence):
        """Property: A successful frame always resets consecutive_errors to zero.

        **Validates: Requirements 2.9**
        """
        # Ensure at least one success in the sequence
        assume(any(sequence))

        pm = _make_plugin_manager()

        plugin = ConfigurablePlugin(sequence)
        pm.active_plugin = plugin
        pm.plugin_start_time = time.time()
        pm.consecutive_errors = 0

        # Track that after every success, the counter is 0
        for i, success in enumerate(sequence):
            await pm.get_frame()
            if success:
                assert pm.consecutive_errors == 0, (
                    f"After success at index {i}, consecutive_errors should be 0 "
                    f"but was {pm.consecutive_errors}"
                )

    @given(n_errors=st.integers(min_value=0, max_value=4))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_fewer_than_five_errors_never_deactivates(self, n_errors):
        """Property: Fewer than 5 consecutive errors SHALL NOT trigger deactivation.

        **Validates: Requirements 2.9**
        """
        pm = _make_plugin_manager()

        plugin = ConfigurablePlugin([False] * n_errors)
        pm.active_plugin = plugin
        pm.plugin_start_time = time.time()
        pm.consecutive_errors = 0

        for _ in range(n_errors):
            await pm.get_frame()

        assert pm.consecutive_errors == n_errors
        assert pm.should_deactivate() is False

    @given(n_errors=st.integers(min_value=5, max_value=20))
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_five_or_more_errors_always_deactivates(self, n_errors):
        """Property: 5 or more consecutive errors SHALL trigger deactivation.

        **Validates: Requirements 2.9**
        """
        pm = _make_plugin_manager()

        plugin = ConfigurablePlugin([False] * n_errors)
        pm.active_plugin = plugin
        pm.plugin_start_time = time.time()
        pm.consecutive_errors = 0

        for _ in range(n_errors):
            await pm.get_frame()

        assert pm.consecutive_errors == n_errors
        assert pm.should_deactivate() is True
