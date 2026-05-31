#!/usr/bin/env python3
"""Generate pixel-perfect 2x HD versions of DotClk .fnt bitmap fonts.

Each pixel in the original font becomes a 2x2 block in the HD version,
preserving the retro DMD aesthetic at 256x64 resolution.

Usage:
    python scripts/generate_hd_fonts.py

Reads from: ~/.zeclock/resources/Fonts/*.fnt
Writes to:  ~/.zeclock/resources/Fonts/*_HD.fnt
"""

import struct
import sys
from pathlib import Path


def read_fnt(path: Path) -> dict:
    """Read a .fnt file and return its raw structure."""
    with open(path, "rb") as f:
        data = f.read()

    offset = 0

    # Header
    version = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2

    font_name_len = struct.unpack("<B", data[offset : offset + 1])[0]
    offset += 1

    font_name = data[offset : offset + font_name_len].decode("ascii", errors="ignore")
    offset += font_name_len

    cnt_font_info = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2

    # Character info
    char_info = []
    for _ in range(cnt_font_info):
        ascii_char = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1
        width = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        kerning = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        char_info.append({"ascii": ascii_char, "width": width, "kerning": kerning})

    # Bitmap data (dotmap)
    bitmap_offset = offset
    dots_width = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    dots_height = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    dots_bpp = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    has_mask = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2

    # Dots data (4-bit packed, 2 pixels per byte)
    width_bytes_dots = (dots_width // 2) + (1 if dots_width % 2 else 0)
    dots_size = width_bytes_dots * dots_height
    dots_data = data[offset : offset + dots_size]
    offset += dots_size

    # Mask data
    mask_data = None
    width_bytes_mask = 0
    if has_mask:
        width_bytes_mask = (dots_width // 8) + (1 if dots_width % 8 else 0)
        mask_size = width_bytes_mask * dots_height
        mask_data = data[offset : offset + mask_size]
        offset += mask_size

    return {
        "version": version,
        "font_name": font_name,
        "font_name_len": font_name_len,
        "char_info": char_info,
        "dots_width": dots_width,
        "dots_height": dots_height,
        "dots_bpp": dots_bpp,
        "has_mask": has_mask,
        "dots_data": dots_data,
        "mask_data": mask_data,
        "width_bytes_dots": width_bytes_dots,
        "width_bytes_mask": width_bytes_mask,
    }


def upscale_dots_2x(dots_data: bytes, src_w: int, src_h: int) -> tuple:
    """Upscale 4-bit packed dot data by 2x using EPX/Scale2x algorithm.

    EPX smooths diagonal edges and corners while preserving the pixel-art
    style. Unlike simple nearest-neighbor doubling, it produces cleaner
    diagonals without introducing new colors.

    Returns (new_data, new_width, new_height).
    """
    dst_w = src_w * 2
    dst_h = src_h * 2
    src_wb = (src_w // 2) + (1 if src_w % 2 else 0)
    dst_wb = (dst_w // 2) + (1 if dst_w % 2 else 0)

    # Unpack source to a 2D array of nibbles
    pixels = []
    for y in range(src_h):
        row = []
        for x in range(src_w):
            byte_idx = (x // 2) + y * src_wb
            if byte_idx < len(dots_data):
                byte_val = dots_data[byte_idx]
                if x % 2 == 0:
                    nibble = byte_val & 0x0F
                else:
                    nibble = (byte_val >> 4) & 0x0F
            else:
                nibble = 0
            row.append(nibble)
        pixels.append(row)

    # Apply EPX/Scale2x (modified: never create holes in filled areas)
    dst_pixels = [[0] * dst_w for _ in range(dst_h)]

    for y in range(src_h):
        for x in range(src_w):
            e = pixels[y][x]
            a = pixels[max(0, y - 1)][x]  # top
            b = pixels[y][min(src_w - 1, x + 1)]  # right
            c = pixels[y][max(0, x - 1)]  # left
            d = pixels[min(src_h - 1, y + 1)][x]  # bottom

            e0 = e1 = e2 = e3 = e

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

            dst_pixels[y * 2][x * 2] = e0
            dst_pixels[y * 2][x * 2 + 1] = e1
            dst_pixels[y * 2 + 1][x * 2] = e2
            dst_pixels[y * 2 + 1][x * 2 + 1] = e3

    # Pack back to 4-bit format
    dst_data = bytearray(dst_wb * dst_h)
    for y in range(dst_h):
        for x in range(dst_w):
            byte_idx = (x // 2) + y * dst_wb
            nibble = dst_pixels[y][x]
            if x % 2 == 0:
                dst_data[byte_idx] = (dst_data[byte_idx] & 0xF0) | (nibble & 0x0F)
            else:
                dst_data[byte_idx] = (dst_data[byte_idx] & 0x0F) | ((nibble & 0x0F) << 4)

    return bytes(dst_data), dst_w, dst_h


def upscale_mask_2x(mask_data: bytes, src_w: int, src_h: int) -> tuple:
    """Upscale 1-bit mask data by 2x.

    Returns (new_data, new_width_bytes).
    """
    dst_w = src_w * 2
    dst_h = src_h * 2
    src_wb = (src_w // 8) + (1 if src_w % 8 else 0)
    dst_wb = (dst_w // 8) + (1 if dst_w % 8 else 0)

    dst_data = bytearray(dst_wb * dst_h)

    for y in range(src_h):
        for x in range(src_w):
            src_byte = (x // 8) + y * src_wb
            src_bit = x % 8
            if src_byte < len(mask_data) and (mask_data[src_byte] >> src_bit) & 1:
                # Set 2x2 block in destination
                for dy in range(2):
                    for dx in range(2):
                        dest_x = x * 2 + dx
                        dest_y = y * 2 + dy
                        dest_byte = (dest_x // 8) + dest_y * dst_wb
                        dest_bit = dest_x % 8
                        dst_data[dest_byte] |= 1 << dest_bit

    return bytes(dst_data), dst_wb


def write_fnt(path: Path, fnt: dict) -> None:
    """Write a .fnt file from structure."""
    out = bytearray()

    # Header
    out += struct.pack("<H", fnt["version"])

    # Font name (append "_HD")
    hd_name = fnt["font_name"] + "_HD"
    out += struct.pack("<B", len(hd_name))
    out += hd_name.encode("ascii")

    # Character count
    out += struct.pack("<H", len(fnt["char_info"]))

    # Character info (widths doubled, kerning doubled)
    for ci in fnt["char_info"]:
        out += struct.pack("<B", ci["ascii"])
        out += struct.pack("<H", ci["width"] * 2)
        out += struct.pack("<H", ci["kerning"] * 2)

    # Dotmap header
    out += struct.pack("<H", fnt["new_dots_width"])
    out += struct.pack("<H", fnt["new_dots_height"])
    out += struct.pack("<H", fnt["dots_bpp"])
    out += struct.pack("<H", fnt["has_mask"])

    # Dots data
    out += fnt["new_dots_data"]

    # Mask data
    if fnt["has_mask"] and fnt["new_mask_data"]:
        out += fnt["new_mask_data"]

    with open(path, "wb") as f:
        f.write(bytes(out))


def generate_hd_font(src_path: Path, dst_path: Path) -> None:
    """Generate a 2x HD version of a .fnt file."""
    fnt = read_fnt(src_path)

    # Upscale dots
    new_dots, new_w, new_h = upscale_dots_2x(
        fnt["dots_data"], fnt["dots_width"], fnt["dots_height"]
    )
    fnt["new_dots_data"] = new_dots
    fnt["new_dots_width"] = new_w
    fnt["new_dots_height"] = new_h

    # Upscale mask if present
    if fnt["has_mask"] and fnt["mask_data"]:
        new_mask, _ = upscale_mask_2x(
            fnt["mask_data"], fnt["dots_width"], fnt["dots_height"]
        )
        fnt["new_mask_data"] = new_mask
    else:
        fnt["new_mask_data"] = None

    write_fnt(dst_path, fnt)
    print(f"  ✓ {src_path.name} ({fnt['dots_width']}x{fnt['dots_height']}) → {dst_path.name} ({new_w}x{new_h})")


def main() -> None:
    fonts_dir = Path.home() / ".zeclock" / "resources" / "Fonts"
    if not fonts_dir.exists():
        print(f"❌ Fonts directory not found: {fonts_dir}")
        sys.exit(1)

    print("🔤 Generating pixel-perfect HD fonts (2x upscale)...")
    print(f"   Source: {fonts_dir}")
    print()

    count = 0
    for fnt_file in sorted(fonts_dir.glob("*.fnt")):
        # Skip already-generated HD fonts
        if fnt_file.stem.endswith("_HD"):
            continue

        dst_path = fonts_dir / f"{fnt_file.stem}_HD.fnt"
        try:
            generate_hd_font(fnt_file, dst_path)
            count += 1
        except Exception as e:
            print(f"  ⚠️  Failed to process {fnt_file.name}: {e}")

    print(f"\n✅ Generated {count} HD font files")


if __name__ == "__main__":
    main()
