#!/usr/bin/env python3
"""Generate weather_icons.py from Noto Color Emoji font.

Renders weather emoji at 16x16 (SD) and 32x32 (HD) and embeds the pixel
data as raw bytes. The HD versions are rendered natively at 32x32 from
the emoji font (not upscaled from 16x16) for maximum quality.

Requires: Noto Color Emoji font installed at /usr/share/fonts/truetype/noto/NotoColorEmoji.ttf

Usage: python3 scripts/gen_weather_icons.py
"""

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


def render_emoji(font, emoji_char: str, size: int = 16) -> Image.Image:
    """Render an emoji character to a size x size RGB image."""
    # Render at high resolution then downscale for quality
    render_size = 150
    img = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((5, 5), emoji_char, font=font, embedded_color=True)
    bbox = img.getbbox()
    if not bbox:
        raise ValueError(f"Emoji '{emoji_char}' did not render")
    cropped = img.crop(bbox)

    # Resize preserving aspect ratio, fit within target size
    w, h = cropped.size
    scale = min(size / w, size / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = cropped.resize((new_w, new_h), Image.LANCZOS)

    # Center on black canvas
    rgb = Image.new("RGB", (size, size), (0, 0, 0))
    rgba_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    rgba_canvas.paste(resized, (offset_x, offset_y))
    rgb.paste(rgba_canvas, mask=rgba_canvas.split()[3])
    return rgb


def main():
    if not Path(FONT_PATH).exists():
        print(f"Error: Font not found at {FONT_PATH}")
        print("Install with: sudo apt install fonts-noto-color-emoji")
        sys.exit(1)

    font = ImageFont.truetype(FONT_PATH, 109)

    # Render all icons at both SD (16x16) and HD (32x32)
    icon_data_sd = {}
    icon_data_hd = {}
    for name, emoji in EMOJIS.items():
        try:
            img_sd = render_emoji(font, emoji, size=16)
            img_hd = render_emoji(font, emoji, size=32)
            icon_data_sd[name] = img_sd.tobytes()
            icon_data_hd[name] = img_hd.tobytes()
            print(f"  {name}: OK (16x16 + 32x32)")
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
            sys.exit(1)

    # Generate output file
    lines = []
    lines.append(
        '"""Color weather icons rendered from Noto Color Emoji (SD 16x16 + HD 32x32).'
    )
    lines.append("")
    lines.append("Icons are pre-rendered from the Noto Color Emoji font (SIL OFL).")
    lines.append("https://fonts.google.com/noto/specimen/Noto+Color+Emoji")
    lines.append("")
    lines.append("SD icons (16x16) are used for 128x32 displays.")
    lines.append("HD icons (32x32) are used for 256x64 displays.")
    lines.append('"""')
    lines.append("")
    lines.append("from typing import Dict")
    lines.append("")
    lines.append("from PIL import Image")
    lines.append("")

    # Write SD icons
    lines.append("# === SD Icons (16x16) ===")
    lines.append("")
    for name, raw_bytes in icon_data_sd.items():
        hex_str = raw_bytes.hex()
        lines.append(f'_{name.upper()}_HEX = "{hex_str}"')
        lines.append("")

    # Write HD icons
    lines.append("")
    lines.append("# === HD Icons (32x32) ===")
    lines.append("")
    for name, raw_bytes in icon_data_hd.items():
        hex_str = raw_bytes.hex()
        lines.append(f'_{name.upper()}_HD_HEX = "{hex_str}"')
        lines.append("")

    lines.append("")
    lines.append("def _hex_to_image(hex_data: str, size: int = 16) -> Image.Image:")
    lines.append('    """Convert hex-encoded RGB data to a PIL Image."""')
    lines.append(
        '    return Image.frombytes("RGB", (size, size), bytes.fromhex(hex_data))'
    )
    lines.append("")
    lines.append("")
    lines.append("# Build icon images from embedded data")
    lines.append("_ICON_IMAGES_SD: Dict[str, Image.Image] = {")
    for name in icon_data_sd:
        lines.append(f'    "{name}": _hex_to_image(_{name.upper()}_HEX, 16),')
    lines.append("}")
    lines.append("")
    lines.append("_ICON_IMAGES_HD: Dict[str, Image.Image] = {")
    for name in icon_data_hd:
        lines.append(f'    "{name}": _hex_to_image(_{name.upper()}_HD_HEX, 32),')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("# Map WMO weather codes to icon keys")
    lines.append("WMO_CODE_TO_ICON: Dict[int, str] = {")
    wmo_map = [
        (0, "sun"),
        (1, "partial_cloud"),
        (2, "partial_cloud"),
        (3, "cloud"),
        (45, "fog"),
        (48, "fog"),
        (51, "light_rain"),
        (53, "light_rain"),
        (55, "light_rain"),
        (56, "light_rain"),
        (57, "light_rain"),
        (61, "rain"),
        (63, "rain"),
        (65, "rain"),
        (66, "rain"),
        (67, "rain"),
        (71, "snow"),
        (73, "snow"),
        (75, "snow"),
        (77, "snow"),
        (80, "rain"),
        (81, "rain"),
        (82, "rain"),
        (85, "snow"),
        (86, "snow"),
        (95, "thunderstorm"),
        (96, "thunderstorm"),
        (99, "thunderstorm"),
    ]
    for code, icon in wmo_map:
        lines.append(f'    {code}: "{icon}",')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append(
        "def get_weather_icon_image(code: int, hd: bool = False) -> Image.Image:"
    )
    lines.append('    """Get the color RGB icon for a WMO weather code.')
    lines.append("")
    lines.append("    Args:")
    lines.append("        code: WMO weather interpretation code.")
    lines.append("        hd: If True, return 32x32 HD icon. Otherwise 16x16 SD.")
    lines.append("")
    lines.append("    Returns:")
    lines.append("        PIL Image (16x16 or 32x32 RGB).")
    lines.append('    """')
    lines.append('    icon_key = WMO_CODE_TO_ICON.get(code, "cloud")')
    lines.append("    icons = _ICON_IMAGES_HD if hd else _ICON_IMAGES_SD")
    lines.append("    return icons[icon_key].copy()")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"\nWritten to {OUTPUT_PATH} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
