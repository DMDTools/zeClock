from PIL import Image
from typing import Any, Dict, List, Tuple

# LUT cache: maps color tuple -> (r_lut, g_lut, b_lut) as lists of ints
_colorize_lut_cache: Dict[
    Tuple[int, int, int], Tuple[List[int], List[int], List[int]]
] = {}

# Pre-built LUT: expand each byte value (0-255) into 8 mask pixels (0 or 255)
_BYTE_TO_MASK = [bytes([255 if (b >> bit) & 1 else 0 for bit in range(8)]) for b in range(256)]


def _get_color_channels(
    gray_img: Image.Image, color: Tuple[int, int, int]
) -> Tuple[Image.Image, Image.Image, Image.Image]:
    """Get colorized R, G, B channels using Pillow's C-native point() with LUT caching.

    Image.point() applies a 256-entry lookup table in C — no Python per-pixel loop.
    The LUT is cached per color so repeated calls with the same color are instant.
    """
    if color not in _colorize_lut_cache:
        # Build lookup tables (256 entries each, computed once per color)
        r_lut = [int((color[0] * i) / 255) for i in range(256)]
        g_lut = [int((color[1] * i) / 255) for i in range(256)]
        b_lut = [int((color[2] * i) / 255) for i in range(256)]
        _colorize_lut_cache[color] = (r_lut, g_lut, b_lut)

    r_lut, g_lut, b_lut = _colorize_lut_cache[color]
    r_channel = gray_img.point(r_lut)
    g_channel = gray_img.point(g_lut)
    b_channel = gray_img.point(b_lut)
    return r_channel, g_channel, b_channel


def colorize_grayscale(
    gray_img: Image.Image, color: Tuple[int, int, int]
) -> Image.Image:
    """Convert a grayscale image to RGB using a color tint.

    Uses Pillow's C-native point() with cached LUTs — ~10-20x faster than
    a Python per-pixel loop.

    Args:
        gray_img: Grayscale (mode 'L') PIL Image.
        color: RGB color tuple to tint with.

    Returns:
        RGB PIL Image with the grayscale values tinted by color.
    """
    r_channel, g_channel, b_channel = _get_color_channels(gray_img, color)
    return Image.merge("RGB", (r_channel, g_channel, b_channel))


# Keep backward-compatible alias
_colorize_grayscale = colorize_grayscale


def _unpack_bitmask(mask_bytes: bytes, mask_width_bytes: int, width: int, height: int) -> Image.Image:
    """Unpack a packed bit-mask into a PIL 'L' mode Image.

    Uses a pre-built 256-entry lookup table to expand each byte into 8 pixels
    via slice assignment, avoiding per-bit Python loops.

    Args:
        mask_bytes: Packed bit-mask data.
        mask_width_bytes: Number of bytes per row in the mask.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        PIL Image in 'L' mode where 255 = mask set, 0 = mask unset.
    """
    mask_data = bytearray(width * height)
    for y in range(height):
        row_offset = y * mask_width_bytes
        out_row = y * width
        for byte_idx in range(mask_width_bytes):
            byte_val = mask_bytes[row_offset + byte_idx] if (row_offset + byte_idx) < len(mask_bytes) else 0
            if byte_val:
                base_x = byte_idx * 8
                end = min(8, width - base_x)
                mask_data[out_row + base_x:out_row + base_x + end] = _BYTE_TO_MASK[byte_val][:end]
    return Image.frombytes("L", (width, height), bytes(mask_data))


def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine images using DotClk DotBlt logic: mask=1 preserves dest, mask=0 copies source.

    Optimized: unpacks mask to a full Pillow Image and uses Image.composite() (C-native)
    when possible, falling back to per-pixel only for edge cases.
    """
    # Check if overlay has mask data
    overlay_any: Any = overlay
    if hasattr(overlay, "mask_data") and overlay_any.mask_data:
        mask_bytes = overlay_any.mask_data
        mask_width_bytes = overlay_any.mask_width_bytes
        width, height = base.size

        mask_img = _unpack_bitmask(mask_bytes, mask_width_bytes, width, height)
        # Image.composite: result = base where mask=255, overlay where mask=0
        return Image.composite(base, overlay, mask_img)
    else:
        # No mask: treat as fully opaque (mask=0 everywhere)
        return overlay.copy()


def overlay_or_rgb(
    base: Image.Image,
    overlay: Image.Image,
    base_color: Tuple[int, int, int],
    overlay_color: Tuple[int, int, int],
) -> Image.Image:
    """Combine grayscale images with different colors for each layer.

    Optimized: uses Pillow's C-native point() for colorization and
    Image.composite() for mask-based blending.
    """
    width, height = base.size

    # Colorize both layers using C-native LUT (no Python per-pixel loop)
    base_rgb = colorize_grayscale(base, base_color)
    overlay_rgb = colorize_grayscale(overlay, overlay_color)

    # Apply overlay with mask
    overlay_any: Any = overlay
    if hasattr(overlay, "mask_data") and overlay_any.mask_data:
        mask_bytes = overlay_any.mask_data
        mask_width_bytes = overlay_any.mask_width_bytes

        mask_img = _unpack_bitmask(mask_bytes, mask_width_bytes, width, height)
        return Image.composite(base_rgb, overlay_rgb, mask_img)
    else:
        # No mask: overlay replaces everything
        return overlay_rgb
