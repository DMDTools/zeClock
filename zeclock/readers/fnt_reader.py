"""
Lecteur de fonts bitmap (.fnt)
Format: Version + FontNameLen + FontName + CntFontInfo + FontCharInfo[] + bitmap data
"""
from pathlib import Path
from typing import Dict, Tuple
from PIL import Image
import struct


class BitmapFont:
    """Représente une police bitmap"""
    
    def __init__(self, fnt_path: Path):
        self.path = fnt_path
        self.name = ""
        self.char_height = 16  # Standard height
        self.glyphs: Dict[str, Image.Image] = {}
        self.char_info = {}
        self._load()
    
    def _load(self):
        """Charge le fichier .fnt"""
        with open(self.path, 'rb') as f:
            data = f.read()
        
        offset = 0
        
        # Read header
        version = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        font_name_len = struct.unpack('<B', data[offset:offset+1])[0]
        offset += 1
        
        self.name = data[offset:offset+font_name_len].decode('ascii', errors='ignore')
        offset += font_name_len
        
        cnt_font_info = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        # Read character info
        for i in range(cnt_font_info):
            ascii_char = struct.unpack('<B', data[offset:offset+1])[0]
            offset += 1
            width = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            kerning = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            char = chr(ascii_char)
            self.char_info[char] = {'width': width, 'kerning': kerning}
        
        # Read bitmap data (4 bits per pixel, 2 pixels per byte)
        bitmap_data = data[offset:]
        self._parse_bitmap(bitmap_data)
    
    def _parse_bitmap(self, bitmap_data: bytes):
        """Parse bitmap format with dotmap header"""
        if len(bitmap_data) < 8:
            return
            
        offset = 0
        
        # Read dotmap header
        dots_width = struct.unpack('<H', bitmap_data[offset:offset+2])[0]
        offset += 2
        dots_height = struct.unpack('<H', bitmap_data[offset:offset+2])[0]
        offset += 2
        dots_bpp = struct.unpack('<H', bitmap_data[offset:offset+2])[0]
        offset += 2
        has_mask = struct.unpack('<H', bitmap_data[offset:offset+2])[0]
        offset += 2
        
        # Update font height from dotmap
        self.char_height = dots_height
        
        # Calculate bitmap dimensions
        width_bytes_dots = (dots_width // 2) + (1 if dots_width % 2 else 0)
        dots_size = width_bytes_dots * dots_height
        
        # Read dots data
        dots_data = bitmap_data[offset:offset + dots_size]
        offset += dots_size
        
        # Skip mask data if present
        if has_mask:
            width_bytes_mask = (dots_width // 8) + (1 if dots_width % 8 else 0)
            mask_size = width_bytes_mask * dots_height
            offset += mask_size
        
        # Create bitmap image (preserve 4-bit grayscale)
        bitmap_img = Image.new('L', (dots_width, dots_height))  # 'L' for grayscale
        pixels = bitmap_img.load()
        
        # Parse bitmap data (4 bits per pixel, 2 pixels per byte)
        for y in range(dots_height):
            for x in range(dots_width):
                byte_idx = (x // 2) + (y * width_bytes_dots)
                if byte_idx < len(dots_data):
                    byte_val = dots_data[byte_idx]
                    if x % 2 == 0:
                        # Even column: lower 4 bits
                        pixel_val = byte_val & 0x0F
                    else:
                        # Odd column: upper 4 bits
                        pixel_val = (byte_val >> 4) & 0x0F
                    
                    # Map 4-bit values with better shadow visibility
                    if pixel_val == 0:
                        pixels[x, y] = 0      # Black
                    elif pixel_val == 1:
                        pixels[x, y] = 64     # Visible shadow
                    else:
                        pixels[x, y] = pixel_val * 17  # Linear for other values
        
        # Extract individual character glyphs
        x_offset = 0
        for char, info in self.char_info.items():
            width = info['width']
            if x_offset + width <= dots_width:
                # Extract character glyph
                glyph = bitmap_img.crop((x_offset, 0, x_offset + width, dots_height))
                self.glyphs[char] = glyph
                x_offset += width
        
        # Add space character with same properties as colon for consistent blinking
        if ':' in self.char_info and ' ' not in self.char_info:
            self.char_info[' '] = self.char_info[':'].copy()
            self.glyphs[' '] = Image.new('L', self.glyphs[':'].size, 0)
    
    def render_text(self, text: str, width: int = 128, height: int = 32) -> Image.Image:
        """Rend du texte avec cette police (optimized)"""
        img = Image.new('L', (width, height))  # Grayscale for 4-bit support
        
        # Calculate total text width (with kerning) and validate chars in one pass
        text_width = 0
        valid_chars = []
        for i, char in enumerate(text):
            if char in self.char_info:
                valid_chars.append(char)
                text_width += self.char_info[char]['width']
                if i < len(text) - 1:  # Not the last character
                    text_width -= self.char_info[char]['kerning']
            else:
                valid_chars.append(None)
                text_width += 8  # Space for missing characters
        
        # Center the text
        x_pos = (width - text_width) // 2
        y_pos = (height - self.char_height) // 2
        
        # Render characters
        for i, char in enumerate(valid_chars):
            if char and char in self.glyphs:
                glyph = self.glyphs[char]
                img.paste(glyph, (x_pos, y_pos))
                x_pos += self.char_info[char]['width']
                if i < len(valid_chars) - 1:  # Apply kerning except for last character
                    x_pos -= self.char_info[char]['kerning']
            else:
                # Space for missing characters
                x_pos += 8
        
        return img
    
    def get_text_width(self, text: str) -> int:
        """Calcule la largeur d'un texte avec kerning"""
        if not text:
            return 0
        
        width = 0
        for i, char in enumerate(text):
            if char in self.char_info:
                width += self.char_info[char]['width']
                if i < len(text) - 1:  # Apply kerning except for last character
                    width -= self.char_info[char]['kerning']
            else:
                width += 8  # Default width for missing chars
        
        return width


def load_font(fnt_path: Path) -> BitmapFont:
    """Charge une police depuis un fichier .fnt"""
    return BitmapFont(fnt_path)
