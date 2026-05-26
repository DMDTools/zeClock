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
        import numpy as np
        
        gray_array = np.asarray(image)
        rgb_array = np.zeros((image.height, image.width, 3), dtype=np.uint8)
        
        # Apply color with brightness from grayscale value
        for i in range(3):
            rgb_array[:, :, i] = (gray_array * color[i]) // 255
        
        return Image.fromarray(rgb_array, 'RGB')
    
    def _rgb_to_rgb565(self, image: Image.Image) -> bytearray:
        """Convert RGB image to RGB565 format (big-endian) - optimized"""
        import numpy as np
        
        # Convert to numpy array for vectorized operations
        rgb_array = np.array(image)
        
        # Vectorized RGB565 conversion
        r = (rgb_array[:, :, 0] >> 3).astype(np.uint16)
        g = (rgb_array[:, :, 1] >> 2).astype(np.uint16) 
        b = (rgb_array[:, :, 2] >> 3).astype(np.uint16)
        
        rgb565 = (r << 11) | (g << 5) | b
        
        # Convert to big-endian bytes
        return rgb565.astype('>u2').tobytes()
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
