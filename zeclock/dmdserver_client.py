"""
Python client to communicate with dmdserver (libdmdutil)
Protocol: StreamHeader + RGB565 data (big-endian)
"""

import socket
from typing import Optional, Tuple
from PIL import Image

from .overlay import colorize_grayscale

# Pre-computed RGB565 lookup tables (computed once at import time)
# Avoids per-pixel bit shifting in the hot loop
_RGB565_R = [((r >> 3) << 11) for r in range(256)]
_RGB565_G = [((g >> 2) << 5) for g in range(256)]
_RGB565_B = [(b >> 3) for b in range(256)]


class DMDServerClient:
    """Client to send RGB565 frames to dmdserver"""

    def __init__(self, host: str = "localhost", port: int = 6789):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
        # Frame cache: avoid re-encoding identical frames
        self._last_frame_id: Optional[int] = None
        self._last_msg: Optional[bytes] = None

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

    def disconnect(self) -> None:
        """Closes the connection"""
        if self.sock:
            self.sock.close()
            self.connected = False

    def send_frame(
        self,
        image: Image.Image,
        buffered: bool = True,
        color: Tuple[int, int, int] = (255, 128, 0),
    ) -> bool:
        """Sends an RGB565 frame to DMDServer.

        Uses frame identity caching: if the same Image object is sent again,
        skips colorization and RGB565 conversion entirely.
        """
        if not self.connected:
            if not self.connect():
                return False

        # Check if this is the exact same frame object (identity check)
        frame_id = id(image)
        if frame_id == self._last_frame_id and self._last_msg is not None:
            msg = self._last_msg
        else:
            if image.mode != "RGB":
                # Convert grayscale to RGB using color palette
                image = self._grayscale_to_rgb(image, color)

            width, height = image.size

            # Convert to RGB565
            rgb565_data = self._rgb_to_rgb565(image)

            # Create header (big-endian like dmd-simulator)
            header = bytearray("DMDStream", "utf-8") + b"\x00"
            header += (1).to_bytes(1, "big")  # version
            header += (3).to_bytes(4, "big")  # mode RGB565
            header += width.to_bytes(2, "big")  # width
            header += height.to_bytes(2, "big")  # height
            header += (1 if buffered else 0).to_bytes(1, "big")  # buffered
            header += (1).to_bytes(1, "big")  # disconnectOthers
            header += len(rgb565_data).to_bytes(4, "big")  # length

            msg = bytes(header + rgb565_data)
            self._last_frame_id = frame_id
            self._last_msg = msg

        try:
            assert self.sock is not None
            self.sock.sendall(msg)
            return True
        except Exception as e:
            print(f"❌ Error sending frame: {e}")
            self.connected = False
            return False

    def _grayscale_to_rgb(
        self, image: Image.Image, color: Tuple[int, int, int]
    ) -> Image.Image:
        """Convert grayscale DMD image to RGB using color palette"""
        return colorize_grayscale(image, color)

    def _rgb_to_rgb565(self, image: Image.Image) -> bytes:
        """Convert RGB image to RGB565 format (big-endian).

        Optimized: uses pre-computed LUTs to avoid per-pixel bit shifting,
        and struct.pack in a single call instead of per-pixel pack_into.
        """
        import struct

        rgb_data = image.tobytes()
        pixel_count = len(rgb_data) // 3
        values = [
            _RGB565_R[rgb_data[i]]
            | _RGB565_G[rgb_data[i + 1]]
            | _RGB565_B[rgb_data[i + 2]]
            for i in range(0, len(rgb_data), 3)
        ]
        return struct.pack(f">{pixel_count}H", *values)

    def __enter__(self) -> "DMDServerClient":
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.disconnect()
