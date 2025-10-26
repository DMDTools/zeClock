"""
Lecteur d'animations DotClk (.scn)
Format: frames binaires 1-bit compressées
"""
from pathlib import Path
from typing import List, Iterator
from PIL import Image
import struct


class DotClkScene:
    """Représente une animation DotClk"""
    
    def __init__(self, scn_path: Path, width: int = 128, height: int = 32):
        self.path = scn_path
        self.width = width
        self.height = height
        self.frames: List[Image.Image] = []
        self.frame_count = 0
        self.duration_ms = 40  # 25 FPS par défaut
        self._load()
    
    def _load(self):
        """Charge le fichier .scn"""
        with open(self.path, 'rb') as f:
            data = f.read()
        
        # Format SCN simplifié :
        # - Pas d'en-tête complexe dans les fichiers DotClk
        # - Juste une séquence de frames bitmap 1-bit
        # - Chaque frame = (width * height) / 8 bytes
        
        frame_size = (self.width * self.height) // 8
        self.frame_count = len(data) // frame_size
        
        # Lire chaque frame
        for i in range(self.frame_count):
            offset = i * frame_size
            frame_data = data[offset:offset + frame_size]
            frame = self._parse_frame(frame_data)
            self.frames.append(frame)
    
    def _parse_frame(self, frame_data: bytes) -> Image.Image:
        """Convertit les données binaires en image PIL"""
        img = Image.new('1', (self.width, self.height))
        pixels = img.load()
        
        for y in range(self.height):
            for x in range(self.width):
                # Calcul bit position
                bit_index = y * self.width + x
                byte_index = bit_index // 8
                bit_pos = 7 - (bit_index % 8)
                
                if byte_index < len(frame_data):
                    bit = (frame_data[byte_index] >> bit_pos) & 1
                    pixels[x, y] = 255 if bit else 0
        
        return img
    
    def __iter__(self) -> Iterator[Image.Image]:
        """Itère sur les frames"""
        return iter(self.frames)
    
    def __len__(self) -> int:
        return self.frame_count
    
    def get_frame(self, index: int) -> Image.Image:
        """Récupère une frame spécifique"""
        return self.frames[index % self.frame_count]


def load_scene(scn_path: Path, width: int = 128, height: int = 32) -> DotClkScene:
    """Charge une animation DotClk depuis un fichier .scn"""
    return DotClkScene(scn_path, width, height)
