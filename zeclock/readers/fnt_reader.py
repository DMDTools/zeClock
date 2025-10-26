"""
Lecteur de fonts bitmap DotClk (.fnt)
Format: en-têtes + bitmap des glyphes
"""
from pathlib import Path
from typing import Dict, Tuple
from PIL import Image
import struct


class DotClkFont:
    """Représente une police bitmap DotClk"""
    
    def __init__(self, fnt_path: Path):
        self.path = fnt_path
        self.name = ""
        self.char_width = 0
        self.char_height = 0
        self.spacing = 0
        self.glyphs: Dict[str, Image.Image] = {}
        self._load()
    
    def _load(self):
        """Charge le fichier .fnt"""
        with open(self.path, 'rb') as f:
            data = f.read()
        
        # Format DotClk .fnt (dérivé du format Windows FNT)
        # Structure simplifiée basée sur l'analyse
        if len(data) < 88:
            raise ValueError(f"Invalid FNT file: {self.path}")
        
        # Header (88 bytes minimum)
        header = struct.unpack('<H', data[0:2])[0]  # Face ID
        size = struct.unpack('<H', data[2:4])[0]     # Point size
        
        # Nom de la fonte (32 bytes, null-terminated)
        name_bytes = data[4:36]
        self.name = name_bytes.split(b'\x00')[0].decode('ascii', errors='ignore')
        
        # Caractéristiques
        first_char = struct.unpack('<H', data[36:38])[0]
        last_char = struct.unpack('<H', data[38:40])[0]
        self.char_height = struct.unpack('<H', data[82:84])[0]
        
        # Width (fixed ou variable)
        self.char_width = struct.unpack('<H', data[52:54])[0]
        self.spacing = 1  # Default spacing
        
        # Offset vers les données bitmap
        font_data_offset = struct.unpack('<I', data[76:80])[0]
        form_width_bytes = struct.unpack('<H', data[80:82])[0]
        
        # Charger les bitmaps de caractères
        self._load_glyphs(
            data[font_data_offset:],
            first_char,
            last_char,
            form_width_bytes
        )
    
    def _load_glyphs(self, bitmap_data: bytes, first: int, last: int, width_bytes: int):
        """Extrait les glyphes depuis les données bitmap"""
        chars_count = last - first + 1
        
        for i in range(chars_count):
            char_code = first + i
            char = chr(char_code)
            
            # Position dans le bitmap (simplifié)
            x_offset = i * self.char_width
            
            # Créer l'image du glyphe
            glyph = Image.new('1', (self.char_width, self.char_height))
            pixels = glyph.load()
            
            for y in range(self.char_height):
                for x in range(self.char_width):
                    # Calcul de l'offset dans les données
                    bit_index = (y * width_bytes * 8) + x_offset + x
                    byte_index = bit_index // 8
                    bit_pos = 7 - (bit_index % 8)
                    
                    if byte_index < len(bitmap_data):
                        bit = (bitmap_data[byte_index] >> bit_pos) & 1
                        pixels[x, y] = 255 if bit else 0
            
            self.glyphs[char] = glyph
    
    def render_text(self, text: str, width: int = 128, height: int = 32) -> Image.Image:
        """Rend du texte avec cette police"""
        img = Image.new('1', (width, height))
        
        x_pos = 0
        y_pos = (height - self.char_height) // 2
        
        for char in text:
            if char in self.glyphs:
                glyph = self.glyphs[char]
                img.paste(glyph, (x_pos, y_pos))
                x_pos += self.char_width + self.spacing
            else:
                x_pos += self.char_width  # Espace pour caractères manquants
        
        return img
    
    def get_text_width(self, text: str) -> int:
        """Calcule la largeur d'un texte"""
        return len(text) * (self.char_width + self.spacing)


def load_font(fnt_path: Path) -> DotClkFont:
    """Charge une police DotClk depuis un fichier .fnt"""
    return DotClkFont(fnt_path)
