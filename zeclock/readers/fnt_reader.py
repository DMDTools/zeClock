"""
Bitmap font loader (.fnt)
Format: Version + FontNameLen + FontName + CntFontInfo + FontCharInfo[] + bitmap data
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image
import struct

# Pre-computed 4-bit nibble to 8-bit grayscale lookup for fonts
# 0=outline(2, distinguishes from background 0), 1=shadow(64), 2-15=brightness(val*17)
_NIBBLE_TO_GRAY_FONT = [2, 64] + [v * 17 for v in range(2, 16)]


class BitmapFont:
    """Represents a bitmap font"""

    def __init__(self, fnt_path: Path):
        self.path = fnt_path
        self.name = ""
        self.char_height = 16  # Standard height
        self.glyphs: Dict[str, Image.Image] = {}
        self.char_info: Dict[str, Dict[str, int]] = {}
        self._load()

    def _load(self) -> None:
        """Loads the .fnt file"""
        with open(self.path, "rb") as f:
            data = f.read()

        offset = 0

        # Read header
        _version = struct.unpack("<H", data[offset : offset + 2])[0]  # noqa: F841
        offset += 2

        font_name_len = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1

        self.name = data[offset : offset + font_name_len].decode(
            "ascii", errors="ignore"
        )
        offset += font_name_len

        cnt_font_info = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2

        # Read character info
        for i in range(cnt_font_info):
            ascii_char = struct.unpack("<B", data[offset : offset + 1])[0]
            offset += 1
            width = struct.unpack("<H", data[offset : offset + 2])[0]
            offset += 2
            kerning = struct.unpack("<H", data[offset : offset + 2])[0]
            offset += 2

            char = chr(ascii_char)
            self.char_info[char] = {"width": width, "kerning": kerning}

        # Read bitmap data (4 bits per pixel, 2 pixels per byte)
        bitmap_data = data[offset:]
        self._parse_bitmap(bitmap_data)

    def _parse_bitmap(self, bitmap_data: bytes) -> None:
        """Parse bitmap format with dotmap header"""
        if len(bitmap_data) < 8:
            return

        offset = 0

        # Read dotmap header
        dots_width = struct.unpack("<H", bitmap_data[offset : offset + 2])[0]
        offset += 2
        dots_height = struct.unpack("<H", bitmap_data[offset : offset + 2])[0]
        offset += 2
        dots_bpp = struct.unpack("<H", bitmap_data[offset : offset + 2])[
            0
        ]  # noqa: F841
        offset += 2
        has_mask = struct.unpack("<H", bitmap_data[offset : offset + 2])[0]
        offset += 2

        # Update font height from dotmap
        self.char_height = dots_height

        # Calculate bitmap dimensions
        width_bytes_dots = (dots_width // 2) + (1 if dots_width % 2 else 0)
        dots_size = width_bytes_dots * dots_height

        # Read dots data
        dots_data = bitmap_data[offset : offset + dots_size]
        offset += dots_size

        # Read mask data if present
        mask_data = None
        width_bytes_mask = 0
        if has_mask:
            width_bytes_mask = (dots_width // 8) + (1 if dots_width % 8 else 0)
            mask_size = width_bytes_mask * dots_height
            mask_data = bitmap_data[offset : offset + mask_size]
            offset += mask_size

        # Create bitmap image using LUT (fast byte-level parsing)
        # Font uses: 0=outline(2), 1=shadow(64), 2-15=brightness(val*17)
        pixel_buf = bytearray(dots_width * dots_height)
        for y in range(dots_height):
            row_start = y * width_bytes_dots
            out_row = y * dots_width
            for x in range(0, dots_width - 1, 2):
                byte_val = dots_data[row_start + (x >> 1)]
                lo = byte_val & 0x0F
                hi = (byte_val >> 4) & 0x0F
                pixel_buf[out_row + x] = _NIBBLE_TO_GRAY_FONT[lo]
                pixel_buf[out_row + x + 1] = _NIBBLE_TO_GRAY_FONT[hi]
            if dots_width % 2:
                byte_val = dots_data[row_start + ((dots_width - 1) >> 1)]
                pixel_buf[out_row + dots_width - 1] = _NIBBLE_TO_GRAY_FONT[byte_val & 0x0F]

        bitmap_img = Image.frombytes("L", (dots_width, dots_height), bytes(pixel_buf))

        # Store mask data on bitmap for later use
        if mask_data:
            bitmap_any: Any = bitmap_img
            bitmap_any.mask_data = mask_data
            bitmap_any.mask_width_bytes = width_bytes_mask

        # Extract individual character glyphs
        x_offset = 0
        for char, info in self.char_info.items():
            width = info["width"]
            if x_offset + width <= dots_width:
                # Extract character glyph
                glyph = bitmap_img.crop((x_offset, 0, x_offset + width, dots_height))

                # Copy mask data for this glyph
                if mask_data:
                    glyph_any: Any = glyph
                    glyph_any.mask_data = mask_data
                    glyph_any.mask_width_bytes = width_bytes_mask
                    glyph_any.mask_x_offset = x_offset

                self.glyphs[char] = glyph
                x_offset += width

        # Add space character with same properties as colon for consistent blinking
        if ":" in self.char_info and " " not in self.char_info:
            self.char_info[" "] = self.char_info[":"].copy()
            self.glyphs[" "] = Image.new("L", self.glyphs[":"].size, 0)

    def render_text(self, text: str, width: int = 128, height: int = 32) -> Image.Image:
        """Renders text with this font (optimized)"""
        img = Image.new("L", (width, height))  # Grayscale for 4-bit support

        # Create mask for the rendered text
        mask_width_bytes = (width // 8) + (1 if width % 8 else 0)
        mask_array = bytearray(height * mask_width_bytes)

        # Calculate total text width (with kerning) and validate chars in one pass
        text_width = 0
        valid_chars: List[Optional[str]] = []
        for i, char in enumerate(text):
            if char in self.char_info:
                valid_chars.append(char)
                text_width += self.char_info[char]["width"]
                if i < len(text) - 1:  # Not the last character
                    text_width -= self.char_info[char]["kerning"]
            else:
                valid_chars.append(None)
                text_width += 8  # Space for missing characters

        # Center the text
        x_pos = (width - text_width) // 2
        y_pos = (height - self.char_height) // 2

        # Render characters
        has_mask = False
        for idx, vc in enumerate(valid_chars):
            if vc and vc in self.glyphs:
                glyph = self.glyphs[vc]
                img.paste(glyph, (x_pos, y_pos))

                # Copy mask for this glyph (byte-level iteration)
                if hasattr(glyph, "mask_data") and getattr(glyph, "mask_data", None):
                    glyph_any: Any = glyph
                    glyph_x_offset = getattr(glyph, "mask_x_offset", 0)
                    glyph_w = glyph.size[0]
                    glyph_h = glyph.size[1]
                    src_mask = glyph_any.mask_data
                    src_wb = glyph_any.mask_width_bytes
                    for gy in range(glyph_h):
                        dest_y = y_pos + gy
                        if dest_y < 0 or dest_y >= height:
                            continue
                        src_row = gy * src_wb
                        dest_row = dest_y * mask_width_bytes
                        for gx in range(glyph_w):
                            src_x = glyph_x_offset + gx
                            src_byte_idx = (src_x >> 3) + src_row
                            if src_byte_idx < len(src_mask) and (src_mask[src_byte_idx] >> (src_x & 7)) & 1:
                                dest_x = x_pos + gx
                                if 0 <= dest_x < width:
                                    mask_array[(dest_x >> 3) + dest_row] |= 1 << (dest_x & 7)
                                    has_mask = True

                x_pos += self.char_info[vc]["width"]
                if (
                    idx < len(valid_chars) - 1
                ):  # Apply kerning except for last character
                    x_pos -= self.char_info[vc]["kerning"]
            else:
                # Space for missing characters
                x_pos += 8

        # Store mask on image
        if has_mask:
            img_any: Any = img
            img_any.mask_data = bytes(mask_array)
            img_any.mask_width_bytes = mask_width_bytes

        return img

    def get_text_width(self, text: str) -> int:
        """Calculates text width with kerning"""
        if not text:
            return 0

        width = 0
        for i, char in enumerate(text):
            if char in self.char_info:
                width += self.char_info[char]["width"]
                if i < len(text) - 1:  # Apply kerning except for last character
                    width -= self.char_info[char]["kerning"]
            else:
                width += 8  # Default width for missing chars

        return width


def load_font(fnt_path: Path) -> BitmapFont:
    """Loads a font from a .fnt file"""
    return BitmapFont(fnt_path)
