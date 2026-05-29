"""Tests for the backend factory module."""

import logging
import sys
from unittest.mock import patch, MagicMock

import pytest

from zeclock.backends.factory import create_backend, VALID_BACKENDS


class TestCreateBackendInvalidMode:
    """Test that invalid backend values cause sys.exit."""

    def test_invalid_backend_exits(self):
        with pytest.raises(SystemExit):
            create_backend(backend="invalid")

    def test_empty_string_exits(self):
        with pytest.raises(SystemExit):
            create_backend(backend="")

    def test_unknown_backend_name_exits(self):
        """An unrecognized backend name causes exit."""
        with pytest.raises(SystemExit):
            create_backend(backend="serial")


class TestCreateBackendDmdserverMode:
    """Test explicit dmdserver mode."""

    def test_dmdserver_mode_returns_dmdserver_backend(self):
        backend = create_backend(backend="dmdserver")
        from zeclock.backends.dmdserver import DMDServerBackend

        assert isinstance(backend, DMDServerBackend)

    def test_dmdserver_mode_uses_provided_host_port(self):
        backend = create_backend(
            backend="dmdserver", dmdserver_host="10.0.0.1", dmdserver_port=9999
        )
        assert backend.host == "10.0.0.1"
        assert backend.port == 9999


class TestCreateBackendZedmdMode:
    """Test explicit zedmd mode."""

    def test_zedmd_mode_exits_when_library_not_found(self):
        with patch(
            "zeclock.backends.factory._create_zedmd",
            side_effect=SystemExit(1),
        ):
            with pytest.raises(SystemExit):
                create_backend(backend="zedmd")

    def test_zedmd_mode_import_error_exits(self):
        """When libzedmd is not installed, zedmd mode should exit."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("Cannot find libzedmd.so"),
        ):
            with pytest.raises(SystemExit):
                create_backend(backend="zedmd")

    def test_zedmd_mode_returns_zedmd_backend_when_available(self):
        """When libzedmd is available, zedmd mode returns ZeDMDBackend."""
        mock_lib = MagicMock()
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = "/fake/path/libzedmd.so"
            with patch("ctypes.CDLL", return_value=mock_lib):
                backend = create_backend(backend="zedmd")
                from zeclock.backends.zedmd import ZeDMDBackend

                assert isinstance(backend, ZeDMDBackend)


class TestCreateBackendAutoMode:
    """Test auto mode fallback behavior."""

    def test_auto_is_default(self):
        """Default backend value is 'auto'."""
        # When libzedmd is not available, auto should fall back to dmdserver
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("lib not found"),
        ):
            backend = create_backend()
            from zeclock.backends.dmdserver import DMDServerBackend

            assert isinstance(backend, DMDServerBackend)

    def test_auto_falls_back_to_dmdserver_when_zedmd_unavailable(self):
        """When ZeDMD import fails, auto mode falls back to dmdserver."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("lib not found"),
        ):
            backend = create_backend(backend="auto")
            from zeclock.backends.dmdserver import DMDServerBackend

            assert isinstance(backend, DMDServerBackend)

    def test_auto_prefers_zedmd_when_available(self):
        """When ZeDMD library is available, auto mode selects it."""
        mock_lib = MagicMock()
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = "/fake/path/libzedmd.so"
            with patch("ctypes.CDLL", return_value=mock_lib):
                backend = create_backend(backend="auto")
                from zeclock.backends.zedmd import ZeDMDBackend

                assert isinstance(backend, ZeDMDBackend)

    def test_auto_exits_when_both_fail(self):
        """When both backends fail, auto mode exits."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("lib not found"),
        ):
            with patch(
                "zeclock.backends.dmdserver.DMDServerBackend.__init__",
                side_effect=Exception("TCP error"),
            ):
                with pytest.raises(SystemExit):
                    create_backend(backend="auto")

    def test_auto_logs_selected_backend_at_info_level(self, caplog):
        """Auto mode logs the selected backend name at INFO level."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("lib not found"),
        ):
            with caplog.at_level(logging.INFO, logger="zeclock.backends.factory"):
                backend = create_backend(backend="auto")
                assert "Selected backend: dmdserver" in caplog.text

    def test_auto_logs_zedmd_when_selected(self, caplog):
        """Auto mode logs 'zedmd' when ZeDMD is selected."""
        mock_lib = MagicMock()
        with patch("zeclock.backends.zedmd._find_library") as mock_find:
            mock_find.return_value = "/fake/path/libzedmd.so"
            with patch("ctypes.CDLL", return_value=mock_lib):
                with caplog.at_level(
                    logging.INFO, logger="zeclock.backends.factory"
                ):
                    create_backend(backend="auto")
                    assert "Selected backend: zedmd" in caplog.text

    def test_auto_both_fail_error_message_includes_reasons(self, caplog):
        """When both fail, error message includes both failure reasons."""
        with patch(
            "zeclock.backends.zedmd._find_library",
            side_effect=ImportError("libzedmd not found"),
        ):
            with patch(
                "zeclock.backends.dmdserver.DMDServerBackend.__init__",
                side_effect=Exception("Connection refused"),
            ):
                with caplog.at_level(
                    logging.ERROR, logger="zeclock.backends.factory"
                ):
                    with pytest.raises(SystemExit):
                        create_backend(backend="auto")
                    assert "libzedmd not found" in caplog.text
                    assert "Connection refused" in caplog.text


class TestValidBackends:
    """Test the VALID_BACKENDS constant."""

    def test_valid_backends_contains_expected_values(self):
        assert "auto" in VALID_BACKENDS
        assert "zedmd" in VALID_BACKENDS
        assert "dmdserver" in VALID_BACKENDS

    def test_valid_backends_has_three_entries(self):
        assert len(VALID_BACKENDS) == 3
