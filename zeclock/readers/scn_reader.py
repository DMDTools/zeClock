"""
Lecteur d'animations DotClk (.scn)
Format: Scene header + dotmap frames (4-bit per pixel)
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
        self.frame_delay_ms = 40  # Default 25 FPS
        self._load()
    
    def _load(self):
        """Charge le fichier .scn selon le format DotClk"""
        with open(self.path, 'rb') as f:
            data = f.read()
        
        offset = 0
        
        # Read scene header
        version = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        cnt_item_dotmap = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        cnt_item_storyboard = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        # Read storyboard data to get timing information
        if cnt_item_storyboard > 0:
            # Read first storyboard item for timing
            first_frame_delay = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            first_frame_layer = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            first_blank = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            frame_delay = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            frame_layer = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            # Use the frame delay from storyboard (in milliseconds)
            if frame_delay > 0:
                self.frame_delay_ms = frame_delay
            
            # Skip rest of first storyboard item
            offset += 2 + 2 + 2 + 1 + 1 + 1 + 17  # lastFrameDelay, lastFrameLayer, lastBlank, clockStyle, customX, customY, space[17]
            
            # Skip remaining storyboard items
            remaining_storyboards = cnt_item_storyboard - 1
            offset += remaining_storyboards * 36
        else:
            # No storyboard, use default timing
            pass
        
        self.frame_count = cnt_item_dotmap
        
        # Read each frame as a dotmap structure
        for i in range(cnt_item_dotmap):
            if offset + 8 <= len(data):  # Need at least header
                frame = self._parse_dotmap_frame(data, offset)
                if frame:
                    self.frames.append(frame[0])
                    offset = frame[1]  # Update offset
    
    def _parse_dotmap_frame(self, data: bytes, offset: int) -> tuple:
        """Parse a single dotmap frame from data"""
        if offset + 8 > len(data):
            return None
        
        # Read dotmap header
        dots_width = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        dots_height = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        dots_bpp = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        has_mask = struct.unpack('<H', data[offset:offset+2])[0]
        offset += 2
        
        # Calculate data sizes
        width_bytes_dots = (dots_width // 2) + (1 if dots_width % 2 else 0)
        dots_size = width_bytes_dots * dots_height
        
        width_bytes_mask = (dots_width // 8) + (1 if dots_width % 8 else 0)
        mask_size = width_bytes_mask * dots_height if has_mask else 0
        
        # Check if we have enough data
        if offset + dots_size + mask_size > len(data):
            return None
        
        # Read dots data
        dots_data = data[offset:offset + dots_size]
        offset += dots_size
        
        # Skip mask data if present
        if has_mask:
            offset += mask_size
        
        # Create image from dots data
        img = Image.new('L', (dots_width, dots_height))
        pixels = img.load()
        
        # Parse 4-bit data (2 pixels per byte)
        for y in range(dots_height):
            for x in range(dots_width):
                byte_idx = (x // 2) + (y * width_bytes_dots)
                if byte_idx < len(dots_data):
                    byte_val = dots_data[byte_idx]
                    if x % 2 == 0:
                        # Even column: lower 4 bits (corrected from conversation summary)
                        pixel_val = byte_val & 0x0F
                    else:
                        # Odd column: upper 4 bits (corrected from conversation summary)
                        pixel_val = (byte_val >> 4) & 0x0F
                    
                    # Map 4-bit values with better shadow visibility
                    if pixel_val == 0:
                        pixels[x, y] = 0      # Black
                    elif pixel_val == 1:
                        pixels[x, y] = 64     # Visible shadow
                    else:
                        pixels[x, y] = pixel_val * 17  # Linear for other values
        
        return (img, offset)
    
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
