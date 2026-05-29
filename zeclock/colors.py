"""Shared color constants for zeClock.

Centralizes the color palette used across the clock, plugins, and rendering.
"""

from typing import Dict, Tuple

# Canonical color palette: name → RGB tuple
COLOR_MAP: Dict[str, Tuple[int, int, int]] = {
    "orange": (255, 128, 0),
    "blue": (0, 128, 255),
    "red": (255, 0, 0),
    "purple": (255, 0, 255),
    "green": (0, 255, 128),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "pink": (255, 64, 128),
}

# Ordered list of colors (for auto-rotate mode)
COLOR_LIST = list(COLOR_MAP.values())

# Reverse lookup: RGB tuple → name
COLOR_NAMES: Dict[Tuple[int, int, int], str] = {v: k for k, v in COLOR_MAP.items()}
