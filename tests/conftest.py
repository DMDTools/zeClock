"""Shared test fixtures for the plugin system tests."""

import asyncio
from typing import Optional

import pytest
from PIL import Image

from zeclock.plugins.base import ClockPlugin


class DummyPlugin(ClockPlugin):
    """A minimal valid plugin for testing."""

    def __init__(
        self,
        name: str = "test-plugin",
        description: str = "A test plugin",
        frame_delay: int = 40,
        frames_to_render: int = 5,
    ):
        self._name = name
        self._description = description
        self._frame_delay_ms = frame_delay
        self._frames_to_render = frames_to_render
        self._frame_count = 0
        self._initialized = False
        self._cleaned_up = False
        self._config = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    async def initialize(self, config: dict) -> None:
        self._config = config
        self._initialized = True
        self._frame_count = 0

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        if self._frame_count >= self._frames_to_render:
            return None
        self._frame_count += 1
        return Image.new("RGB", (width, height), (255, 128, 0))

    async def cleanup(self) -> None:
        self._cleaned_up = True


class FailingPlugin(ClockPlugin):
    """A plugin that raises exceptions on render_frame."""

    def __init__(self, name: str = "failing-plugin", fail_count: int = 10):
        self._name = name
        self._fail_count = fail_count
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A plugin that always fails"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise RuntimeError(f"Simulated failure #{self._call_count}")
        return Image.new("RGB", (width, height), (0, 255, 0))

    async def cleanup(self) -> None:
        pass


class SlowInitPlugin(ClockPlugin):
    """A plugin with a slow initialize method for timeout testing."""

    def __init__(self, delay_seconds: float = 15.0):
        self._delay = delay_seconds

    @property
    def name(self) -> str:
        return "slow-init"

    @property
    def description(self) -> str:
        return "Plugin with slow initialization"

    @property
    def frame_delay_ms(self) -> int:
        return 40

    async def initialize(self, config: dict) -> None:
        await asyncio.sleep(self._delay)

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 255))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def dummy_plugin():
    """Create a fresh DummyPlugin instance."""
    return DummyPlugin()


@pytest.fixture
def failing_plugin():
    """Create a FailingPlugin instance."""
    return FailingPlugin()
