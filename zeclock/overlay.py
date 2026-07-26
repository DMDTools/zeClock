from PIL import Image
from typing import Any, Dict, List, Tuple

# LUT cache: maps color tuple -> (r_lut, g_lut, b_lut) as lists of ints
_colorize_lut_cache: Dict[
    Tuple[int, int, int], Tuple[List[int], List[int], List[int]]
] = {}

# Pre-built LUT: expand each byte value (0-255) into 8 mask pixels (0 or 255)
_BYTE_TO_MASK = [
    bytes([255 if (b >> bit) & 1 else 0 for bit in range(8)]) for b in range(256)
]


# ==============================================================================
# Pixel-art upscaling
# ==============================================================================


def epx_upscale_2x(img: Image.Image) -> Image.Image:
    """Upscale a grayscale PIL Image 2x using the EPX/Scale2x algorithm.

    EPX (Eric's Pixel Expansion) smooths diagonal edges and corners while
    preserving the pixel-art style. Unlike nearest-neighbor, it produces
    cleaner diagonals without introducing new colors or blurring.

    A hole-prevention rule ensures filled pixels are never replaced by empty
    ones, avoiding gaps at inner corners of shapes (e.g., inside an "E").

    Works on mode "L" (grayscale) images. Mask data (DotBlt overlay masks
    stored as dynamic attributes) is also upscaled if present.

    See: https://en.wikipedia.org/wiki/Pixel-art_scaling_algorithms#EPX/Scale2x

    Args:
        img: Source PIL Image in 'L' (grayscale) mode.

    Returns:
        2x upscaled PIL Image in 'L' mode.
    """
    src_w, src_h = img.size
    dst_w, dst_h = src_w * 2, src_h * 2
    src_data = img.tobytes()

    def px(x: int, y: int) -> int:
        return src_data[max(0, min(src_h - 1, y)) * src_w + max(0, min(src_w - 1, x))]

    dst_data = bytearray(dst_w * dst_h)

    for y in range(src_h):
        for x in range(src_w):
            e = px(x, y)
            a = px(x, y - 1)  # top
            b = px(x + 1, y)  # right
            c = px(x - 1, y)  # left
            d = px(x, y + 1)  # bottom

            e0 = e1 = e2 = e3 = e

            # EPX rules with hole prevention
            if c == a and c != d and a != b:
                if not (e > 0 and a == 0):
                    e0 = a
            if a == b and a != c and b != d:
                if not (e > 0 and b == 0):
                    e1 = b
            if c == d and c != a and d != b:
                if not (e > 0 and c == 0):
                    e2 = c
            if d == b and d != c and b != a:
                if not (e > 0 and d == 0):
                    e3 = d

            dst_data[y * 2 * dst_w + x * 2] = e0
            dst_data[y * 2 * dst_w + x * 2 + 1] = e1
            dst_data[(y * 2 + 1) * dst_w + x * 2] = e2
            dst_data[(y * 2 + 1) * dst_w + x * 2 + 1] = e3

    dst = Image.frombytes("L", (dst_w, dst_h), bytes(dst_data))

    # Preserve DotBlt mask data if present
    src_any: Any = img
    if hasattr(img, "mask_data") and src_any.mask_data:
        dst_any: Any = dst
        dst_any.mask_data = _upscale_mask_nx(
            src_any.mask_data, src_any.mask_width_bytes, src_w, src_h, 2, dst_w, dst_h
        )
        dst_any.mask_width_bytes = (dst_w // 8) + (1 if dst_w % 8 else 0)

    return dst


def nearest_upscale_2x(img: Image.Image) -> Image.Image:
    """Upscale a PIL Image 2x using nearest-neighbor (simple pixel doubling).

    Each pixel becomes a 2×2 block. Fastest upscaling method, preserves
    exact pixel values. Works on any PIL image mode.

    Mask data (DotBlt overlay masks) is also upscaled if present.

    Args:
        img: Source PIL Image.

    Returns:
        2x upscaled PIL Image in the same mode.
    """
    dst_w, dst_h = img.size[0] * 2, img.size[1] * 2
    dst = img.resize((dst_w, dst_h), Image.Resampling.NEAREST)

    # Preserve DotBlt mask data if present
    src_any: Any = img
    if hasattr(img, "mask_data") and src_any.mask_data:
        src_w, src_h = img.size
        dst_any: Any = dst
        dst_any.mask_data = _upscale_mask_nx(
            src_any.mask_data, src_any.mask_width_bytes, src_w, src_h, 2, dst_w, dst_h
        )
        dst_any.mask_width_bytes = (dst_w // 8) + (1 if dst_w % 8 else 0)

    return dst


def upscale_2x(img: Image.Image, mode: str = "epx") -> Image.Image:
    """Upscale a PIL Image 2x using the specified algorithm.

    Dispatcher for pixel-art upscaling. Use this as the single entry point
    for all 2x upscaling in zeClock.

    Args:
        img: Source PIL Image.
        mode: Upscaling algorithm:
            - "epx" (default): EPX/Scale2x — smooths diagonals and corners,
              no new colors. Best for strict pixel-art.
              See https://en.wikipedia.org/wiki/Pixel-art_scaling_algorithms
            - "hq2x": High-quality 2x — smoother curves and anti-aliased
              diagonals via interpolation. May introduce intermediate values.
              Best quality for pre-computed content (fonts, animations).
            - "nearest": Simple pixel doubling. Fastest, no smoothing.

    Returns:
        2x upscaled PIL Image.
    """
    if mode == "epx":
        return epx_upscale_2x(img)
    if mode == "hq2x":
        return hq2x(img)
    return nearest_upscale_2x(img)


# ==============================================================================
# hq2x — High-quality 2x upscaling
# ==============================================================================

# hq2x threshold: pixels with absolute difference <= this are considered "equal"
_HQ2X_THRESHOLD = 30

# hq2x blend table: 256 entries, each a tuple of 4 blend functions for the
# 4 output pixels (top-left, top-right, bottom-left, bottom-right).
# Each blend function is a tuple of (weights for [E, A, B, C, D, F, G, H, I])
# where the neighborhood is:
#   A B C
#   D E F
#   G H I
# Weights are integers; output = weighted_average(neighbors) / sum(weights).
# We use a simplified version with only the most common patterns.
#
# Reference: Maxim Stepin's original hq2x C implementation
# https://web.archive.org/web/20131205091805/http://www.hiend3d.com/hq2x.html


def _hq2x_blend(w1: int, w2: int, c1: int, c2: int) -> int:
    """Blend two pixel values with given weights."""
    return (w1 * c1 + w2 * c2) // (w1 + w2)


def _hq2x_blend3(w1: int, w2: int, w3: int, c1: int, c2: int, c3: int) -> int:
    """Blend three pixel values with given weights."""
    return (w1 * c1 + w2 * c2 + w3 * c3) // (w1 + w2 + w3)


def hq2x(img: Image.Image) -> Image.Image:
    """Upscale a grayscale PIL Image 2x using the hq2x algorithm.

    hq2x (High Quality 2x) by Maxim Stepin produces smoother curves and
    anti-aliased diagonals by interpolating between neighboring pixel values.
    Unlike EPX, it may introduce intermediate gray values, giving a more
    "painted" look with smoother edges.

    Best used for pre-computed content (pinball animations, fonts) where
    the upscaling happens once at initialization, not per-frame.

    Works on mode "L" (grayscale) images. Mask data is upscaled with
    nearest-neighbor (interpolated masks would break DotBlt compositing).

    See: https://en.wikipedia.org/wiki/Pixel-art_scaling_algorithms#hq2x

    Args:
        img: Source PIL Image in 'L' (grayscale) mode.

    Returns:
        2x upscaled PIL Image in 'L' mode.
    """
    src_w, src_h = img.size
    dst_w, dst_h = src_w * 2, src_h * 2
    src_data = img.tobytes()
    dst_data = bytearray(dst_w * dst_h)

    def px(x: int, y: int) -> int:
        return src_data[max(0, min(src_h - 1, y)) * src_w + max(0, min(src_w - 1, x))]

    def diff(a: int, b: int) -> bool:
        return abs(a - b) > _HQ2X_THRESHOLD

    for y in range(src_h):
        for x in range(src_w):
            # 3x3 neighborhood
            a = px(x - 1, y - 1)
            b = px(x, y - 1)
            c = px(x + 1, y - 1)
            d = px(x - 1, y)
            e = px(x, y)
            f = px(x + 1, y)
            g = px(x - 1, y + 1)
            h = px(x, y + 1)
            i = px(x + 1, y + 1)

            # Build difference bitmask (8 neighbors)
            # Bit 0=A, 1=B, 2=C, 3=D, 4=F, 5=G, 6=H, 7=I
            pattern = (
                (1 if diff(e, a) else 0)
                | (2 if diff(e, b) else 0)
                | (4 if diff(e, c) else 0)
                | (8 if diff(e, d) else 0)
                | (16 if diff(e, f) else 0)
                | (32 if diff(e, g) else 0)
                | (64 if diff(e, h) else 0)
                | (128 if diff(e, i) else 0)
            )

            # Output pixel positions
            ox, oy = x * 2, y * 2

            # hq2x blending rules based on pattern
            # Each output pixel is a blend of E with its relevant neighbors.
            # Rules derived from the original hq2x lookup table logic.

            # Top-left output pixel (e0)
            if not diff(e, d) and not diff(e, b):
                # Corner: blend E with D and B
                e0 = _hq2x_blend3(2, 1, 1, e, d, b)
            elif not diff(e, d):
                e0 = _hq2x_blend(3, 1, e, d)
            elif not diff(e, b):
                e0 = _hq2x_blend(3, 1, e, b)
            else:
                e0 = e

            # Top-right output pixel (e1)
            if not diff(e, b) and not diff(e, f):
                e1 = _hq2x_blend3(2, 1, 1, e, b, f)
            elif not diff(e, b):
                e1 = _hq2x_blend(3, 1, e, b)
            elif not diff(e, f):
                e1 = _hq2x_blend(3, 1, e, f)
            else:
                e1 = e

            # Bottom-left output pixel (e2)
            if not diff(e, d) and not diff(e, h):
                e2 = _hq2x_blend3(2, 1, 1, e, d, h)
            elif not diff(e, d):
                e2 = _hq2x_blend(3, 1, e, d)
            elif not diff(e, h):
                e2 = _hq2x_blend(3, 1, e, h)
            else:
                e2 = e

            # Bottom-right output pixel (e3)
            if not diff(e, f) and not diff(e, h):
                e3 = _hq2x_blend3(2, 1, 1, e, f, h)
            elif not diff(e, f):
                e3 = _hq2x_blend(3, 1, e, f)
            elif not diff(e, h):
                e3 = _hq2x_blend(3, 1, e, h)
            else:
                e3 = e

            # Anti-diagonal correction: if a diagonal edge is detected,
            # sharpen the corner pixels to avoid blurring across the edge.
            # This is the key hq2x insight: detect diagonal lines and
            # preserve their sharpness.
            if diff(e, a) and not diff(d, b):
                # Top-left corner: diagonal edge from top-left
                e0 = _hq2x_blend(3, 1, e0, _hq2x_blend(1, 1, d, b))
            if diff(e, c) and not diff(b, f):
                e1 = _hq2x_blend(3, 1, e1, _hq2x_blend(1, 1, b, f))
            if diff(e, g) and not diff(d, h):
                e2 = _hq2x_blend(3, 1, e2, _hq2x_blend(1, 1, d, h))
            if diff(e, i) and not diff(f, h):
                e3 = _hq2x_blend(3, 1, e3, _hq2x_blend(1, 1, f, h))

            # Suppress unused variable warning
            _ = pattern

            dst_data[oy * dst_w + ox] = e0
            dst_data[oy * dst_w + ox + 1] = e1
            dst_data[(oy + 1) * dst_w + ox] = e2
            dst_data[(oy + 1) * dst_w + ox + 1] = e3

    dst = Image.frombytes("L", (dst_w, dst_h), bytes(dst_data))

    # Preserve DotBlt mask data — use nearest-neighbor (not interpolated)
    # because interpolated masks would break the DotBlt compositing logic.
    src_any: Any = img
    if hasattr(img, "mask_data") and src_any.mask_data:
        dst_any: Any = dst
        dst_any.mask_data = _upscale_mask_nx(
            src_any.mask_data, src_any.mask_width_bytes, src_w, src_h, 2, dst_w, dst_h
        )
        dst_any.mask_width_bytes = (dst_w // 8) + (1 if dst_w % 8 else 0)

    return dst


def scale3x(img: Image.Image) -> Image.Image:
    """Upscale a grayscale PIL Image 3x using the Scale3x/AdvMAME3x algorithm.

    Scale3x is a generalization of EPX to the 3x case. Each source pixel
    expands to a 3×3 block of output pixels. Corner pixels use the same
    logic as EPX; edge pixels use additional neighbor comparisons.

    Like EPX, it never introduces new colors and preserves the pixel-art
    style. Useful for 3x scale factors (e.g., 128x32 → 384x96).

    See: https://en.wikipedia.org/wiki/Pixel-art_scaling_algorithms#Scale3x

    Args:
        img: Source PIL Image in 'L' (grayscale) mode.

    Returns:
        3x upscaled PIL Image in 'L' mode.
    """
    src_w, src_h = img.size
    dst_w, dst_h = src_w * 3, src_h * 3
    src_data = img.tobytes()

    def px(x: int, y: int) -> int:
        return src_data[max(0, min(src_h - 1, y)) * src_w + max(0, min(src_w - 1, x))]

    dst_data = bytearray(dst_w * dst_h)

    def set_px(dx: int, dy: int, val: int) -> None:
        dst_data[dy * dst_w + dx] = val

    for y in range(src_h):
        for x in range(src_w):
            # 3x3 neighborhood: A-I with E as center
            #  A B C
            #  D E F
            #  G H I
            a = px(x - 1, y - 1)
            b = px(x, y - 1)
            c = px(x + 1, y - 1)
            d = px(x - 1, y)
            e = px(x, y)
            f = px(x + 1, y)
            g = px(x - 1, y + 1)
            h = px(x, y + 1)
            i = px(x + 1, y + 1)

            # Output 3x3 block positions (ox, oy) = (x*3, y*3)
            ox, oy = x * 3, y * 3

            # Default: all 9 output pixels = E
            e1 = e2 = e3 = e4 = e5 = e6 = e7 = e8 = e9 = e

            # Scale3x rules
            if d == b and d != h and b != f:
                e1 = d
            if (d == b and d != h and b != f and e != c) or (
                b == f and b != d and f != h and e != a
            ):
                e2 = b
            if b == f and b != d and f != h:
                e3 = f
            if (h == d and h != f and d != b and e != a) or (
                d == b and d != h and b != f and e != g
            ):
                e4 = d
            # e5 = e (center always stays)
            if (b == f and b != d and f != h and e != i) or (
                f == h and f != b and h != d and e != c
            ):
                e6 = f
            if h == d and h != f and d != b:
                e7 = d
            if (f == h and f != b and h != d and e != g) or (
                h == d and h != f and d != b and e != i
            ):
                e8 = h
            if f == h and f != b and h != d:
                e9 = f

            set_px(ox, oy, e1)
            set_px(ox + 1, oy, e2)
            set_px(ox + 2, oy, e3)
            set_px(ox, oy + 1, e4)
            set_px(ox + 1, oy + 1, e5)
            set_px(ox + 2, oy + 1, e6)
            set_px(ox, oy + 2, e7)
            set_px(ox + 1, oy + 2, e8)
            set_px(ox + 2, oy + 2, e9)

    dst = Image.frombytes("L", (dst_w, dst_h), bytes(dst_data))

    # Preserve DotBlt mask data if present
    src_any: Any = img
    if hasattr(img, "mask_data") and src_any.mask_data:
        dst_any: Any = dst
        dst_any.mask_data = _upscale_mask_nx(
            src_any.mask_data, src_any.mask_width_bytes, src_w, src_h, 3, dst_w, dst_h
        )
        dst_any.mask_width_bytes = (dst_w // 8) + (1 if dst_w % 8 else 0)

    return dst


def upscale_nx(img: Image.Image, scale: int, mode: str = "epx") -> Image.Image:
    """Upscale a PIL Image by an arbitrary integer scale factor.

    For scale=2, uses the selected algorithm (epx, hq2x, or nearest).
    For scale=3, uses Scale3x (if mode="epx") or nearest.
    For other scales, falls back to nearest-neighbor.

    Args:
        img: Source PIL Image.
        scale: Integer scale factor (2, 3, 4, ...).
        mode: "epx", "hq2x", or "nearest".

    Returns:
        Upscaled PIL Image.
    """
    if scale == 1:
        return img
    if scale == 2:
        return upscale_2x(img, mode=mode)
    if scale == 3 and mode in ("epx", "hq2x"):
        return scale3x(img)
    # Fallback: nearest-neighbor for any scale
    dst_w, dst_h = img.size[0] * scale, img.size[1] * scale
    dst = img.resize((dst_w, dst_h), Image.Resampling.NEAREST)
    src_any: Any = img
    if hasattr(img, "mask_data") and src_any.mask_data:
        src_w, src_h = img.size
        dst_any: Any = dst
        dst_any.mask_data = _upscale_mask_nx(
            src_any.mask_data,
            src_any.mask_width_bytes,
            src_w,
            src_h,
            scale,
            dst_w,
            dst_h,
        )
        dst_any.mask_width_bytes = (dst_w // 8) + (1 if dst_w % 8 else 0)
    return dst


def _upscale_mask_2x(
    mask_data: bytes,
    mask_width_bytes: int,
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> bytes:
    """Upscale a DotBlt bit-mask 2x (each set bit → 2×2 block).

    Internal helper used by epx_upscale_2x and nearest_upscale_2x.
    """
    return _upscale_mask_nx(mask_data, mask_width_bytes, src_w, src_h, 2, dst_w, dst_h)


def _upscale_mask_nx(
    mask_data: bytes,
    mask_width_bytes: int,
    src_w: int,
    src_h: int,
    scale: int,
    dst_w: int,
    dst_h: int,
) -> bytes:
    """Upscale a DotBlt bit-mask by an integer scale factor.

    Each set bit in the source becomes a scale×scale block in the output.
    Internal helper shared by all upscale functions.
    """
    dst_wb = (dst_w // 8) + (1 if dst_w % 8 else 0)
    dst_mask = bytearray(dst_wb * dst_h)

    for y in range(src_h):
        src_row = y * mask_width_bytes
        for x in range(src_w):
            sb = (x >> 3) + src_row
            if sb < len(mask_data) and (mask_data[sb] >> (x & 7)) & 1:
                for dy in range(scale):
                    for dx in range(scale):
                        nx = x * scale + dx
                        ny = y * scale + dy
                        db = (nx >> 3) + ny * dst_wb
                        dst_mask[db] |= 1 << (nx & 7)

    return bytes(dst_mask)


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


def _unpack_bitmask(
    mask_bytes: bytes, mask_width_bytes: int, width: int, height: int
) -> Image.Image:
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
            byte_val = (
                mask_bytes[row_offset + byte_idx]
                if (row_offset + byte_idx) < len(mask_bytes)
                else 0
            )
            if byte_val:
                base_x = byte_idx * 8
                end = min(8, width - base_x)
                mask_data[out_row + base_x : out_row + base_x + end] = _BYTE_TO_MASK[
                    byte_val
                ][:end]
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


# Threshold for font outline pixels (nibble 0 maps to gray value 2)
_FONT_OUTLINE_THRESHOLD = 2


def overlay_clock_above(
    base: Image.Image,
    overlay: Image.Image,
    base_color: Tuple[int, int, int],
    overlay_color: Tuple[int, int, int],
) -> Image.Image:
    """Composite clock overlay above animation using pixel-based transparency.

    Used when frame_layer=1 (clock drawn on top of animation). Unlike
    overlay_or_rgb which uses the DotBlt bit-mask, this function treats
    overlay pixels with value <= _FONT_OUTLINE_THRESHOLD as transparent,
    letting the base (animation) show through everywhere the clock has no
    visible content.

    This fixes scenes where the clock's DotBlt mask only marks outline
    pixels as transparent, leaving the black background opaque and
    incorrectly erasing the animation underneath.

    Args:
        base: Grayscale animation frame (mode 'L').
        overlay: Grayscale clock frame (mode 'L').
        base_color: RGB color for the animation.
        overlay_color: RGB color for the clock text.

    Returns:
        Merged RGB PIL Image with clock digits over animation.
    """
    width, height = base.size

    # Build transparency mask from overlay pixel values:
    # mask=255 (transparent, show base) where overlay pixel <= threshold
    # mask=0 (opaque, show overlay) where overlay pixel > threshold
    overlay_bytes = overlay.tobytes()
    threshold = _FONT_OUTLINE_THRESHOLD
    mask_data = bytes(255 if p <= threshold else 0 for p in overlay_bytes)
    mask_img = Image.frombytes("L", (width, height), mask_data)

    base_rgb = colorize_grayscale(base, base_color)
    overlay_rgb = colorize_grayscale(overlay, overlay_color)

    return Image.composite(base_rgb, overlay_rgb, mask_img)
