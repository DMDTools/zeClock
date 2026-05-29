"""Tests for the ZeDMDBackend class with mocked ctypes."""

import ctypes
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from PIL import Image

from zeclock.backends.base import DMDBackend


@pytest.fixture
def mock_lib():
    """Create a mock ctypes library with all ZeDMD functions."""
    lib = MagicMock()
    lib.ZeDMD_GetInstance.return_value = 0x12345678  # fake pointer
    lib.ZeDMD_Open.return_value = True
    lib.ZeDMD_OpenWiFi.return_value = True
    lib.ZeDMD_Close.return_value = None
    lib.ZeDMD_SetFrameSize.return_value = None
    lib.ZeDMD_SetBrightness.return_value = None
    lib.ZeDMD_SetDevice.return_value = None
    lib.ZeDMD_RenderRgb565.return_value = None
    return lib


@pytest.fixture
def zedmd_backend(mock_lib):
    """Create a ZeDMDBackend with mocked library loading."""
    with patch("zeclock.backends.zedmd._find_library") as mock_find:
        mock_find.return_value = Path("/fake/path/libzedmd.so")
        with patch("ctypes.CDLL", return_value=mock_lib):
            from zeclock.backends.zedmd import ZeDMDBackend

            backend = ZeDMDBackend(wifi_addr="192.168.0.35", brightness=10)
            return backend


@pytest.fixture
def zedmd_backend_usb(mock_lib):
    """Create a ZeDMDBackend configured for USB device."""
    with patch("zeclock.backends.zedmd._find_library") as mock_find:
        mock_find.return_value = Path("/fake/path/libzedmd.so")
        with patch("ctypes.CDLL", return_value=mock_lib):
            from zeclock.backends.zedmd import ZeDMDBackend

            backend = ZeDMDBackend(device="/dev/ttyUSB0", brightness=8)
            return backend


@pytest.fixture
def zedmd_backend_auto(mock_lib):
    """Create a ZeDMDBackend with no WiFi or device (auto-detect)."""
    with patch("zeclock.backends.zedmd._find_library") as mock_find:
        mock_find.return_value = Path("/fake/path/libzedmd.so")
        with patch("ctypes.CDLL", return_value=mock_lib):
            from zeclock.backends.zedmd import ZeDMDBackend

            backend = ZeDMDBackend()
            return backend


class TestZeDMDBackendInheritance:
    """Test that ZeDMDBackend properly implements DMDBackend."""

    def test_is_instance_of_dmd_backend(self, zedmd_backend):
        assert isinstance(zedmd_backend, DMDBackend)


class TestZeDMDBackendConnect:
    """Test connect() behavior for different configurations."""

    def test_connect_wifi_calls_open_wifi(self, zedmd_backend, mock_lib):
        """connect() with wifi_addr calls ZeDMD_OpenWiFi."""
        result = zedmd_backend.connect()
        assert result is True
        mock_lib.ZeDMD_GetInstance.assert_called_once()
        mock_lib.ZeDMD_OpenWiFi.assert_called_once()
        # Verify the WiFi address was passed
        call_args = mock_lib.ZeDMD_OpenWiFi.call_args
        assert call_args[0][1] == b"192.168.0.35"

    def test_connect_usb_device_calls_set_device_then_open(
        self, zedmd_backend_usb, mock_lib
    ):
        """connect() with device calls ZeDMD_SetDevice then ZeDMD_Open."""
        result = zedmd_backend_usb.connect()
        assert result is True
        mock_lib.ZeDMD_GetInstance.assert_called_once()
        mock_lib.ZeDMD_SetDevice.assert_called_once()
        call_args = mock_lib.ZeDMD_SetDevice.call_args
        assert call_args[0][1] == b"/dev/ttyUSB0"
        mock_lib.ZeDMD_Open.assert_called_once()

    def test_connect_auto_detect_calls_open(self, zedmd_backend_auto, mock_lib):
        """connect() with neither wifi nor device calls ZeDMD_Open (auto-detect)."""
        result = zedmd_backend_auto.connect()
        assert result is True
        mock_lib.ZeDMD_GetInstance.assert_called_once()
        mock_lib.ZeDMD_Open.assert_called_once()
        mock_lib.ZeDMD_OpenWiFi.assert_not_called()
        mock_lib.ZeDMD_SetDevice.assert_not_called()

    def test_connect_sets_frame_size_and_brightness(self, zedmd_backend, mock_lib):
        """After successful connect, frame size and brightness are configured."""
        zedmd_backend.connect()
        mock_lib.ZeDMD_SetFrameSize.assert_called_once()
        mock_lib.ZeDMD_SetBrightness.assert_called_once()
        # Check brightness value
        brightness_call = mock_lib.ZeDMD_SetBrightness.call_args
        assert brightness_call[0][1] == 10

    def test_connect_returns_false_when_open_fails(self, zedmd_backend, mock_lib):
        """connect() returns False when ZeDMD_OpenWiFi returns False."""
        mock_lib.ZeDMD_OpenWiFi.return_value = False
        result = zedmd_backend.connect()
        assert result is False
        assert not zedmd_backend.connected

    def test_connect_returns_false_when_get_instance_fails(
        self, zedmd_backend, mock_lib
    ):
        """connect() returns False when ZeDMD_GetInstance returns null."""
        mock_lib.ZeDMD_GetInstance.return_value = 0  # null pointer
        result = zedmd_backend.connect()
        assert result is False

    def test_connected_property_true_after_connect(self, zedmd_backend, mock_lib):
        """connected property is True after successful connect."""
        assert not zedmd_backend.connected
        zedmd_backend.connect()
        assert zedmd_backend.connected


class TestZeDMDBackendSendFrame:
    """Test send_frame() behavior."""

    def test_send_frame_converts_to_rgb565_and_calls_render(
        self, zedmd_backend, mock_lib
    ):
        """send_frame() sends RGB888 data via ZeDMD_RenderRgb888."""
        zedmd_backend.connect()
        img = Image.new("RGB", (128, 32), (255, 0, 0))
        result = zedmd_backend.send_frame(img)
        assert result is True
        mock_lib.ZeDMD_RenderRgb888.assert_called_once()

    def test_send_frame_returns_false_when_not_connected(
        self, zedmd_backend, mock_lib
    ):
        """send_frame() returns False when not connected."""
        # Make connect fail so backend stays disconnected
        mock_lib.ZeDMD_GetInstance.return_value = 0
        img = Image.new("RGB", (128, 32), (255, 0, 0))
        result = zedmd_backend.send_frame(img)
        assert result is False

    def test_send_frame_colorizes_grayscale_images(self, zedmd_backend, mock_lib):
        """send_frame() colorizes grayscale images before conversion."""
        zedmd_backend.connect()
        # Create a grayscale image (mode "L")
        gray_img = Image.new("L", (128, 32), 128)
        with patch("zeclock.backends.zedmd.colorize_grayscale") as mock_colorize:
            # Return an RGB image from colorize
            mock_colorize.return_value = Image.new("RGB", (128, 32), (128, 64, 0))
            result = zedmd_backend.send_frame(gray_img, color=(255, 128, 0))
            assert result is True
            mock_colorize.assert_called_once_with(gray_img, (255, 128, 0))

    def test_send_frame_does_not_colorize_rgb_images(self, zedmd_backend, mock_lib):
        """send_frame() does not colorize images already in RGB mode."""
        zedmd_backend.connect()
        rgb_img = Image.new("RGB", (128, 32), (255, 0, 0))
        with patch("zeclock.backends.zedmd.colorize_grayscale") as mock_colorize:
            zedmd_backend.send_frame(rgb_img)
            mock_colorize.assert_not_called()


class TestZeDMDBackendDisconnect:
    """Test disconnect() behavior."""

    def test_disconnect_calls_zedmd_close(self, zedmd_backend, mock_lib):
        """disconnect() calls ZeDMD_Close when connected."""
        zedmd_backend.connect()
        zedmd_backend.disconnect()
        mock_lib.ZeDMD_Close.assert_called_once()

    def test_disconnect_sets_connected_false(self, zedmd_backend, mock_lib):
        """disconnect() sets connected to False."""
        zedmd_backend.connect()
        assert zedmd_backend.connected
        zedmd_backend.disconnect()
        assert not zedmd_backend.connected

    def test_disconnect_without_connect_does_not_call_close(
        self, zedmd_backend, mock_lib
    ):
        """disconnect() without prior connect does not call ZeDMD_Close."""
        zedmd_backend.disconnect()
        mock_lib.ZeDMD_Close.assert_not_called()


class TestZeDMDBackendImportError:
    """Test ImportError handling when library is not found."""

    def test_import_error_when_library_not_found(self):
        """ZeDMDBackend raises ImportError when _find_library fails."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("Cannot find libzedmd.so"),
        ):
            from zeclock.backends.zedmd import ZeDMDBackend

            with pytest.raises(ImportError, match="Cannot find libzedmd.so"):
                ZeDMDBackend()

    def test_import_error_when_cdll_fails(self):
        """ZeDMDBackend raises ImportError when CDLL loading fails."""
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = Path("/fake/path/libzedmd.so")
            with patch(
                "ctypes.CDLL",
                side_effect=OSError("cannot open shared object file"),
            ):
                from zeclock.backends.zedmd import ZeDMDBackend

                with pytest.raises(ImportError, match="Failed to load libzedmd"):
                    ZeDMDBackend()


class TestZeDMDBackendBrightnessClamping:
    """Test that brightness values are clamped to 0-15."""

    def test_brightness_clamped_to_max_15(self, mock_lib):
        """Brightness above 15 is clamped to 15."""
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = Path("/fake/path/libzedmd.so")
            with patch("ctypes.CDLL", return_value=mock_lib):
                from zeclock.backends.zedmd import ZeDMDBackend

                backend = ZeDMDBackend(brightness=20)
                assert backend._brightness == 15

    def test_brightness_clamped_to_min_0(self, mock_lib):
        """Brightness below 0 is clamped to 0."""
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = Path("/fake/path/libzedmd.so")
            with patch("ctypes.CDLL", return_value=mock_lib):
                from zeclock.backends.zedmd import ZeDMDBackend

                backend = ZeDMDBackend(brightness=-5)
                assert backend._brightness == 0

    def test_brightness_within_range_unchanged(self, mock_lib):
        """Brightness within 0-15 is not modified."""
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = Path("/fake/path/libzedmd.so")
            with patch("ctypes.CDLL", return_value=mock_lib):
                from zeclock.backends.zedmd import ZeDMDBackend

                backend = ZeDMDBackend(brightness=7)
                assert backend._brightness == 7
