"""ZeDMD backend using libzedmd via ctypes.

Includes connection health monitoring and automatic reconnection for both
USB and WiFi transports. Uses the libzedmd log callback to detect
communication failures (StreamBytes errors, serial/TCP/UDP errors) and
triggers reconnection with exponential backoff.
"""

import ctypes
import logging
import platform
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from ..overlay import colorize_grayscale
from .base import DMDBackend

logger = logging.getLogger(__name__)

# Library search path
LIB_DIR = Path.home() / ".zeclock" / "lib"

# Reconnection constants
HEALTH_CHECK_INTERVAL = 5.0  # Seconds between health checks
RECONNECT_DELAY_INITIAL = 2.0  # Initial delay before first reconnect attempt
RECONNECT_DELAY_MAX = 30.0  # Maximum delay between reconnect attempts
RECONNECT_DELAY_MULTIPLIER = 1.5  # Backoff multiplier
# Number of StreamBytes failures (detected via log) before declaring disconnection
FAILURE_THRESHOLD = 3


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
# On Linux/macOS, va_list is a pointer-sized type. We use c_void_p for both args and userData.
ZEDMD_LOG_CALLBACK = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p
)


class ZeDMDBackend(DMDBackend):
    """Direct ZeDMD communication via libzedmd ctypes.

    This backend loads the libzedmd shared library and communicates
    directly with ZeDMD hardware over WiFi or USB, bypassing the
    need for a separate dmdserver process.

    Connection monitoring strategy:
    - Registers a log callback with libzedmd to intercept internal error messages
    - Detects "StreamBytes failed", "libserialport error", "TCP stream error",
      "UDP stream error" messages as indicators of connection loss
    - After FAILURE_THRESHOLD consecutive failures, marks connection as lost
    - Periodic health check via ZeDMD_GetWidth (returns 0 if no active connection)
    - Automatic reconnection with exponential backoff (works for both USB and WiFi)

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

        # Health check and reconnection state
        self._last_health_check = 0.0
        self._consecutive_failures = 0
        self._reconnect_delay = RECONNECT_DELAY_INITIAL
        self._last_reconnect_attempt = 0.0
        self._reconnecting = False

        # Log-based failure detection (thread-safe)
        self._stream_error_count = 0
        self._stream_error_lock = threading.Lock()
        self._last_lib_log: Optional[str] = None

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
        """Callback invoked by libzedmd for log messages.

        Formats the message using ZeDMD_FormatLogMessage and inspects it
        for error patterns indicating connection loss. This runs on the
        libzedmd Run thread, so access to shared state is protected by a lock.

        Note: On Linux x86_64, va_list is a struct (not a pointer), so
        ZeDMD_FormatLogMessage may fail to resolve format arguments.
        In that case, the raw format string is logged at TRACE level only.
        """
        msg: Optional[str] = None
        try:
            # Use the library's own formatter to resolve the va_list
            formatted = self._lib.ZeDMD_FormatLogMessage(fmt, args, user_data)
            if formatted:
                msg = formatted.decode("utf-8", errors="replace")
        except Exception:
            pass

        if not msg:
            # Formatting failed (va_list incompatibility on x86_64)
            # Fall back to raw format string with unresolved placeholders
            if fmt:
                try:
                    msg = fmt.decode("utf-8", errors="replace")
                except Exception:
                    return
            else:
                return

        # Forward to Python logging at appropriate level
        error_patterns = (
            "StreamBytes failed",
            "libserialport error",
            "TCP stream error",
            "UDP stream error",
            "Full frame forced, error",
            "Unable to",
            "failed",
            "Failed",
            "error",
        )
        is_error = any(pattern in msg for pattern in error_patterns)
        if is_error:
            # Suppress repeated warnings during reconnection
            if not self._reconnecting:
                logger.warning("🔧 libzedmd: %s", msg)
        else:
            logger.debug("🔧 libzedmd: %s", msg)
        self._last_lib_log = msg

        # Detect stream error patterns for reconnection logic
        stream_error_patterns = (
            "StreamBytes failed",
            "libserialport error",
            "TCP stream error",
            "UDP stream error",
            "Full frame forced, error",
        )
        if any(pattern in msg for pattern in stream_error_patterns):
            # Ignore errors during reconnection — they come from the dying old instance
            if self._reconnecting:
                return
            with self._stream_error_lock:
                self._stream_error_count += 1
                count = self._stream_error_count
            logger.debug("libzedmd stream error detected (#%d): %s", count, msg)

    def _reset_error_count(self) -> None:
        """Reset the stream error counter (called on successful operations)."""
        with self._stream_error_lock:
            self._stream_error_count = 0

    def _get_error_count(self) -> int:
        """Get the current stream error count (thread-safe)."""
        with self._stream_error_lock:
            return self._stream_error_count

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

        Calls ZeDMD_GetInstance, registers the log callback, then connects
        via WiFi (ZeDMD_OpenWiFi) or USB (ZeDMD_Open). On success,
        configures frame size and brightness.

        Returns:
            True if connection was established successfully, False otherwise.
        """
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
            # Auto-detect USB
            ok = self._lib.ZeDMD_Open(self._instance)

        if not ok:
            logger.warning("Failed to connect to ZeDMD")
            # Clean up the instance on failure
            self._instance = None
            self._log_callback_ref = None
            return False

        # Auto-detect display resolution from hardware panel dimensions
        panel_width = self._lib.ZeDMD_GetPanelWidth(self._instance)
        panel_height = self._lib.ZeDMD_GetPanelHeight(self._instance)
        if panel_width > 0 and panel_height > 0:
            if panel_width != self._width or panel_height != self._height:
                logger.info(
                    "ZeDMD panel is %dx%d (configured: %dx%d) — adapting to panel resolution",
                    panel_width,
                    panel_height,
                    self._width,
                    self._height,
                )
                self._width = panel_width
                self._height = panel_height

        # Configure display frame size and enable upscaling (libzedmd handles
        # centering/scaling if frame size differs from panel size)
        self._lib.ZeDMD_SetFrameSize(self._instance, self._width, self._height)
        self._lib.ZeDMD_EnableUpscaling(self._instance)
        self._lib.ZeDMD_SetBrightness(self._instance, self._brightness)
        self._connected = True
        self._consecutive_failures = 0
        self._reconnect_delay = RECONNECT_DELAY_INITIAL
        self._last_health_check = time.monotonic()
        self._reset_error_count()
        logger.info("ZeDMD connected successfully (%dx%d)", self._width, self._height)
        return True

    def _check_health(self) -> bool:
        """Check if the ZeDMD connection is still alive.

        Two-pronged detection:
        1. Check stream error count from log callback (detects USB serial
           failures and WiFi TCP/UDP send errors in real-time)
        2. Check ZeDMD_GetWidth — returns 0 when the internal active
           connection pointer is null (e.g. after Close or fatal error)

        Returns:
            True if the connection appears healthy, False otherwise.
        """
        if not self._instance:
            return False

        # Check 1: Log-based error detection (most reliable for both USB & WiFi)
        error_count = self._get_error_count()
        if error_count >= FAILURE_THRESHOLD:
            logger.warning(
                "ZeDMD health check: %d stream errors detected via log callback",
                error_count,
            )
            return False

        # Check 2: Width probe (catches cases where pActive becomes null)
        try:
            width = self._lib.ZeDMD_GetWidth(self._instance)
            if width == 0:
                logger.warning("ZeDMD health check: GetWidth returned 0")
                return False
        except (OSError, ctypes.ArgumentError):
            return False

        return True

    def _attempt_reconnect(self) -> bool:
        """Attempt to reconnect to the ZeDMD device.

        Closes the current (dead) connection and tries to establish
        a new one. Uses exponential backoff between attempts.
        Works for both USB (device re-enumeration) and WiFi (device reboot).

        Returns:
            True if reconnection succeeded, False otherwise.
        """
        now = time.monotonic()

        # Respect backoff delay
        time_since_last = now - self._last_reconnect_attempt
        if time_since_last < self._reconnect_delay:
            remaining = self._reconnect_delay - time_since_last
            # Log waiting status once per second (avoid spam)
            if int(remaining) != int(remaining + 1):
                logger.info(
                    "ZeDMD reconnection: waiting %.0fs before next attempt...",
                    remaining,
                )
            return False

        self._last_reconnect_attempt = now
        logger.info(
            "Attempting ZeDMD reconnection...",
        )

        # Close the old instance cleanly
        self._close_instance()

        # Reset error counter before reconnection attempt — old errors
        # from the dead connection should not poison the new one
        self._reset_error_count()

        # Try to reconnect
        success = self.connect()

        if success:
            logger.info("ZeDMD reconnected successfully")
            self._reconnecting = False
        else:
            # Increase backoff delay for next attempt
            self._reconnect_delay = min(
                self._reconnect_delay * RECONNECT_DELAY_MULTIPLIER,
                RECONNECT_DELAY_MAX,
            )
            logger.info(
                "ZeDMD reconnection failed — next retry in %.0fs",
                self._reconnect_delay,
            )

        return success

    def _close_instance(self) -> None:
        """Close the current ZeDMD instance without resetting config state.

        Note: When called during reconnection after a connection loss,
        ZeDMD_Close may segfault if the internal Run thread is in a
        corrupted state. We catch this by skipping Close when reconnecting
        (the old instance is abandoned — minor memory leak but avoids crash).
        """
        if self._instance:
            if not self._reconnecting:
                # Safe to close: normal shutdown path
                try:
                    self._lib.ZeDMD_Close(self._instance)
                except (OSError, ctypes.ArgumentError):
                    # Instance may already be invalid
                    pass
            else:
                # Reconnecting after crash: skip Close to avoid segfault
                logger.debug("Skipping ZeDMD_Close on dead instance to avoid segfault")
        self._connected = False
        self._instance = None
        self._log_callback_ref = None

    def send_frame(
        self,
        image: Image.Image,
        buffered: bool = True,
        color: Tuple[int, int, int] = (255, 128, 0),
    ) -> bool:
        """Send a frame to the ZeDMD display.

        Includes connection health monitoring: periodically checks if the
        device is still reachable (via log-based error detection and
        GetWidth probe), and catches errors during rendering.
        If the connection is lost, enters reconnection mode.

        Args:
            image: PIL Image to send (any mode, will be converted to RGB).
            buffered: Unused, kept for interface compatibility.
            color: RGB color tuple for grayscale colorization.

        Returns:
            True if the frame was sent successfully, False if the
            connection appears to be lost (reconnection in progress).
        """
        # If we're in reconnection mode, attempt reconnect
        if self._reconnecting:
            if not self._attempt_reconnect():
                return False
            # Reconnection succeeded, continue with frame send

        if not self._connected or not self._instance:
            return False

        # Periodic health check
        now = time.monotonic()
        if now - self._last_health_check >= HEALTH_CHECK_INTERVAL:
            self._last_health_check = now
            if not self._check_health():
                logger.warning(
                    "ZeDMD connection lost — will retry in %.0fs",
                    self._reconnect_delay,
                )
                self._connected = False
                self._reconnecting = True
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
            self._consecutive_failures += 1
            logger.warning(
                "ZeDMD render error (failure #%d): %s",
                self._consecutive_failures,
                e,
            )
            if self._consecutive_failures >= FAILURE_THRESHOLD:
                logger.error(
                    "ZeDMD connection lost (repeated render failures) — will retry in %.0fs",
                    self._reconnect_delay,
                )
                self._connected = False
                self._reconnecting = True
                return False
            # Single failure might be transient
            return True

        # Successful render — reset ctypes-level failure counter
        # (log-based errors are checked in health check)
        self._consecutive_failures = 0
        return True

    def disconnect(self) -> None:
        """Close the connection to the ZeDMD display.

        Calls ZeDMD_Close to release the hardware connection.
        """
        self._reconnecting = False
        self._close_instance()
