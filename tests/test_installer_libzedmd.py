"""Tests for libzedmd installer functions."""

import platform
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from zeclock.installer import (
    GITHUB_REPO_ZEDMD,
    LIB_DIR,
    LIBZEDMD_LIBS,
    LIBZEDMD_VERSION_FILE,
    get_latest_zedmd_version,
    is_libzedmd_installed,
    install_libzedmd,
    _download_libzedmd_release,
    _install_libzedmd_files,
    check_and_install_resources,
    install_dmdserver,
)


class TestConstants:
    """Test that constants are correctly defined."""

    def test_github_repo_zedmd(self):
        assert GITHUB_REPO_ZEDMD == "PPUC/libzedmd"

    def test_lib_dir_is_under_zeclock(self):
        assert LIB_DIR == Path.home() / ".zeclock" / "lib"

    def test_version_file_path(self):
        assert LIBZEDMD_VERSION_FILE == LIB_DIR / ".libzedmd-version"

    def test_linux_libs(self):
        assert LIBZEDMD_LIBS["Linux"] == [
            "libzedmd.so",
            "libsockpp.so",
            "libserialport.so",
        ]

    def test_macos_libs(self):
        assert LIBZEDMD_LIBS["Darwin"] == [
            "libzedmd.dylib",
            "libsockpp.dylib",
            "libserialport.dylib",
        ]

    def test_windows_libs(self):
        assert LIBZEDMD_LIBS["Windows"] == [
            "zedmd.dll",
            "sockpp.dll",
            "serialport.dll",
        ]


class TestIsLibzedmdInstalled:
    """Test is_libzedmd_installed() function."""

    def test_returns_false_when_lib_dir_missing(self, tmp_path):
        with patch("zeclock.installer.LIB_DIR", tmp_path / "nonexistent"):
            assert is_libzedmd_installed() is False

    def test_returns_false_when_main_lib_missing(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        version_file = lib_dir / ".libzedmd-version"
        version_file.write_text("v0.7.3")
        with (
            patch("zeclock.installer.LIB_DIR", lib_dir),
            patch("zeclock.installer.LIBZEDMD_VERSION_FILE", version_file),
        ):
            assert is_libzedmd_installed() is False

    def test_returns_false_when_version_file_missing(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        # Create the main library file
        system = platform.system()
        main_lib = LIBZEDMD_LIBS.get(system, ["libzedmd.so"])[0]
        (lib_dir / main_lib).write_text("fake")
        version_file = lib_dir / ".libzedmd-version"
        with (
            patch("zeclock.installer.LIB_DIR", lib_dir),
            patch("zeclock.installer.LIBZEDMD_VERSION_FILE", version_file),
        ):
            assert is_libzedmd_installed() is False

    def test_returns_true_when_lib_and_version_exist(self, tmp_path):
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        system = platform.system()
        main_lib = LIBZEDMD_LIBS.get(system, ["libzedmd.so"])[0]
        (lib_dir / main_lib).write_text("fake")
        version_file = lib_dir / ".libzedmd-version"
        version_file.write_text("v0.7.3")
        with (
            patch("zeclock.installer.LIB_DIR", lib_dir),
            patch("zeclock.installer.LIBZEDMD_VERSION_FILE", version_file),
        ):
            assert is_libzedmd_installed() is True


class TestInstallLibzedmd:
    """Test install_libzedmd() function."""

    @patch("zeclock.installer.get_latest_zedmd_version")
    @patch("zeclock.installer.is_libzedmd_installed")
    @patch("zeclock.installer.LIBZEDMD_VERSION_FILE")
    def test_skips_download_when_version_matches(
        self, mock_version_file, mock_is_installed, mock_get_version, tmp_path
    ):
        mock_get_version.return_value = "v0.7.3"
        mock_is_installed.return_value = True
        mock_version_file.exists.return_value = True
        mock_version_file.read_text.return_value = "v0.7.3"

        result = install_libzedmd()
        assert result is True

    @patch("zeclock.installer._install_libzedmd_files")
    @patch("zeclock.installer._download_libzedmd_release")
    @patch("zeclock.installer.get_latest_zedmd_version")
    @patch("zeclock.installer.is_libzedmd_installed")
    def test_downloads_when_not_installed(
        self, mock_is_installed, mock_get_version, mock_download, mock_install, tmp_path
    ):
        mock_is_installed.return_value = False
        mock_get_version.return_value = "v0.7.3"
        mock_download.return_value = tmp_path

        with patch("zeclock.installer.LIBZEDMD_VERSION_FILE") as mock_vf:
            mock_vf.write_text = MagicMock()
            result = install_libzedmd()

        assert result is True
        mock_download.assert_called_once()
        mock_install.assert_called_once()

    @patch("zeclock.installer.get_latest_zedmd_version")
    def test_returns_false_on_network_error(self, mock_get_version):
        mock_get_version.side_effect = Exception("Network error")
        result = install_libzedmd()
        assert result is False


class TestCheckAndInstallResources:
    """Test that check_and_install_resources uses libzedmd by default."""

    @patch("zeclock.installer.are_resources_installed")
    @patch("zeclock.installer.is_libzedmd_installed")
    def test_returns_true_when_all_installed(self, mock_libzedmd, mock_resources):
        mock_libzedmd.return_value = True
        mock_resources.return_value = True
        assert check_and_install_resources(interactive=False) is True

    @patch("zeclock.installer.install_dotclk_resources")
    @patch("zeclock.installer.install_libzedmd")
    @patch("zeclock.installer.are_resources_installed")
    @patch("zeclock.installer.is_libzedmd_installed")
    def test_installs_libzedmd_when_missing(
        self, mock_is_installed, mock_resources, mock_install_zedmd, mock_install_res
    ):
        mock_is_installed.return_value = False
        mock_resources.return_value = True
        mock_install_zedmd.return_value = True

        result = check_and_install_resources(interactive=False)
        assert result is True
        mock_install_zedmd.assert_called_once()
        mock_install_res.assert_not_called()


class TestInstallDmdserverStillAvailable:
    """Test that install_dmdserver remains available."""

    def test_install_dmdserver_is_callable(self):
        assert callable(install_dmdserver)
