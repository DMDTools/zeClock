"""ZeDMD backend using libzedmd via ctypes.

Simple reconnection strategy:
- On stream error from libzedmd → immediately mark as disconnected
- Stop sending frames, close the instance
- Wait with exponential backoff, then reconnect fresh
"""

import ctypes
import logging
import platform
import threading
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


# ctypes callback type matching: void (*)(const char* format, va_list args, const void* userData)
ZEDMD_LOG_CALLBACK = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p
)


class ZeDMDBackend(DMDBackend):
    """Direct ZeDMD communication via libzedmd ctypes.

    Simple error handling: on any stream error detected via the libzedmd
    log callback, the connection is immediately marked as lost. The main
    loop (clock.py) handles the retry by calling send_frame which returns
    False, triggering the reconnection flow.

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

        # Reconnection state
        self._error_logged = False  # avoid spamming the same disconnect message

        # Thread-safe flag: set by log callback on error
        self._stream_error_flag = False
        self._error_lock = threading.Lock()

        # Load library — raises ImportError if not found
        lib_path = _find_library()
        try:
            self._lib = ctypes.CDLL(str(lib_path))
        except OSError as e:
            raise ImportError(f"Failed to load libzedmd from {lib_path}: {e}") from e
        self._setup_ctypes()

        # Keep a reference to the callback to prevent garbage collection
        self._log_callback_ref: object = None

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

        lib.ZeDMD_GetWidth.restype = ctypes.c_uint16
        lib.ZeDMD_GetWidth.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_GetHeight.restype = ctypes.c_uint16
        lib.ZeDMD_GetHeight.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_GetPanelWidth.restype = ctypes.c_uint16
        lib.ZeDMD_GetPanelWidth.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_GetPanelHeight.restype = ctypes.c_uint16
        lib.ZeDMD_GetPanelHeight.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_EnableUpscaling.restype = None
        lib.ZeDMD_EnableUpscaling.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_DisableUpscaling.restype = None
        lib.ZeDMD_DisableUpscaling.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_ClearScreen.restype = None
        lib.ZeDMD_ClearScreen.argtypes = [ctypes.c_void_p]

        lib.ZeDMD_SetLogCallback.restype = None
        lib.ZeDMD_SetLogCallback.argtypes = [
            ctypes.c_void_p,
            ZEDMD_LOG_CALLBACK,
            ctypes.c_void_p,
        ]

        lib.ZeDMD_FormatLogMessage.restype = ctypes.c_char_p
        lib.ZeDMD_FormatLogMessage.argtypes = [
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]

    def _log_callback(
        self,
        fmt: Optional[bytes],
        args: Optional[ctypes.c_void_p],
        user_data: Optional[ctypes.c_void_p],
    ) -> None:
        """Callback invoked by libzedmd on its internal thread.

        On stream error: immediately set the error flag so send_frame
        stops sending. All other log messages are forwarded to Python logging.

        Note: This runs on a C thread — logging may fail if colorama's
        StreamWrapper is active. All operations are wrapped in try/except.
        """
        try:
            # Decode message
            msg: Optional[str] = None
            try:
                formatted = self._lib.ZeDMD_FormatLogMessage(fmt, args, user_data)
                if formatted:
                    msg = formatted.decode("utf-8", errors="replace")
            except Exception:
                pass
            if not msg and fmt:
                try:
                    msg = fmt.decode("utf-8", errors="replace")
                except Exception:
                    return
            if not msg:
                return

            # Check for stream errors — immediately flag disconnect
            stream_error_patterns = (
                "StreamBytes failed",
                "libserialport error",
                "TCP stream error",
                "UDP stream error",
            )
            if any(pattern in msg for pattern in stream_error_patterns):
                with self._error_lock:
                    self._stream_error_flag = True
                # Only log the first error, not the flood
                if not self._error_logged:
                    logger.warning("🔧 libzedmd: %s", msg)
                return

            # Non-error messages
            logger.debug("🔧 libzedmd: %s", msg)
        except Exception:
            # Swallow all exceptions — this runs on a C thread and must not crash
            pass

    @property
    def connected(self) -> bool:
        """Whether the backend is currently connected to a display."""
        return self._connected

    @property
    def width(self) -> int:
        """Display width in pixels (may be updated after connect via auto-detection)."""
        return self._width

    @property
    def height(self) -> int:
        """Display height in pixels (may be updated after connect via auto-detection)."""
        return self._height

    @property
    def is_hd(self) -> bool:
        """Whether the connected display is HD (256x64) resolution."""
        return self._width >= 256 and self._height >= 64

    def connect(self) -> bool:
        """Establish connection to the ZeDMD display.

        Creates a fresh instance, registers the log callback, connects
        via WiFi or USB, configures frame size and brightness.

        Returns:
            True if connection was established successfully, False otherwise.
        """
        # Clean slate
        with self._error_lock:
            self._stream_error_flag = False
        self._error_logged = False

        self._instance = self._lib.ZeDMD_GetInstance()
        if not self._instance:
            logger.error("Failed to create ZeDMD instance")
            return False

        # Register log callback for error detection
        self._log_callback_ref = ZEDMD_LOG_CALLBACK(self._log_callback)
        self._lib.ZeDMD_SetLogCallback(self._instance, self._log_callback_ref, None)

        # Connect via WiFi or USB
        if self._wifi_addr:
            ok = self._lib.ZeDMD_OpenWiFi(self._instance, self._wifi_addr.encode())
        elif self._device:
            self._lib.ZeDMD_SetDevice(self._instance, self._device.encode())
            ok = self._lib.ZeDMD_Open(self._instance)
        else:
            ok = self._lib.ZeDMD_Open(self._instance)

        if not ok:
            logger.warning("Failed to connect to ZeDMD")
            self._instance = None
            self._log_callback_ref = None
            return False

        # Auto-detect display resolution from hardware panel dimensions
        panel_width = self._lib.ZeDMD_GetPanelWidth(self._instance)
        panel_height = self._lib.ZeDMD_GetPanelHeight(self._instance)
        if panel_width > 0 and panel_height > 0:
            if panel_width != self._width or panel_height != self._height:
                logger.info(
                    "ZeDMD panel is %dx%d (configured: %dx%d) — adapting",
                    panel_width,
                    panel_height,
                    self._width,
                    self._height,
                )
                self._width = panel_width
                self._height = panel_height

        # Configure display
        self._lib.ZeDMD_SetFrameSize(self._instance, self._width, self._height)
        self._lib.ZeDMD_EnableUpscaling(self._instance)
        self._lib.ZeDMD_SetBrightness(self._instance, self._brightness)

        self._connected = True
        logger.info("ZeDMD connected successfully (%dx%d)", self._width, self._height)
        return True

    def send_frame(
        self,
        image: Image.Image,
        buffered: bool = True,
        color: Tuple[int, int, int] = (255, 128, 0),
    ) -> bool:
        """Send a frame to the ZeDMD display.

        If a stream error was detected (via log callback), immediately
        marks as disconnected, closes the instance, and returns False.
        The caller (clock.py main loop) handles the wait and retry.

        Args:
            image: PIL Image to send (any mode, will be converted to RGB).
            buffered: Unused, kept for interface compatibility.
            color: RGB color tuple for grayscale colorization.

        Returns:
            True if the frame was sent successfully, False if disconnected.
        """
        if not self._connected or not self._instance:
            return False

        # Check if log callback flagged a stream error
        with self._error_lock:
            has_error = self._stream_error_flag

        if has_error:
            if not self._error_logged:
                logger.warning("ZeDMD connection lost — closing instance")
                self._error_logged = True
            self._connected = False
            # Close the dead instance (best effort, may fail)
            self._close_instance()
            return False

        # Colorize grayscale if needed
        if image.mode != "RGB":
            image = colorize_grayscale(image, color)

        # Resize frame if it doesn't match display resolution
        if image.size != (self._width, self._height):
            image = image.resize((self._width, self._height), Image.Resampling.NEAREST)

        # Send RGB888 directly
        try:
            rgb_data = image.tobytes()
            frame_array = (ctypes.c_uint8 * len(rgb_data)).from_buffer_copy(rgb_data)
            self._lib.ZeDMD_RenderRgb888(self._instance, frame_array)
        except (OSError, ctypes.ArgumentError) as e:
            logger.warning("ZeDMD render error: %s — closing instance", e)
            self._connected = False
            self._close_instance()
            return False

        return True

    def _close_instance(self) -> None:
        """Close the current ZeDMD instance (best effort).

        After a connection loss, ZeDMD_Close may hang or crash because
        the internal thread is stuck. We attempt it with a short timeout
        mindset but accept that it may not fully clean up.
        """
        if self._instance:
            try:
                self._lib.ZeDMD_Close(self._instance)
            except (OSError, ctypes.ArgumentError):
                pass
        self._instance = None
        self._log_callback_ref = None

    def disconnect(self) -> None:
        """Close the connection to the ZeDMD display.

        Calls ClearScreen before closing so the display goes dark
        instead of showing the ZeDMD idle animation.
        """
        if self._connected and self._instance:
            try:
                self._lib.ZeDMD_ClearScreen(self._instance)
            except (OSError, ctypes.ArgumentError):
                pass  # Best effort
        self._connected = False
        self._close_instance()
