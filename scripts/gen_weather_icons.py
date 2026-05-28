#!/usr/bin/env python3
"""Generate weather_icons.py from Noto Color Emoji font.

Renders weather emoji at 16x16 and embeds the pixel data as raw bytes.
Requires: Noto Color Emoji font installed at /usr/share/fonts/truetype/noto/NotoColorEmoji.ttf

Usage: python3 scripts/gen_weather_icons.py
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageFont, ImageDraw

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
OUTPUT_PATH = Path(__file__).parent.parent / "zeclock" / "plugins" / "weather_icons.py"

EMOJIS = {
    "sun": "☀️",
    "partial_cloud": "⛅",
    "cloud": "☁️",
    "light_rain": "🌧️",
    "rain": "🌧️",
    "snow": "❄️",
    "thunderstorm": "⛈️",
    "fog": "🌫️",
}


def render_emoji(font, emoji_char: str) -> Image.Image:
    """Render an emoji character to a 16x16 RGB image, preserving aspect ratio."""
    img = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((5, 5), emoji_char, font=font, embedded_color=True)
    bbox = img.getbbox()
    if not bbox:
        raise ValueError(f"Emoji '{emoji_char}' did not render")
    cropped = img.crop(bbox)

    # Resize preserving aspect ratio, fit within 16x16
    w, h = cropped.size
    scale = min(16 / w, 16 / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    # Center on 16x16 black canvas
    rgb = Image.new("RGB", (16, 16), (0, 0, 0))
    rgba_canvas = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    offset_x = (16 - new_w) // 2
    offset_y = (16 - new_h) // 2
    rgba_canvas.paste(resized, (offset_x, offset_y))
    rgb.paste(rgba_canvas, mask=rgba_canvas.split()[3])
    return rgb


def main():
    if not Path(FONT_PATH).exists():
        print(f"Error: Font not found at {FONT_PATH}")
        print("Install with: sudo apt install fonts-noto-color-emoji")
        sys.exit(1)

    font = ImageFont.truetype(FONT_PATH, 109)

    # Render all icons
    icon_data = {}
    for name, emoji in EMOJIS.items():
        try:
            img = render_emoji(font, emoji)
            icon_data[name] = img.tobytes()
            print(f"  {name}: OK")
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
            sys.exit(1)

    # Generate output file
    lines = []
    lines.append('"""Color 16x16 weather icons rendered from Noto Color Emoji.')
    lines.append("")
    lines.append("Icons are pre-rendered from the Noto Color Emoji font (SIL OFL).")
    lines.append("https://fonts.google.com/noto/specimen/Noto+Color+Emoji")
    lines.append('"""')
    lines.append("")
    lines.append("from typing import Dict")
    lines.append("")
    lines.append("from PIL import Image")
    lines.append("")

    # Write each icon as raw bytes
    for name, raw_bytes in icon_data.items():
        # Encode as hex string for compact storage
        hex_str = raw_bytes.hex()
        lines.append(f'_{name.upper()}_HEX = "{hex_str}"')
        lines.append("")

    lines.append("")
    lines.append("def _hex_to_image(hex_data: str) -> Image.Image:")
    lines.append('    """Convert hex-encoded RGB data to a 16x16 PIL Image."""')
    lines.append('    return Image.frombytes("RGB", (16, 16), bytes.fromhex(hex_data))')
    lines.append("")
    lines.append("")
    lines.append("# Build icon images from embedded data")
    lines.append("_ICON_IMAGES: Dict[str, Image.Image] = {")
    for name in icon_data:
        lines.append(f'    "{name}": _hex_to_image(_{name.upper()}_HEX),')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("# Map WMO weather codes to icon keys")
    lines.append("WMO_CODE_TO_ICON: Dict[int, str] = {")
    wmo_map = [
        (0, "sun"), (1, "partial_cloud"), (2, "partial_cloud"), (3, "cloud"),
        (45, "fog"), (48, "fog"),
        (51, "light_rain"), (53, "light_rain"), (55, "light_rain"),
        (56, "light_rain"), (57, "light_rain"),
        (61, "rain"), (63, "rain"), (65, "rain"), (66, "rain"), (67, "rain"),
        (71, "snow"), (73, "snow"), (75, "snow"), (77, "snow"),
        (80, "rain"), (81, "rain"), (82, "rain"),
        (85, "snow"), (86, "snow"),
        (95, "thunderstorm"), (96, "thunderstorm"), (99, "thunderstorm"),
    ]
    for code, icon in wmo_map:
        lines.append(f'    {code}: "{icon}",')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def get_weather_icon_image(code: int) -> Image.Image:")
    lines.append('    """Get the 16x16 color RGB icon for a WMO weather code."""')
    lines.append('    icon_key = WMO_CODE_TO_ICON.get(code, "cloud")')
    lines.append("    return _ICON_IMAGES[icon_key].copy()")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"\nWritten to {OUTPUT_PATH} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
