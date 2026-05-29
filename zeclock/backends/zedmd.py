"""ZeDMD backend using libzedmd via ctypes."""

import ctypes
import logging
import platform
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from ..overlay import colorize_grayscale
from .base import DMDBackend

logger = logging.getLogger(__name__)

# Library search path
LIB_DIR = Path.home() / ".zeclock" / "lib"


def _find_library() -> Path:
    """Find the libzedmd shared library on the current platform.

    Searches in ~/.zeclock/lib/ for the platform-appropriate filename.

    Returns:
        Path to the shared library file.

    Raises:
        ImportError: If the library cannot be found or the platform is unsupported.
    """
    system = platform.system()
    names = {
        "Linux": "libzedmd.so",
        "Darwin": "libzedmd.dylib",
        "Windows": "zedmd.dll",
    }
    lib_name = names.get(system)
    if not lib_name:
        raise ImportError(f"Unsupported platform: {system}")

    lib_path = LIB_DIR / lib_name
    if lib_path.exists():
        return lib_path

    raise ImportError(
        f"Cannot find {lib_name}. Searched: {lib_path}. "
        f"Run 'zeclock --bootstrap' to install."
    )


class ZeDMDBackend(DMDBackend):
    """Direct ZeDMD communication via libzedmd ctypes.

    This backend loads the libzedmd shared library and communicates
    directly with ZeDMD hardware over WiFi or USB, bypassing the
    need for a separate dmdserver process.

    Args:
        wifi_addr: WiFi IP address of the ZeDMD device.
        device: USB serial device path (e.g. /dev/ttyUSB0).
        brightness: Display brightness level (0-15, default 10).
        width: Display width in pixels (default 128).
        height: Display height in pixels (default 32).

    Raises:
        ImportError: If libzedmd shared library cannot be found.
    """

    def __init__(
        self,
        wifi_addr: Optional[str] = None,
        device: Optional[str] = None,
        brightness: int = 10,
        width: int = 128,
        height: int = 32,
    ):
        self._wifi_addr = wifi_addr
        self._device = device
        self._brightness = max(0, min(15, brightness))
        self._width = width
        self._height = height
        self._connected = False
        self._instance: Optional[int] = None

        # Load library — raises ImportError if not found
        lib_path = _find_library()
        try:
            self._lib = ctypes.CDLL(str(lib_path))
        except OSError as e:
            raise ImportError(f"Failed to load libzedmd from {lib_path}: {e}") from e
        self._setup_ctypes()

    def _setup_ctypes(self) -> None:
        """Declare ctypes function signatures for the libzedmd C API."""
        lib = self._lib

        lib.ZeDMD_GetInstance.restype = ctypes.c_void_p
        lib.ZeDMD_GetInstance.argtypes = []

        lib.ZeDMD_Open.restype = ctypes.c_bool
        lib.ZeDMD_Open.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_OpenWiFi.restype = ctypes.c_bool
        lib.ZeDMD_OpenWiFi.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        lib.ZeDMD_Close.restype = None
        lib.ZeDMD_Close.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_SetFrameSize.restype = None
        lib.ZeDMD_SetFrameSize.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_uint16,
        ]

        lib.ZeDMD_SetBrightness.restype = None
        lib.ZeDMD_SetBrightness.argtypes = [ctypes.c_void_p, ctypes.c_uint8]

        lib.ZeDMD_SetDevice.restype = None
        lib.ZeDMD_SetDevice.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

        lib.ZeDMD_RenderRgb888.restype = None
        lib.ZeDMD_RenderRgb888.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint8),
        ]

    @property
    def connected(self) -> bool:
        """Whether the backend is currently connected to a display."""
        return self._connected

    def connect(self) -> bool:
        """Establish connection to the ZeDMD display.

        Calls ZeDMD_GetInstance, then connects via WiFi (ZeDMD_OpenWiFi)
        or USB (ZeDMD_Open). On success, configures frame size and brightness.

        Returns:
            True if connection was established successfully, False otherwise.
        """
        self._instance = self._lib.ZeDMD_GetInstance()
        if not self._instance:
            logger.error("Failed to create ZeDMD instance")
            return False

        # Connect via WiFi or USB
        if self._wifi_addr:
            ok = self._lib.ZeDMD_OpenWiFi(self._instance, self._wifi_addr.encode())
        elif self._device:
            self._lib.ZeDMD_SetDevice(self._instance, self._device.encode())
            ok = self._lib.ZeDMD_Open(self._instance)
        else:
            # Auto-detect USB
            ok = self._lib.ZeDMD_Open(self._instance)

        if not ok:
            logger.warning("Failed to connect to ZeDMD")
            return False

        # Configure display
        self._lib.ZeDMD_SetFrameSize(self._instance, self._width, self._height)
        self._lib.ZeDMD_SetBrightness(self._instance, self._brightness)
        self._connected = True
        return True

    def send_frame(
        self,
        image: Image.Image,
        buffered: bool = True,
        color: Tuple[int, int, int] = (255, 128, 0),
    ) -> bool:
        """Send a frame to the ZeDMD display.

        Sends the image as RGB888 directly via ZeDMD_RenderRgb888,
        avoiding any Python-level pixel conversion. If the image is
        not RGB, it is colorized using the provided color tuple first.

        Args:
            image: PIL Image to send (any mode, will be converted to RGB).
            buffered: Unused, kept for interface compatibility.
            color: RGB color tuple for grayscale colorization.

        Returns:
            True if the frame was sent successfully, False otherwise.
        """
        if not self._connected:
            return False

        # Colorize grayscale if needed
        if image.mode != "RGB":
            image = colorize_grayscale(image, color)

        # Send RGB888 directly — no Python-level pixel conversion needed
        rgb_data = image.tobytes()
        frame_array = (ctypes.c_uint8 * len(rgb_data)).from_buffer_copy(rgb_data)
        self._lib.ZeDMD_RenderRgb888(self._instance, frame_array)
        return True

    def disconnect(self) -> None:
        """Close the connection to the ZeDMD display.

        Calls ZeDMD_Close to release the hardware connection.
        """
        if self._instance and self._connected:
            self._lib.ZeDMD_Close(self._instance)
        self._connected = False
        self._instance = None
