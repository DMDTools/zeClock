"""zeClock plugin system - built-in plugins and base interface."""

from .base import (
    ClockPlugin,
    PagedPlugin,
    validate_plugin_name,
    validate_plugin_description,
    validate_frame_delay_ms,
)

__all__ = [
    "ClockPlugin",
    "PagedPlugin",
    "validate_plugin_name",
    "validate_plugin_description",
    "validate_frame_delay_ms",
]
