from PIL import Image
from typing import Any, Tuple


def colorize_grayscale(
    gray_img: Image.Image, color: Tuple[int, int, int]
) -> Image.Image:
    """Convert a grayscale image to RGB using a color tint.

    Args:
        gray_img: Grayscale (mode 'L') PIL Image.
        color: RGB color tuple to tint with.

    Returns:
        RGB PIL Image with the grayscale values tinted by color.
    """
    width, height = gray_img.size
    gray_data = gray_img.tobytes()
    rgb_data = bytearray(width * height * 3)

    for i, pixel in enumerate(gray_data):
        if pixel > 0:
            offset = i * 3
            rgb_data[offset] = (color[0] * pixel) // 255
            rgb_data[offset + 1] = (color[1] * pixel) // 255
            rgb_data[offset + 2] = (color[2] * pixel) // 255

    return Image.frombytes("RGB", (width, height), bytes(rgb_data))


# Keep backward-compatible alias
_colorize_grayscale = colorize_grayscale


def overlay_or(base: Image.Image, overlay: Image.Image) -> Image.Image:
    """Combine images using DotClk DotBlt logic: mask=1 preserves dest, mask=0 copies source"""
    base_data = bytearray(base.tobytes())
    overlay_data = overlay.tobytes()
    width, height = base.size

    # Check if overlay has mask data
    overlay_any: Any = overlay
    if hasattr(overlay, "mask_data") and overlay_any.mask_data:
        mask_bytes = overlay_any.mask_data
        mask_width_bytes = overlay_any.mask_width_bytes

        for y in range(height):
            for x in range(width):
                byte_idx = (x // 8) + (y * mask_width_bytes)
                bit_pos = x % 8
                if byte_idx < len(mask_bytes):
                    mask_bit = (mask_bytes[byte_idx] >> bit_pos) & 1
                else:
                    mask_bit = 0

                # DotClk DotBlt logic: mask=0 copy overlay, mask=1 keep base
                if mask_bit == 0:
                    idx = y * width + x
                    base_data[idx] = overlay_data[idx]

        return Image.frombytes("L", (width, height), bytes(base_data))
    else:
        # No mask: treat as fully opaque (mask=0 everywhere)
        return overlay.copy()


def overlay_or_rgb(
    base: Image.Image,
    overlay: Image.Image,
    base_color: Tuple[int, int, int],
    overlay_color: Tuple[int, int, int],
) -> Image.Image:
    """Combine grayscale images with different colors for each layer"""
    width, height = base.size
    base_data = base.tobytes()
    overlay_data = overlay.tobytes()
    rgb_data = bytearray(width * height * 3)

    # Start with base colorized
    for i, pixel in enumerate(base_data):
        if pixel > 0:
            offset = i * 3
            rgb_data[offset] = (base_color[0] * pixel) // 255
            rgb_data[offset + 1] = (base_color[1] * pixel) // 255
            rgb_data[offset + 2] = (base_color[2] * pixel) // 255

    # Apply overlay with mask
    overlay_any: Any = overlay
    if hasattr(overlay, "mask_data") and overlay_any.mask_data:
        mask_bytes = overlay_any.mask_data
        mask_width_bytes = overlay_any.mask_width_bytes

        for y in range(height):
            for x in range(width):
                byte_idx = (x // 8) + (y * mask_width_bytes)
                bit_pos = x % 8
                if byte_idx < len(mask_bytes):
                    mask_bit = (mask_bytes[byte_idx] >> bit_pos) & 1
                else:
                    mask_bit = 0

                # Where mask=0, apply overlay color
                if mask_bit == 0:
                    idx = y * width + x
                    pixel = overlay_data[idx]
                    offset = idx * 3
                    rgb_data[offset] = (overlay_color[0] * pixel) // 255
                    rgb_data[offset + 1] = (overlay_color[1] * pixel) // 255
                    rgb_data[offset + 2] = (overlay_color[2] * pixel) // 255
    else:
        # No mask: apply overlay color everywhere
        for i, pixel in enumerate(overlay_data):
            offset = i * 3
            rgb_data[offset] = (overlay_color[0] * pixel) // 255
            rgb_data[offset + 1] = (overlay_color[1] * pixel) // 255
            rgb_data[offset + 2] = (overlay_color[2] * pixel) // 255

    return Image.frombytes("RGB", (width, height), bytes(rgb_data))
