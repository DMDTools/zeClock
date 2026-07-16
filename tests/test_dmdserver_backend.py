"""Tests for the DMDServerBackend class with mocked sockets."""

import socket
import struct
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from PIL import Image

from zeclock.backends.base import DMDBackend
from zeclock.backends.dmdserver import (
    DMDServerBackend,
    _RGB565_R,
    _RGB565_G,
    _RGB565_B,
)


@pytest.fixture
def mock_socket():
    """Create a mock socket object."""
    sock = MagicMock(spec=socket.socket)
    return sock


@pytest.fixture
def backend():
    """Create a DMDServerBackend with default settings."""
    return DMDServerBackend(host="localhost", port=6789)


@pytest.fixture
def connected_backend(mock_socket):
    """Create a DMDServerBackend that is already connected."""
    with patch("socket.socket", return_value=mock_socket):
        b = DMDServerBackend(host="127.0.0.1", port=9999)
        b.connect()
        return b


class TestDMDServerBackendInheritance:
    """Test that DMDServerBackend properly implements DMDBackend."""

    def test_is_instance_of_dmd_backend(self, backend):
        """DMDServerBackend is a subclass of DMDBackend."""
        assert isinstance(backend, DMDBackend)


class TestDMDServerBackendInit:
    """Test __init__() stores parameters correctly."""

    def test_stores_host_and_port(self):
        """Constructor stores host and port."""
        b = DMDServerBackend(host="192.168.1.10", port=1234)
        assert b.host == "192.168.1.10"
        assert b.port == 1234

    def test_default_host_and_port(self):
        """Constructor uses default host and port when not specified."""
        b = DMDServerBackend()
        assert b.host == "localhost"
        assert b.port == 6789

    def test_initially_not_connected(self, backend):
        """Backend is not connected after construction."""
        assert not backend.connected


class TestDMDServerBackendConnect:
    """Test connect() behavior."""

    def test_connect_success(self, mock_socket):
        """connect() returns True and sets connected on success."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            result = b.connect()
            assert result is True
            assert b.connected
            mock_socket.connect.assert_called_once_with(("localhost", 6789))

    def test_connect_creates_tcp_socket(self, mock_socket):
        """connect() creates an AF_INET SOCK_STREAM socket."""
        with patch("socket.socket", return_value=mock_socket) as sock_cls:
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            sock_cls.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)

    def test_connect_failure_returns_false(self, mock_socket):
        """connect() returns False when socket.connect() raises."""
        mock_socket.connect.side_effect = ConnectionRefusedError("Connection refused")
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            result = b.connect()
            assert result is False
            assert not b.connected

    def test_connect_failure_on_socket_creation(self):
        """connect() returns False when socket creation raises."""
        with patch("socket.socket", side_effect=OSError("Cannot create socket")):
            b = DMDServerBackend(host="localhost", port=6789)
            result = b.connect()
            assert result is False
            assert not b.connected


class TestDMDServerBackendDisconnect:
    """Test disconnect() behavior."""

    def test_disconnect_closes_socket(self, connected_backend, mock_socket):
        """disconnect() closes the TCP socket."""
        connected_backend.disconnect()
        mock_socket.close.assert_called()

    def test_disconnect_sets_connected_false(self, connected_backend):
        """disconnect() sets connected to False."""
        assert connected_backend.connected
        connected_backend.disconnect()
        assert not connected_backend.connected

    def test_disconnect_sends_black_frame_before_close(
        self, connected_backend, mock_socket
    ):
        """disconnect() sends a black frame before closing the socket."""
        connected_backend.disconnect()
        # sendall should be called at least once (the black frame)
        assert mock_socket.sendall.called

    def test_disconnect_without_connect_is_safe(self, backend):
        """disconnect() without prior connect does not raise."""
        backend.disconnect()  # Should not raise
        assert not backend.connected


class TestDMDServerBackendSendFrame:
    """Test send_frame() behavior."""

    def test_send_frame_rgb_image(self, connected_backend, mock_socket):
        """send_frame() sends data for an RGB image."""
        img = Image.new("RGB", (128, 32), (255, 0, 0))
        result = connected_backend.send_frame(img)
        assert result is True
        mock_socket.sendall.assert_called()

    def test_send_frame_returns_false_when_not_connected(self):
        """send_frame() returns False when not connected and reconnect fails."""
        with patch("socket.socket") as mock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_cls.return_value = mock_sock
            b = DMDServerBackend(host="localhost", port=6789)
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            result = b.send_frame(img)
            assert result is False

    def test_send_frame_attempts_reconnect_when_disconnected(self, mock_socket):
        """send_frame() attempts reconnection if not connected."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            # Not connected yet; send_frame should trigger connect
            img = Image.new("RGB", (128, 32), (0, 255, 0))
            result = b.send_frame(img)
            assert result is True
            # socket.connect() was called as part of auto-reconnection
            mock_socket.connect.assert_called_once_with(("localhost", 6789))

    def test_send_frame_colorizes_grayscale(self, connected_backend, mock_socket):
        """send_frame() colorizes grayscale images before conversion."""
        gray_img = Image.new("L", (128, 32), 128)
        with patch("zeclock.backends.dmdserver.colorize_grayscale") as mock_colorize:
            mock_colorize.return_value = Image.new("RGB", (128, 32), (128, 64, 0))
            result = connected_backend.send_frame(gray_img, color=(255, 128, 0))
            assert result is True
            mock_colorize.assert_called_once_with(gray_img, (255, 128, 0))

    def test_send_frame_does_not_colorize_rgb(self, connected_backend, mock_socket):
        """send_frame() does not colorize images already in RGB mode."""
        rgb_img = Image.new("RGB", (128, 32), (0, 128, 255))
        with patch("zeclock.backends.dmdserver.colorize_grayscale") as mock_colorize:
            connected_backend.send_frame(rgb_img)
            mock_colorize.assert_not_called()

    def test_send_frame_error_marks_disconnected(self, connected_backend, mock_socket):
        """send_frame() marks backend as disconnected on socket error."""
        mock_socket.sendall.side_effect = BrokenPipeError("Connection lost")
        img = Image.new("RGB", (128, 32), (255, 0, 0))
        result = connected_backend.send_frame(img)
        assert result is False
        assert not connected_backend.connected


class TestDMDServerBackendFrameCaching:
    """Test frame identity caching behavior."""

    def test_same_frame_object_uses_cache(self, connected_backend, mock_socket):
        """Sending the same Image object twice reuses the cached message."""
        img = Image.new("RGB", (128, 32), (100, 50, 25))
        connected_backend.send_frame(img)
        first_call_data = mock_socket.sendall.call_args[0][0]

        # Reset mock to track second call
        mock_socket.sendall.reset_mock()
        connected_backend.send_frame(img)
        second_call_data = mock_socket.sendall.call_args[0][0]

        # Both calls should send identical data (cached)
        assert first_call_data == second_call_data

    def test_different_frame_object_encodes_fresh(self, connected_backend, mock_socket):
        """Sending a different Image object re-encodes the frame."""
        img1 = Image.new("RGB", (128, 32), (255, 0, 0))
        img2 = Image.new("RGB", (128, 32), (0, 255, 0))
        connected_backend.send_frame(img1)
        first_call_data = mock_socket.sendall.call_args[0][0]

        connected_backend.send_frame(img2)
        second_call_data = mock_socket.sendall.call_args[0][0]

        # Data should differ because frames have different colors
        assert first_call_data != second_call_data

    def test_cache_invalidated_by_new_frame(self, connected_backend, mock_socket):
        """Cache is updated when a new frame is sent."""
        img1 = Image.new("RGB", (128, 32), (255, 0, 0))
        img2 = Image.new("RGB", (128, 32), (0, 0, 255))

        connected_backend.send_frame(img1)
        connected_backend.send_frame(img2)

        # Now sending img1 again should re-encode (cache only holds last frame)
        with patch.object(
            connected_backend, "_rgb_to_rgb565", wraps=connected_backend._rgb_to_rgb565
        ) as mock_convert:
            connected_backend.send_frame(img1)
            mock_convert.assert_called_once()


class TestDMDServerBackendRGB565Conversion:
    """Test _rgb_to_rgb565() conversion correctness."""

    def test_pure_red_pixel(self, backend):
        """Pure red (255,0,0) converts to correct RGB565 value."""
        img = Image.new("RGB", (1, 1), (255, 0, 0))
        result = backend._rgb_to_rgb565(img)
        # Red: (255 >> 3) << 11 = 31 << 11 = 0xF800
        expected = struct.pack(">H", 0xF800)
        assert result == expected

    def test_pure_green_pixel(self, backend):
        """Pure green (0,255,0) converts to correct RGB565 value."""
        img = Image.new("RGB", (1, 1), (0, 255, 0))
        result = backend._rgb_to_rgb565(img)
        # Green: (255 >> 2) << 5 = 63 << 5 = 0x07E0
        expected = struct.pack(">H", 0x07E0)
        assert result == expected

    def test_pure_blue_pixel(self, backend):
        """Pure blue (0,0,255) converts to correct RGB565 value."""
        img = Image.new("RGB", (1, 1), (0, 0, 255))
        result = backend._rgb_to_rgb565(img)
        # Blue: 255 >> 3 = 31 = 0x001F
        expected = struct.pack(">H", 0x001F)
        assert result == expected

    def test_white_pixel(self, backend):
        """White (255,255,255) converts to 0xFFFF in RGB565."""
        img = Image.new("RGB", (1, 1), (255, 255, 255))
        result = backend._rgb_to_rgb565(img)
        expected = struct.pack(">H", 0xFFFF)
        assert result == expected

    def test_black_pixel(self, backend):
        """Black (0,0,0) converts to 0x0000 in RGB565."""
        img = Image.new("RGB", (1, 1), (0, 0, 0))
        result = backend._rgb_to_rgb565(img)
        expected = struct.pack(">H", 0x0000)
        assert result == expected

    def test_multi_pixel_image(self, backend):
        """Multiple pixels are all converted correctly."""
        img = Image.new("RGB", (3, 1))
        img.putpixel((0, 0), (255, 0, 0))
        img.putpixel((1, 0), (0, 255, 0))
        img.putpixel((2, 0), (0, 0, 255))
        result = backend._rgb_to_rgb565(img)
        expected = struct.pack(">HHH", 0xF800, 0x07E0, 0x001F)
        assert result == expected

    def test_output_length_matches_pixel_count(self, backend):
        """Output is exactly 2 bytes per pixel (big-endian uint16)."""
        img = Image.new("RGB", (128, 32), (100, 100, 100))
        result = backend._rgb_to_rgb565(img)
        assert len(result) == 128 * 32 * 2


class TestDMDServerBackendRGB565LUTs:
    """Test the pre-computed RGB565 lookup tables."""

    def test_lut_r_length(self):
        """Red LUT has 256 entries."""
        assert len(_RGB565_R) == 256

    def test_lut_g_length(self):
        """Green LUT has 256 entries."""
        assert len(_RGB565_G) == 256

    def test_lut_b_length(self):
        """Blue LUT has 256 entries."""
        assert len(_RGB565_B) == 256

    def test_lut_r_max_value(self):
        """Red LUT for 255 gives (31 << 11) = 0xF800."""
        assert _RGB565_R[255] == 0xF800

    def test_lut_g_max_value(self):
        """Green LUT for 255 gives (63 << 5) = 0x07E0."""
        assert _RGB565_G[255] == 0x07E0

    def test_lut_b_max_value(self):
        """Blue LUT for 255 gives 31 = 0x001F."""
        assert _RGB565_B[255] == 0x001F

    def test_lut_r_zero(self):
        """Red LUT for 0 gives 0."""
        assert _RGB565_R[0] == 0

    def test_lut_g_zero(self):
        """Green LUT for 0 gives 0."""
        assert _RGB565_G[0] == 0

    def test_lut_b_zero(self):
        """Blue LUT for 0 gives 0."""
        assert _RGB565_B[0] == 0


class TestDMDServerBackendHeaderStructure:
    """Test that the DMDStream header is correctly formatted."""

    def _extract_header(self, data: bytes) -> dict:
        """Parse a DMDStream header from the raw message bytes."""
        assert len(data) >= 25, f"Message too short for header: {len(data)} bytes"
        magic = data[0:10]
        version = data[10]
        mode = int.from_bytes(data[11:15], "big")
        width = int.from_bytes(data[15:17], "big")
        height = int.from_bytes(data[17:19], "big")
        buffered = data[19]
        disconnect_others = data[20]
        length = int.from_bytes(data[21:25], "big")
        return {
            "magic": magic,
            "version": version,
            "mode": mode,
            "width": width,
            "height": height,
            "buffered": buffered,
            "disconnect_others": disconnect_others,
            "length": length,
        }

    def test_header_magic_word(self, mock_socket):
        """Header starts with b'DMDStream\\x00'."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["magic"] == b"DMDStream\x00"

    def test_header_version(self, mock_socket):
        """Header version field is 1."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["version"] == 1

    def test_header_mode_rgb565(self, mock_socket):
        """Header mode field is 3 (RGB565)."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["mode"] == 3

    def test_header_dimensions(self, mock_socket):
        """Header contains correct width and height."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["width"] == 128
            assert header["height"] == 32

    def test_header_buffered_flag_true(self, mock_socket):
        """Header buffered flag is 1 when buffered=True."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img, buffered=True)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["buffered"] == 1

    def test_header_buffered_flag_false(self, mock_socket):
        """Header buffered flag is 0 when buffered=False."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img, buffered=False)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["buffered"] == 0

    def test_header_disconnect_others_flag(self, mock_socket):
        """Header disconnectOthers flag is always 1."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["disconnect_others"] == 1

    def test_header_data_length_field(self, mock_socket):
        """Header length field matches actual RGB565 data size."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            # RGB565 for 128x32 = 8192 bytes
            expected_length = 128 * 32 * 2
            assert header["length"] == expected_length

    def test_total_message_size(self, mock_socket):
        """Total message is header (25 bytes) + RGB565 data."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (128, 32), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            expected_size = 25 + (128 * 32 * 2)
            assert len(data) == expected_size

    def test_header_with_different_image_size(self, mock_socket):
        """Header dimensions match the actual image size."""
        with patch("socket.socket", return_value=mock_socket):
            b = DMDServerBackend(host="localhost", port=6789)
            b.connect()
            img = Image.new("RGB", (64, 16), (0, 0, 0))
            b.send_frame(img)
            data = mock_socket.sendall.call_args[0][0]
            header = self._extract_header(data)
            assert header["width"] == 64
            assert header["height"] == 16
            assert header["length"] == 64 * 16 * 2
