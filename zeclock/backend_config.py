"""
Backend configuration management for zeClock.

Loads configuration from ~/.zeclock/config/zeclock.ini and merges
with CLI arguments (CLI takes precedence over config file values).
"""

import configparser
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .paths import get_config_dir

logger = logging.getLogger(__name__)

# Default config file location
CONFIG_DIR = get_config_dir()
CONFIG_FILE = CONFIG_DIR / "zeclock.ini"

# Days of the week for schedule parsing
DAYS_OF_WEEK = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


@dataclass
class LocationConfig:
    """Global location configuration used by weather, sunrise/sunset, etc."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city_name: str = ""


@dataclass
class BrightnessScheduleConfig:
    """Configuration for brightness scheduling."""

    max_brightness: int = 7  # HW brightness for 100% (0-15)
    schedule_lines: Dict[str, str] = field(default_factory=dict)
    sunrise_brightness: Optional[int] = None  # Brightness % during daytime
    sunset_brightness: Optional[int] = None  # Brightness % during nighttime
    time_only: Optional[str] = None  # "HH:MM-HH:MM" — time-only mode range
    sun_transition_minutes: int = 30  # Gradual transition duration (minutes)


@dataclass
class MqttConfig:
    """MQTT remote control configuration."""

    enabled: bool = False
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    device_id: str = "zeclock"
    topic_prefix: str = "zeclock"
    ha_discovery: bool = True
    ha_discovery_prefix: str = "homeassistant"
    state_interval: float = 30.0


@dataclass
class RestApiConfig:
    """REST API remote control configuration."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class BackendConfig:
    """Configuration for DMD backend selection and connection parameters."""

    backend: str = "auto"  # auto | zedmd | dmdserver
    wifi_addr: Optional[str] = None
    device: Optional[str] = None
    brightness: int = 10
    dmdserver_host: str = "localhost"
    dmdserver_port: int = 6789
    width: int = 128
    height: int = 32
    upscale_mode: str = "epx"  # nearest | epx | hq2x
    font: str = "STANDARD"  # Global font name (without .fnt extension)
    location: LocationConfig = field(default_factory=LocationConfig)
    brightness_schedule: BrightnessScheduleConfig = field(
        default_factory=BrightnessScheduleConfig
    )
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    rest_api: RestApiConfig = field(default_factory=RestApiConfig)


def _validate_brightness(value: str) -> int:
    """Validate brightness value, returning default 10 if invalid.

    Args:
        value: The brightness value as a string from config.

    Returns:
        Validated brightness integer in range 0-15, or 10 if invalid.
    """
    try:
        brightness = int(value)
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid brightness value '{value}' (not an integer), using default 10"
        )
        return 10

    if brightness < 0 or brightness > 15:
        logger.warning(
            f"Brightness {brightness} outside valid range (0-15), using default 10"
        )
        return 10

    return brightness


def _parse_config_file(config_path: Path) -> dict:
    """Parse the INI config file and return a flat dict of values.

    Args:
        config_path: Path to the zeclock.ini config file.

    Returns:
        Dictionary with parsed config values (only keys that are present).
    """
    result: dict[str, object] = {}

    if not config_path.exists():
        logger.debug(f"Config file not found: {config_path}")
        return result

    parser = configparser.RawConfigParser()
    parser.read(config_path)

    # Read [zedmd] section
    if parser.has_section("zedmd"):
        if parser.has_option("zedmd", "wifi_addr"):
            val = parser.get("zedmd", "wifi_addr").strip()
            if val:
                result["wifi_addr"] = val

        if parser.has_option("zedmd", "device"):
            val = parser.get("zedmd", "device").strip()
            if val:
                result["device"] = val

        if parser.has_option("zedmd", "brightness"):
            val = parser.get("zedmd", "brightness").strip()
            if val:
                result["brightness"] = _validate_brightness(val)

    # Read [dmdserver] section
    if parser.has_section("dmdserver"):
        if parser.has_option("dmdserver", "host"):
            val = parser.get("dmdserver", "host").strip()
            if val:
                result["dmdserver_host"] = val

        if parser.has_option("dmdserver", "port"):
            val = parser.get("dmdserver", "port").strip()
            if val:
                try:
                    result["dmdserver_port"] = int(val)
                except ValueError:
                    logger.warning(
                        f"Invalid dmdserver port '{val}', using default 6789"
                    )

    # Read [display] section
    if parser.has_section("display"):
        if parser.has_option("display", "width"):
            val = parser.get("display", "width").strip()
            if val:
                try:
                    result["width"] = int(val)
                except ValueError:
                    logger.warning(f"Invalid display width '{val}', using default 128")

        if parser.has_option("display", "height"):
            val = parser.get("display", "height").strip()
            if val:
                try:
                    result["height"] = int(val)
                except ValueError:
                    logger.warning(f"Invalid display height '{val}', using default 32")

        if parser.has_option("display", "upscale"):
            val = parser.get("display", "upscale").strip().lower()
            if val in ("nearest", "epx", "hq2x"):
                result["upscale_mode"] = val
            elif val:
                logger.warning(f"Invalid upscale mode '{val}', using default 'epx'")

        if parser.has_option("display", "font"):
            val = parser.get("display", "font").strip()
            if val:
                result["font"] = val

    # Read [location] section (global location for weather, sunrise/sunset, etc.)
    if parser.has_section("location"):
        location = LocationConfig()
        if parser.has_option("location", "latitude"):
            val = parser.get("location", "latitude").strip()
            if val:
                try:
                    location.latitude = float(val)
                except ValueError:
                    logger.warning(f"Invalid latitude '{val}'")
        if parser.has_option("location", "longitude"):
            val = parser.get("location", "longitude").strip()
            if val:
                try:
                    location.longitude = float(val)
                except ValueError:
                    logger.warning(f"Invalid longitude '{val}'")
        if parser.has_option("location", "city_name"):
            location.city_name = parser.get("location", "city_name").strip()
        result["location"] = location

    # Read [mqtt] section
    if parser.has_section("mqtt"):
        mqtt = MqttConfig()
        if parser.has_option("mqtt", "enabled"):
            val = parser.get("mqtt", "enabled").strip().lower()
            mqtt.enabled = val in ("true", "1", "yes")
        if parser.has_option("mqtt", "host"):
            val = parser.get("mqtt", "host").strip()
            if val:
                mqtt.host = val
        if parser.has_option("mqtt", "port"):
            val = parser.get("mqtt", "port").strip()
            if val:
                try:
                    mqtt.port = int(val)
                except ValueError:
                    logger.warning(f"Invalid MQTT port '{val}', using default 1883")
        if parser.has_option("mqtt", "username"):
            val = parser.get("mqtt", "username").strip()
            if val:
                mqtt.username = val
        if parser.has_option("mqtt", "password"):
            val = parser.get("mqtt", "password").strip()
            if val:
                mqtt.password = val
        if parser.has_option("mqtt", "device_id"):
            val = parser.get("mqtt", "device_id").strip()
            if val:
                mqtt.device_id = val
        if parser.has_option("mqtt", "topic_prefix"):
            val = parser.get("mqtt", "topic_prefix").strip()
            if val:
                mqtt.topic_prefix = val
        if parser.has_option("mqtt", "ha_discovery"):
            val = parser.get("mqtt", "ha_discovery").strip().lower()
            mqtt.ha_discovery = val in ("true", "1", "yes")
        if parser.has_option("mqtt", "ha_discovery_prefix"):
            val = parser.get("mqtt", "ha_discovery_prefix").strip()
            if val:
                mqtt.ha_discovery_prefix = val
        if parser.has_option("mqtt", "state_interval"):
            val = parser.get("mqtt", "state_interval").strip()
            if val:
                try:
                    mqtt.state_interval = max(5.0, float(val))
                except ValueError:
                    logger.warning(
                        f"Invalid MQTT state_interval '{val}', using default 30"
                    )
        result["mqtt"] = mqtt

    # Read [rest_api] section
    if parser.has_section("rest_api"):
        rest = RestApiConfig()
        if parser.has_option("rest_api", "enabled"):
            val = parser.get("rest_api", "enabled").strip().lower()
            rest.enabled = val in ("true", "1", "yes")
        if parser.has_option("rest_api", "host"):
            val = parser.get("rest_api", "host").strip()
            if val:
                rest.host = val
        if parser.has_option("rest_api", "port"):
            val = parser.get("rest_api", "port").strip()
            if val:
                try:
                    rest.port = int(val)
                except ValueError:
                    logger.warning(f"Invalid REST API port '{val}', using default 8080")
        result["rest_api"] = rest

    # Read [brightness_schedule] section
    if parser.has_section("brightness_schedule"):
        bs = BrightnessScheduleConfig()
        if parser.has_option("brightness_schedule", "max_brightness"):
            val = parser.get("brightness_schedule", "max_brightness").strip()
            if val:
                try:
                    bs.max_brightness = max(1, min(15, int(val)))
                except ValueError:
                    logger.warning(f"Invalid max_brightness '{val}', using default 7")

        if parser.has_option("brightness_schedule", "sunrise_brightness"):
            val = (
                parser.get("brightness_schedule", "sunrise_brightness")
                .strip()
                .rstrip("%")
            )
            if val:
                try:
                    bs.sunrise_brightness = max(0, min(100, int(val)))
                except ValueError:
                    logger.warning(f"Invalid sunrise_brightness '{val}'")

        if parser.has_option("brightness_schedule", "sunset_brightness"):
            val = (
                parser.get("brightness_schedule", "sunset_brightness")
                .strip()
                .rstrip("%")
            )
            if val:
                try:
                    bs.sunset_brightness = max(0, min(100, int(val)))
                except ValueError:
                    logger.warning(f"Invalid sunset_brightness '{val}'")

        if parser.has_option("brightness_schedule", "time_only"):
            bs.time_only = parser.get("brightness_schedule", "time_only").strip()

        if parser.has_option("brightness_schedule", "sun_transition_minutes"):
            val = parser.get("brightness_schedule", "sun_transition_minutes").strip()
            if val:
                try:
                    bs.sun_transition_minutes = max(0, min(120, int(val)))
                except ValueError:
                    logger.warning(f"Invalid sun_transition_minutes '{val}'")

        # Parse day-of-week schedule lines
        schedule_lines = {}
        for key in DAYS_OF_WEEK + ["default"]:
            if parser.has_option("brightness_schedule", key):
                schedule_lines[key] = parser.get("brightness_schedule", key).strip()
        bs.schedule_lines = schedule_lines

        result["brightness_schedule"] = bs

    return result


def load_config(
    config_path: Optional[Path] = None,
    backend: Optional[str] = None,
    wifi_addr: Optional[str] = None,
    device: Optional[str] = None,
    brightness: Optional[int] = None,
    dmdserver_host: Optional[str] = None,
    dmdserver_port: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    upscale_mode: Optional[str] = None,
) -> BackendConfig:
    """Load backend configuration with CLI arguments taking precedence.

    Priority (highest to lowest):
    1. CLI arguments (non-None values passed to this function)
    2. Config file (~/.zeclock/config/zeclock.ini)
    3. Defaults (from BackendConfig dataclass)

    Args:
        config_path: Override path to config file (default: ~/.zeclock/config/zeclock.ini).
        backend: CLI --backend value.
        wifi_addr: CLI --wifi-addr value.
        device: CLI --device value.
        brightness: CLI --brightness value.
        dmdserver_host: CLI --dmdserver-host value.
        dmdserver_port: CLI --dmdserver-port value.
        width: CLI --width value or HD preset width.
        height: CLI --height value or HD preset height.

    Returns:
        A fully resolved BackendConfig instance.
    """
    # Start with defaults
    config = BackendConfig()

    # Layer 2: config file values
    path = config_path if config_path is not None else CONFIG_FILE
    file_values = _parse_config_file(path)

    if "wifi_addr" in file_values:
        config.wifi_addr = file_values["wifi_addr"]
    if "device" in file_values:
        config.device = file_values["device"]
    if "brightness" in file_values:
        config.brightness = file_values["brightness"]
    if "dmdserver_host" in file_values:
        config.dmdserver_host = file_values["dmdserver_host"]
    if "dmdserver_port" in file_values:
        config.dmdserver_port = file_values["dmdserver_port"]
    if "upscale_mode" in file_values:
        config.upscale_mode = file_values["upscale_mode"]
    if "font" in file_values:
        config.font = file_values["font"]
    if "width" in file_values:
        config.width = file_values["width"]
    if "height" in file_values:
        config.height = file_values["height"]
    if "location" in file_values:
        config.location = file_values["location"]
    if "brightness_schedule" in file_values:
        config.brightness_schedule = file_values["brightness_schedule"]
    if "mqtt" in file_values:
        config.mqtt = file_values["mqtt"]
    if "rest_api" in file_values:
        config.rest_api = file_values["rest_api"]

    # Layer 1: CLI arguments (highest precedence)
    if backend is not None:
        config.backend = backend
    if wifi_addr is not None:
        config.wifi_addr = wifi_addr
    if device is not None:
        config.device = device
    if brightness is not None:
        config.brightness = _validate_brightness(str(brightness))
    if dmdserver_host is not None:
        config.dmdserver_host = dmdserver_host
    if dmdserver_port is not None:
        config.dmdserver_port = dmdserver_port
    if width is not None:
        config.width = width
    if height is not None:
        config.height = height
    if upscale_mode is not None:
        config.upscale_mode = upscale_mode

    # Req 4.4: If both wifi_addr and device are configured, use WiFi and ignore device
    if config.wifi_addr and config.device:
        logger.info("Both wifi_addr and device configured; using WiFi, ignoring device")
        config.device = None

    return config
