"""Shared color constants for zeClock.

Centralizes the color palette used across the clock, plugins, and rendering.
"""

import colorsys
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


def complementary_color(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Return the palette color most complementary to the given color.

    Computes the HSV complement (180° hue rotation) then finds the closest
    match in COLOR_MAP by Euclidean distance in RGB space.

    Args:
        color: RGB tuple (0-255 per channel).

    Returns:
        The COLOR_MAP entry closest to the HSV complement of the input.
    """
    r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    # Rotate hue by 180°
    h_comp = (h + 0.5) % 1.0
    rc, gc, bc = colorsys.hsv_to_rgb(h_comp, s, v)
    target = (int(rc * 255), int(gc * 255), int(bc * 255))

    # Find closest palette color (Euclidean distance in RGB)
    best: Tuple[int, int, int] = COLOR_LIST[0]
    best_dist = float("inf")
    for candidate in COLOR_LIST:
        if candidate == color:
            continue  # Skip the input color itself
        dist = sum((a - b_) ** 2 for a, b_ in zip(target, candidate))
        if dist < best_dist:
            best_dist = dist
            best = candidate

    return best
