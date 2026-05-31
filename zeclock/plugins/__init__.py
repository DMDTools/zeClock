"""zeClock plugin system - built-in plugins and base interface."""

from .base import (
    ClockPlugin,
    PagedPlugin,
    validate_plugin_name,
    validate_plugin_description,
    validate_frame_delay_ms,
)
from .helpers import (
    ConfettiAnimation,
    CONFETTI_COLORS_PARTY,
    CONFETTI_COLORS_WARM,
    CONFETTI_COLORS_COOL,
)
from ..overlay import (
    upscale_2x,
    epx_upscale_2x,
    nearest_upscale_2x,
    hq2x,
    scale3x,
    upscale_nx,
)

__all__ = [
    "ClockPlugin",
    "PagedPlugin",
    "validate_plugin_name",
    "validate_plugin_description",
    "validate_frame_delay_ms",
    "ConfettiAnimation",
    "CONFETTI_COLORS_PARTY",
    "CONFETTI_COLORS_WARM",
    "CONFETTI_COLORS_COOL",
    "upscale_2x",
    "upscale_nx",
    "epx_upscale_2x",
    "nearest_upscale_2x",
    "hq2x",
    "scale3x",
]
