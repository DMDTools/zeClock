"""
Client Python pour communiquer avec dmdserver (libdmdutil)
Protocole : StreamHeader + RGB24 data
"""
import socket
import struct
from typing import Optional, Tuple
from PIL import Image


class DMDServerClient:
    """Client pour envoyer des frames RGB24 à dmdserver"""
    
    # Modes supportés
    MODE_DATA = 1    # Mode natif libdmdutil (complexe)
    MODE_RGB24 = 2   # RGB888 - 3 bytes par pixel (R, G, B)
    MODE_RGB16 = 3   # RGB565 - 2 bytes par pixel
    
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
            print(f"✅ Connected to dmdserver at {self.host}:{self.port}")
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
            print("Disconnected from dmdserver")
    
    def send_rgb24_frame(
        self,
        image: Image.Image,
        buffered: bool = False,
        disconnect_others: bool = False
    ) -> bool:
        """
        Envoie une frame RGB24 au DMDServer
        
        Args:
            image: Image PIL (sera convertie en RGB si nécessaire)
            buffered: Si True, la frame est bufferisée (affichée après déconnexion)
            disconnect_others: Si True, déconnecte les autres clients
        
        Returns:
            True si succès
        """
        if not self.connected:
            if not self.connect():
                return False
        
        # Convertir en RGB si nécessaire
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        width, height = image.size
        
        # Préparer le header (structure C)
        header = self._create_stream_header(
            mode=self.MODE_RGB24,
            width=width,
            height=height,
            buffered=buffered,
            disconnect_others=disconnect_others
        )
        
        # Préparer les données RGB24
        rgb_data = image.tobytes()  # Format RGB24 natif PIL
        
        try:
            # Envoyer header puis data
            self.sock.sendall(header)
            self.sock.sendall(rgb_data)
            return True
        except Exception as e:
            print(f"❌ Error sending frame: {e}")
            self.connected = False
            return False
    
    def send_monochrome_frame(
        self,
        image: Image.Image,
        color: Tuple[int, int, int] = (255, 128, 0),  # Orange DMD classique
        buffered: bool = False
    ) -> bool:
        """
        Envoie une frame monochrome (1-bit) colorisée
        
        Args:
            image: Image PIL en mode '1' (bitmap) ou 'L' (grayscale)
            color: Couleur RGB à appliquer aux pixels allumés
            buffered: Si True, la frame est bufferisée
        
        Returns:
            True si succès
        """
        # Convertir en RGB colorisé
        if image.mode == '1':
            # Image bitmap : pixels 0 ou 255
            rgb_image = Image.new('RGB', image.size)
            px_src = image.load()
            px_dst = rgb_image.load()
            
            for y in range(image.height):
                for x in range(image.width):
                    if px_src[x, y]:
                        px_dst[x, y] = color
                    else:
                        px_dst[x, y] = (0, 0, 0)
        
        elif image.mode == 'L':
            # Grayscale : appliquer couleur proportionnellement
            rgb_image = Image.new('RGB', image.size)
            px_src = image.load()
            px_dst = rgb_image.load()
            
            for y in range(image.height):
                for x in range(image.width):
                    intensity = px_src[x, y] / 255.0
                    px_dst[x, y] = (
                        int(color[0] * intensity),
                        int(color[1] * intensity),
                        int(color[2] * intensity)
                    )
        else:
            # Déjà en couleur
            rgb_image = image.convert('RGB')
        
        return self.send_rgb24_frame(rgb_image, buffered=buffered)
    
    def _create_stream_header(
        self,
        mode: int,
        width: int,
        height: int,
        buffered: bool = False,
        disconnect_others: bool = False
    ) -> bytes:
        """
        Crée le StreamHeader selon la spec libdmdutil
        
        Structure (total 23 bytes):
        - char[10] header = "DMDStream\0"
        - uint8_t version = 1
        - uint32_t mode (little-endian)
        - uint16_t width (little-endian)
        - uint16_t height (little-endian)
        - uint8_t buffered
        - uint8_t disconnectOthers
        - uint32_t length (little-endian)
        """
        # Calcul de la taille des données
        if mode == self.MODE_RGB24:
            data_length = width * height * 3
        elif mode == self.MODE_RGB16:
            data_length = width * height * 2
        else:
            data_length = 0
        
        # Construction du header
        header = b"DMDStream\x00"  # 10 bytes (string + null terminator)
        header += struct.pack('<B', 1)  # version: uint8_t
        header += struct.pack('<I', mode)  # mode: uint32_t (little-endian)
        header += struct.pack('<H', width)  # width: uint16_t
        header += struct.pack('<H', height)  # height: uint16_t
        header += struct.pack('<B', 1 if buffered else 0)  # buffered: uint8_t
        header += struct.pack('<B', 1 if disconnect_others else 0)  # disconnect: uint8_t
        header += struct.pack('<I', data_length)  # length: uint32_t
        
        return header
    
    def __enter__(self):
        """Support context manager"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support context manager"""
        self.disconnect()
