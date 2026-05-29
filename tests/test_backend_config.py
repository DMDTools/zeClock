"""Tests for zeclock.backend_config module."""

import configparser
import logging
from pathlib import Path

import pytest

from zeclock.backend_config import (
    BackendConfig,
    _parse_config_file,
    _validate_brightness,
    load_config,
)


class TestBackendConfigDefaults:
    """Test BackendConfig dataclass defaults."""

    def test_default_values(self):
        config = BackendConfig()
        assert config.backend == "auto"
        assert config.wifi_addr is None
        assert config.device is None
        assert config.brightness == 10
        assert config.dmdserver_host == "localhost"
        assert config.dmdserver_port == 6789


class TestValidateBrightness:
    """Test brightness validation logic."""

    def test_valid_brightness_min(self):
        assert _validate_brightness("0") == 0

    def test_valid_brightness_max(self):
        assert _validate_brightness("15") == 15

    def test_valid_brightness_mid(self):
        assert _validate_brightness("7") == 7

    def test_brightness_below_range(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _validate_brightness("-1")
        assert result == 10
        assert "outside valid range" in caplog.text

    def test_brightness_above_range(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _validate_brightness("16")
        assert result == 10
        assert "outside valid range" in caplog.text

    def test_brightness_non_integer(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _validate_brightness("abc")
        assert result == 10
        assert "not an integer" in caplog.text

    def test_brightness_float_string(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _validate_brightness("7.5")
        assert result == 10
        assert "not an integer" in caplog.text

    def test_brightness_empty_string(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = _validate_brightness("")
        assert result == 10
        assert "not an integer" in caplog.text


class TestParseConfigFile:
    """Test INI config file parsing."""

    def test_nonexistent_file(self, tmp_path):
        result = _parse_config_file(tmp_path / "nonexistent.ini")
        assert result == {}

    def test_full_config(self, tmp_path):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = 192.168.1.100\n"
            "device = /dev/ttyUSB0\n"
            "brightness = 12\n"
            "\n"
            "[dmdserver]\n"
            "host = 10.0.0.1\n"
            "port = 7890\n"
        )
        result = _parse_config_file(config_file)
        assert result["wifi_addr"] == "192.168.1.100"
        assert result["device"] == "/dev/ttyUSB0"
        assert result["brightness"] == 12
        assert result["dmdserver_host"] == "10.0.0.1"
        assert result["dmdserver_port"] == 7890

    def test_partial_config_zedmd_only(self, tmp_path):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = 192.168.0.35\n"
            "brightness = 5\n"
        )
        result = _parse_config_file(config_file)
        assert result["wifi_addr"] == "192.168.0.35"
        assert result["brightness"] == 5
        assert "device" not in result
        assert "dmdserver_host" not in result

    def test_empty_values_ignored(self, tmp_path):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = \n"
            "device = \n"
            "brightness = \n"
        )
        result = _parse_config_file(config_file)
        assert "wifi_addr" not in result
        assert "device" not in result
        assert "brightness" not in result

    def test_invalid_port_uses_default(self, tmp_path, caplog):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[dmdserver]\n"
            "host = myhost\n"
            "port = notanumber\n"
        )
        with caplog.at_level(logging.WARNING):
            result = _parse_config_file(config_file)
        assert result["dmdserver_host"] == "myhost"
        assert "dmdserver_port" not in result
        assert "Invalid dmdserver port" in caplog.text


class TestLoadConfig:
    """Test the full load_config function with priority merging."""

    def test_defaults_when_no_file_no_cli(self, tmp_path):
        config = load_config(config_path=tmp_path / "nonexistent.ini")
        assert config.backend == "auto"
        assert config.wifi_addr is None
        assert config.device is None
        assert config.brightness == 10
        assert config.dmdserver_host == "localhost"
        assert config.dmdserver_port == 6789

    def test_config_file_values_applied(self, tmp_path):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = 10.0.0.5\n"
            "brightness = 8\n"
            "\n"
            "[dmdserver]\n"
            "host = server1\n"
            "port = 1234\n"
        )
        config = load_config(config_path=config_file)
        assert config.wifi_addr == "10.0.0.5"
        assert config.brightness == 8
        assert config.dmdserver_host == "server1"
        assert config.dmdserver_port == 1234

    def test_cli_overrides_config_file(self, tmp_path):
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = 10.0.0.5\n"
            "brightness = 8\n"
            "\n"
            "[dmdserver]\n"
            "host = server1\n"
            "port = 1234\n"
        )
        config = load_config(
            config_path=config_file,
            wifi_addr="192.168.1.1",
            brightness=15,
            dmdserver_host="override-host",
            dmdserver_port=9999,
        )
        assert config.wifi_addr == "192.168.1.1"
        assert config.brightness == 15
        assert config.dmdserver_host == "override-host"
        assert config.dmdserver_port == 9999

    def test_cli_backend_applied(self, tmp_path):
        config = load_config(
            config_path=tmp_path / "nonexistent.ini",
            backend="zedmd",
        )
        assert config.backend == "zedmd"

    def test_wifi_addr_takes_precedence_over_device(self, tmp_path, caplog):
        """Req 4.4: If both wifi_addr and device are configured, use WiFi."""
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "wifi_addr = 192.168.0.35\n"
            "device = /dev/ttyUSB0\n"
        )
        with caplog.at_level(logging.INFO):
            config = load_config(config_path=config_file)
        assert config.wifi_addr == "192.168.0.35"
        assert config.device is None
        assert "using WiFi, ignoring device" in caplog.text

    def test_wifi_addr_cli_overrides_device_in_file(self, tmp_path, caplog):
        """CLI wifi_addr should still trigger the wifi-over-device rule."""
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "device = /dev/ttyUSB0\n"
        )
        with caplog.at_level(logging.INFO):
            config = load_config(config_path=config_file, wifi_addr="10.0.0.1")
        assert config.wifi_addr == "10.0.0.1"
        assert config.device is None

    def test_invalid_brightness_cli_defaults_to_10(self, tmp_path, caplog):
        """Req 4.6: Invalid brightness from CLI should default to 10."""
        with caplog.at_level(logging.WARNING):
            config = load_config(
                config_path=tmp_path / "nonexistent.ini",
                brightness=20,
            )
        assert config.brightness == 10
        assert "outside valid range" in caplog.text

    def test_device_only_no_wifi(self, tmp_path):
        """Req 4.9: Only device configured, no wifi_addr."""
        config_file = tmp_path / "zeclock.ini"
        config_file.write_text(
            "[zedmd]\n"
            "device = /dev/ttyACM0\n"
        )
        config = load_config(config_path=config_file)
        assert config.wifi_addr is None
        assert config.device == "/dev/ttyACM0"

    def test_neither_wifi_nor_device(self, tmp_path):
        """Req 4.9: Neither configured means auto-detection will be attempted."""
        config = load_config(config_path=tmp_path / "nonexistent.ini")
        assert config.wifi_addr is None
        assert config.device is None
