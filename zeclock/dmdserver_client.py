"""
Python client to communicate with dmdserver (libdmdutil)
Protocol: StreamHeader + RGB565 data (big-endian)
"""
import socket
from typing import Optional, Tuple
from PIL import Image


class DMDServerClient:
    """Client to send RGB565 frames to dmdserver"""
    
    def __init__(self, host: str = "localhost", port: int = 6789):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Establishes connection with dmdserver"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"❌ Failed to connect to dmdserver: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Closes the connection"""
        if self.sock:
            self.sock.close()
            self.connected = False
    
    def send_frame(self, image: Image.Image, buffered: bool = True, color: Tuple[int, int, int] = (255, 128, 0)) -> bool:
        """Sends an RGB565 frame to DMDServer"""
        if not self.connected:
            if not self.connect():
                return False
        
        if image.mode != 'RGB':
            # Convert grayscale to RGB using color palette
            image = self._grayscale_to_rgb(image, color)
        
        width, height = image.size
        
        # Convert to RGB565
        rgb565_data = self._rgb_to_rgb565(image)
        
        # Create header (big-endian like dmd-simulator)
        header = bytearray("DMDStream", "utf-8") + b'\x00'
        header += (1).to_bytes(1, 'big')                    # version
        header += (3).to_bytes(4, 'big')                    # mode RGB565
        header += width.to_bytes(2, 'big')                  # width
        header += height.to_bytes(2, 'big')                 # height
        header += (1 if buffered else 0).to_bytes(1, 'big') # buffered
        header += (1).to_bytes(1, 'big')                    # disconnectOthers
        header += len(rgb565_data).to_bytes(4, 'big')       # length
        
        try:
            msg = header + rgb565_data
            self.sock.sendall(msg)
            return True
        except Exception as e:
            print(f"❌ Error sending frame: {e}")
            self.connected = False
            return False
    
    def _grayscale_to_rgb(self, image: Image.Image, color: Tuple[int, int, int]) -> Image.Image:
        """Convert grayscale DMD image to RGB using color palette"""
        width, height = image.size
        gray_data = image.tobytes()
        rgb_data = bytearray(width * height * 3)
        
        for i, pixel in enumerate(gray_data):
            if pixel > 0:
                offset = i * 3
                rgb_data[offset] = (color[0] * pixel) // 255
                rgb_data[offset + 1] = (color[1] * pixel) // 255
                rgb_data[offset + 2] = (color[2] * pixel) // 255
        
        return Image.frombytes('RGB', (width, height), bytes(rgb_data))
    
    def _rgb_to_rgb565(self, image: Image.Image) -> bytearray:
        """Convert RGB image to RGB565 format (big-endian)"""
        import struct
        
        rgb_data = image.tobytes()
        pixel_count = len(rgb_data) // 3
        result = bytearray(pixel_count * 2)
        
        for i in range(pixel_count):
            offset = i * 3
            r = rgb_data[offset] >> 3
            g = rgb_data[offset + 1] >> 2
            b = rgb_data[offset + 2] >> 3
            rgb565 = (r << 11) | (g << 5) | b
            struct.pack_into('>H', result, i * 2, rgb565)
        
        return result
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
