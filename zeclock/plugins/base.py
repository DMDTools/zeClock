"""ClockPlugin abstract base class and validation utilities."""

import re
from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image

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
