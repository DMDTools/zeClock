"""
Client Python pour communiquer avec dmdserver (libdmdutil)
Protocole : StreamHeader + RGB565 data (big-endian)
"""
import socket
from typing import Optional, Tuple
from PIL import Image


class DMDServerClient:
    """Client pour envoyer des frames RGB565 à dmdserver"""
    
    def __init__(self, host: str = "localhost", port: int = 6789):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Établit la connexion avec dmdserver"""
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
        """Ferme la connexion"""
        if self.sock:
            self.sock.close()
            self.connected = False
    
    def send_frame(self, image: Image.Image, buffered: bool = True) -> bool:
        """Envoie une frame RGB565 au DMDServer"""
        if not self.connected:
            if not self.connect():
                return False
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
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
