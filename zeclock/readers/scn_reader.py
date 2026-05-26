"""
Animation loader (.scn)
Format: Scene header + dotmap frames (4-bit per pixel)
"""
from pathlib import Path
from typing import List, Iterator
from PIL import Image
import struct


class Scene:
    """Represents an animation"""
    
    def __init__(self, scn_path: Path, width: int = 128, height: int = 32):
        self.path = scn_path
        self.width = width
        self.height = height
        self.frames: List[Image.Image] = []
        self.frame_count = 0
        
        # Storyboard data
        self.first_frame_delay = 0
        self.first_frame_layer = 0
        self.first_blank = 0
        self.frame_delay_ms = 40  # Default 25 FPS
        self.frame_layer = 0
        self.last_frame_delay = 0
        self.last_frame_layer = 0
        self.last_blank = 0
        self.clock_style = 0
        self.custom_x = 0
        self.custom_y = 0
        
        self._load()
    
    def _load(self):
        """Loads the .scn file"""
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
            # Read first storyboard item for timing (all uint16_t except clock fields)
            self.first_frame_delay = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            self.first_frame_layer = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            self.first_blank = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            self.frame_delay_ms = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            self.frame_layer = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            self.last_frame_delay = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            self.last_frame_layer = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            self.last_blank = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            
            # Clock fields are bytes
            self.clock_style = struct.unpack('<B', data[offset:offset+1])[0]
            offset += 1
            self.custom_x = struct.unpack('<B', data[offset:offset+1])[0]
            offset += 1
            self.custom_y = struct.unpack('<B', data[offset:offset+1])[0]
            offset += 1
            
            # Skip the 17 bytes for future features
            offset += 17
            
            # Skip remaining storyboard items (each is 36 bytes total)
            remaining_storyboards = cnt_item_storyboard - 1
            offset += remaining_storyboards * 36
        else:
            # No storyboard, use default timing
            pass
        
        self.frame_count = cnt_item_dotmap
        
        # Frame state management
        self.do_first = 1 if self.first_frame_delay > 0 else 0  # TODO=1, NA=0
        self.do_last = 1 if self.last_frame_delay > 0 else 0
        
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
        
        # Read mask data if present
        mask_data = None
        if has_mask:
            mask_data = data[offset:offset + mask_size]
            offset += mask_size
        
        # Create image from dots data
        img = Image.new('L', (dots_width, dots_height))
        pixels = img.load()
        
        # Parse 4-bit data (2 pixels per byte) - preserve original values
        for y in range(dots_height):
            for x in range(dots_width):
                byte_idx = (x // 2) + (y * width_bytes_dots)
                if byte_idx < len(dots_data):
                    byte_val = dots_data[byte_idx]
                    if x % 2 == 0:
                        pixel_val = byte_val & 0x0F
                    else:
                        pixel_val = (byte_val >> 4) & 0x0F
                    
                    # Map 4-bit values with better shadow visibility
                    if pixel_val == 0:
                        pixels[x, y] = 0
                    elif pixel_val == 1:
                        pixels[x, y] = 64
                    else:
                        pixels[x, y] = pixel_val * 17
        
        # Store mask data for overlay use
        if mask_data:
            img.mask_data = mask_data
            img.mask_width_bytes = width_bytes_mask
        
        return (img, offset)
    
    def __iter__(self) -> Iterator[Image.Image]:
        """Itère sur les frames"""
        return iter(self.frames)
    
    def __len__(self) -> int:
        return self.frame_count
    
    def get_frame(self, index: int) -> Image.Image:
        """Récupère une frame spécifique"""
        return self.frames[index % self.frame_count]

def load_scene(scn_path: Path, width: int = 128, height: int = 32) -> Scene:
    """Loads an animation from a .scn file"""
    return Scene(scn_path, width, height)
