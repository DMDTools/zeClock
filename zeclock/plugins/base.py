"""ClockPlugin abstract base class, mixins, and validation utilities."""

import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Validation constants
PLUGIN_NAME_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
PLUGIN_NAME_MAX_LENGTH = 64
PLUGIN_DESCRIPTION_MAX_LENGTH = 256
FRAME_DELAY_MIN_MS = 20
FRAME_DELAY_MAX_MS = 5000


def validate_plugin_name(name: str) -> bool:
    """Validate a plugin name against the naming rules.

    A valid name consists of 1 to 64 lowercase alphanumeric characters,
    hyphens, or underscores.

    Args:
        name: The plugin name to validate.

    Returns:
        True if the name is valid, False otherwise.
    """
    if not isinstance(name, str):
        return False
    return bool(PLUGIN_NAME_PATTERN.match(name))


def validate_plugin_description(description: str) -> bool:
    """Validate a plugin description.

    A valid description is a non-empty string of at most 256 characters.

    Args:
        description: The description to validate.

    Returns:
        True if the description is valid, False otherwise.
    """
    if not isinstance(description, str):
        return False
    return 0 < len(description) <= PLUGIN_DESCRIPTION_MAX_LENGTH


def validate_frame_delay_ms(delay: int) -> bool:
    """Validate a frame delay value.

    A valid frame delay is an integer between 20 and 5000 inclusive.

    Args:
        delay: The frame delay in milliseconds.

    Returns:
        True if the delay is valid, False otherwise.
    """
    if not isinstance(delay, int):
        return False
    return FRAME_DELAY_MIN_MS <= delay <= FRAME_DELAY_MAX_MS


class ClockPlugin(ABC):
    """Base class for all zeClock display plugins.

    Plugin authors must subclass this and implement all abstract methods
    and properties. See docs/plugin_authoring.md for a complete guide.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier: 1-64 chars, lowercase alphanumeric/hyphens/underscores."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description, 1-256 characters."""
        ...

    @property
    @abstractmethod
    def frame_delay_ms(self) -> int:
        """Desired delay between frames in milliseconds (20-5000)."""
        ...

    @abstractmethod
    async def initialize(self, config: dict) -> None:
        """Prepare the plugin for rendering.

        Called once before the first render_frame call. The config dict
        contains plugin-specific settings from plugins.yaml, plus a
        '_helpers' key with a PluginHelpers instance.

        Args:
            config: Plugin-specific settings from plugins.yaml.

        Raises:
            Exception: If initialization fails (plugin will be excluded).
        """
        ...

    @abstractmethod
    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next frame for the DMD display.

        Args:
            width: Display width in pixels (128 or 256).
            height: Display height in pixels (32 or 64).

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources. Called when plugin is deactivated."""
        ...


class CachedDataMixin:
    """Mixin for plugins that fetch and cache external data with staleness tracking.

    Provides a standard cache-with-refresh pattern: data is fetched once and
    reused until the cache duration expires. On fetch failure, existing cached
    data is preserved.

    Subclasses must implement `_fetch_data()` to perform the actual API call.

    Attributes:
        _cache_duration_seconds: How long cached data remains fresh (default: 900s / 15min).
        _cache_data: The cached data (any type, managed by subclass).
        _cache_fetched_at: Timestamp of last successful fetch.
    """

    _cache_duration_seconds: int = 900  # 15 minutes default
    _cache_data: Any = None
    _cache_fetched_at: float = 0.0

    def is_cache_stale(self) -> bool:
        """Check if the cached data is older than the configured duration.

        Returns:
            True if cache is stale or empty, False if fresh.
        """
        if self._cache_data is None:
            return True
        elapsed = time.time() - self._cache_fetched_at
        return elapsed >= self._cache_duration_seconds

    async def _refresh_cache_if_needed(self) -> None:
        """Fetch new data if cache is stale. Preserves old cache on failure."""
        if not self.is_cache_stale():
            return

        try:
            data = await self._fetch_data()
            if data is not None:
                self._cache_data = data
                self._cache_fetched_at = time.time()
        except Exception as e:
            logger.warning(
                "[%s] Failed to fetch data: %s",
                getattr(self, "name", "unknown"),
                e,
            )

    @abstractmethod
    async def _fetch_data(self) -> Any:
        """Fetch fresh data from the external source.

        Returns:
            The fetched data, or None on failure.
        """
        ...


class PagedPlugin(ClockPlugin):
    """Base class for plugins that cycle through multiple display pages.

    Handles the common page-cycling boilerplate: frame counting, page
    advancement, and automatic completion signaling after all pages
    are displayed. Subclasses implement `render_page()` instead of
    `render_frame()`.

    Config keys handled automatically:
        page_duration_seconds (int): Duration per page, 2-30s (default: 4).
    """

    def __init__(self):
        """Initialize paging state."""
        self._frame_delay_ms: int = 100  # 10 FPS default
        self._page_duration_seconds: int = 4
        self._current_page: int = 0
        self._frame_count: int = 0
        self._frames_per_page: int = 0
        self._total_pages: int = 0
        self._helpers: Any = None

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    def _init_paging(
        self,
        total_pages: int,
        page_duration_seconds: int = 4,
        frame_delay_ms: int = 100,
    ) -> None:
        """Set up page cycling state. Call this from initialize().

        Args:
            total_pages: Number of pages to cycle through.
            page_duration_seconds: Duration per page (clamped to 2-30).
            frame_delay_ms: Delay between frames in ms.
        """
        self._frame_delay_ms = frame_delay_ms
        self._page_duration_seconds = max(2, min(30, int(page_duration_seconds)))
        self._total_pages = total_pages
        self._current_page = 0
        self._frame_count = 0
        # Ceiling division: ensures at least 1 frame per page
        self._frames_per_page = (
            self._page_duration_seconds * 1000 + self._frame_delay_ms - 1
        ) // self._frame_delay_ms

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Handle page cycling; delegates to render_page().

        Returns None after all pages have been displayed.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if self._current_page >= self._total_pages:
            return None

        if self._current_page == 0 and self._frame_count == 0:
            logger.info("[%s] Start rendering", self.name)

        # Delegate to subclass
        frame = self.render_page(self._current_page, width, height)

        # Advance frame counter
        self._frame_count += 1
        if self._frame_count >= self._frames_per_page:
            self._frame_count = 0
            self._current_page += 1

        return frame

    @abstractmethod
    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a specific page. Implement this instead of render_frame().

        Args:
            page: Zero-based page index.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        ...

    async def cleanup(self) -> None:
        """Reset paging state for next activation."""
        self._current_page = 0
        self._frame_count = 0
