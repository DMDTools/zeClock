#!/usr/bin/env python3
"""Convert any emoji to a 16x16 RGB pixel-art icon.

Renders emoji from Noto Color Emoji font and outputs the pixel data
as a hex string that can be used with PIL Image.frombytes().

Usage:
    # Render a single emoji and print hex data
    python3 scripts/emoji_to_icon.py "☀️"

    # Render and save as PNG (scaled up for viewing)
    python3 scripts/emoji_to_icon.py "🌧️" --save rain.png

    # Render at a different size (default 16)
    python3 scripts/emoji_to_icon.py "❄️" --size 32

    # Output Python code ready to paste
    python3 scripts/emoji_to_icon.py "⛈️" --python thunderstorm

    # Batch mode: render multiple emojis
    python3 scripts/emoji_to_icon.py "☀️" "☁️" "🌧️" --python sun cloud rain

Requires: fonts-noto-color-emoji (sudo apt install fonts-noto-color-emoji)
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFont, ImageDraw

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
FONT_SIZE = 109  # Noto Color Emoji native bitmap size


def render_emoji(emoji_char: str, size: int = 16) -> Image.Image:
    """Render an emoji character to an RGB image, preserving aspect ratio.

    Args:
        emoji_char: The emoji string to render.
        size: Target icon size in pixels (square).

    Returns:
        PIL Image in RGB mode at (size, size).
    """
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    img = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((5, 5), emoji_char, font=font, embedded_color=True)
    bbox = img.getbbox()
    if not bbox:
        raise ValueError(f"Emoji '{emoji_char}' did not render (no glyph found)")
    cropped = img.crop(bbox)

    # Resize preserving aspect ratio, fit within size x size
    w, h = cropped.size
    scale = min(size / w, size / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    # Center on canvas
    rgb = Image.new("RGB", (size, size), (0, 0, 0))
    rgba_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    rgba_canvas.paste(resized, (offset_x, offset_y))
    rgb.paste(rgba_canvas, mask=rgba_canvas.split()[3])
    return rgb


def image_to_hex(img: Image.Image) -> str:
    """Convert a PIL Image to a hex string of raw RGB bytes."""
    return img.tobytes().hex()


def print_ascii_preview(img: Image.Image):
    """Print a small ASCII art preview of the icon."""
    import numpy as np

    arr = np.array(img)
    for y in range(img.height):
        row = ""
        for x in range(img.width):
            r, g, b = arr[y, x]
            if r + g + b < 30:
                row += "."
            elif r + g + b > 500:
                row += "#"
            else:
                row += "o"
        print(f"  {row}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert emoji to pixel-art icons for DMD displays"
    )
    parser.add_argument("emojis", nargs="+", help="Emoji character(s) to render")
    parser.add_argument(
        "--size", type=int, default=16, help="Icon size in pixels (default: 16)"
    )
    parser.add_argument(
        "--save",
        nargs="*",
        default=None,
        help="Save as PNG file(s). Scaled 8x for visibility.",
    )
    parser.add_argument(
        "--python",
        nargs="*",
        default=None,
        help="Output Python variable name(s) for the hex data",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=True,
        help="Show ASCII preview (default: on)",
    )
    parser.add_argument(
        "--no-preview", action="store_true", help="Suppress ASCII preview"
    )

    args = parser.parse_args()

    if not Path(FONT_PATH).exists():
        print(f"Error: Noto Color Emoji font not found at {FONT_PATH}")
        print("Install with: sudo apt install fonts-noto-color-emoji")
        sys.exit(1)

    names = args.python if args.python else [None] * len(args.emojis)
    save_paths = args.save if args.save else [None] * len(args.emojis)

    if len(names) < len(args.emojis):
        names.extend([None] * (len(args.emojis) - len(names)))
    if len(save_paths) < len(args.emojis):
        save_paths.extend([None] * (len(args.emojis) - len(save_paths)))

    for emoji, name, save_path in zip(args.emojis, names, save_paths):
        print(f"\n{'='*50}")
        print(f"Emoji: {emoji}")
        print(f"{'='*50}")

        try:
            img = render_emoji(emoji, args.size)
        except ValueError as e:
            print(f"  Error: {e}")
            continue

        # ASCII preview
        if not args.no_preview:
            print_ascii_preview(img)

        # Hex output
        hex_data = image_to_hex(img)
        print(f"\n  Size: {img.size[0]}x{img.size[1]}")
        print(f"  Bytes: {len(hex_data)//2}")

        # Python output
        if name:
            print(f"\n  # Paste into weather_icons.py:")
            print(f'  _{name.upper()}_HEX = "{hex_data}"')
            print(f"  # Then add to _ICON_IMAGES:")
            print(f'  #   "{name}": _hex_to_image(_{name.upper()}_HEX),')

        # Save PNG
        if save_path:
            # Save scaled up for visibility
            scaled = img.resize((img.width * 8, img.height * 8), Image.NEAREST)
            scaled.save(save_path)
            print(f"\n  Saved (8x scaled): {save_path}")
            # Also save original size
            orig_path = save_path.replace(".png", "_16x.png")
            img.save(orig_path)
            print(f"  Saved (original):  {orig_path}")


if __name__ == "__main__":
    main()
