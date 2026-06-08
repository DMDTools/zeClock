"""Plugin configuration loading and validation from YAML."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Validation bounds
CLOCK_DISPLAY_SECONDS_MIN = 1
CLOCK_DISPLAY_SECONDS_MAX = 300
CLOCK_DISPLAY_SECONDS_DEFAULT = 5
FREQUENCY_MIN = 0
FREQUENCY_MAX = 100


def clamp(value: int, min_val: int, max_val: int) -> int:
    """Clamp an integer value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


class PluginConfig:
    """Reads and validates plugins.yaml configuration.

    Handles loading from disk, creating defaults, clamping out-of-range
    values, and providing plugin-specific settings.
    """

    DEFAULT_CONFIG = {
        "clock_display_seconds": CLOCK_DISPLAY_SECONDS_DEFAULT,
        "plugins": [{"name": "pinball", "frequency": 100, "settings": {}}],
    }

    def __init__(self, config_path: Optional[Path] = None):
        from .paths import get_config_dir

        self.path = config_path or get_config_dir() / "plugins.yaml"
        self.clock_display_seconds: int = CLOCK_DISPLAY_SECONDS_DEFAULT
        self.plugin_entries: List[Dict[str, Any]] = []
        self._raw: Dict[str, Any] = {}

    def load(self) -> None:
        """Load and validate YAML config, creating defaults if missing."""
        try:
            import yaml
        except ImportError:
            logger.warning("pyyaml not installed, using default plugin configuration")
            self._apply_defaults()
            return

        if not self.path.exists():
            self._create_default_config()
            self._apply_defaults()
            return

        try:
            with open(self.path, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to parse {self.path}: {e}")
            self._apply_defaults()
            return

        if not isinstance(data, dict):
            logger.error(f"Invalid config format in {self.path}, using defaults")
            self._apply_defaults()
            return

        self._raw = data
        self._parse_config(data)

    def _parse_config(self, data: Dict[str, Any]) -> None:
        """Parse and validate configuration data."""
        # clock_display_seconds
        raw_seconds = data.get("clock_display_seconds", CLOCK_DISPLAY_SECONDS_DEFAULT)
        if isinstance(raw_seconds, int):
            if (
                raw_seconds < CLOCK_DISPLAY_SECONDS_MIN
                or raw_seconds > CLOCK_DISPLAY_SECONDS_MAX
            ):
                logger.warning(
                    f"clock_display_seconds={raw_seconds} out of range "
                    f"[{CLOCK_DISPLAY_SECONDS_MIN}, {CLOCK_DISPLAY_SECONDS_MAX}], clamping"
                )
            self.clock_display_seconds = clamp(
                raw_seconds, CLOCK_DISPLAY_SECONDS_MIN, CLOCK_DISPLAY_SECONDS_MAX
            )
        else:
            self.clock_display_seconds = CLOCK_DISPLAY_SECONDS_DEFAULT

        # plugins list
        raw_plugins = data.get("plugins", [])
        if not isinstance(raw_plugins, list):
            logger.warning("'plugins' is not a list, using defaults")
            self._apply_defaults()
            return

        self.plugin_entries = []
        for entry in raw_plugins:
            if not isinstance(entry, dict) or "name" not in entry:
                logger.warning(f"Skipping invalid plugin entry: {entry}")
                continue

            name = entry["name"]
            raw_freq = entry.get("frequency", 100)

            if not isinstance(raw_freq, int):
                raw_freq = 100

            if raw_freq < FREQUENCY_MIN or raw_freq > FREQUENCY_MAX:
                logger.warning(
                    f"Plugin '{name}' frequency={raw_freq} out of range "
                    f"[{FREQUENCY_MIN}, {FREQUENCY_MAX}], clamping"
                )

            frequency = clamp(raw_freq, FREQUENCY_MIN, FREQUENCY_MAX)
            settings = entry.get("settings", {})
            if not isinstance(settings, dict):
                settings = {}

            self.plugin_entries.append(
                {
                    "name": name,
                    "frequency": frequency,
                    "settings": settings,
                }
            )

    def _apply_defaults(self) -> None:
        """Apply default configuration."""
        self.clock_display_seconds = CLOCK_DISPLAY_SECONDS_DEFAULT
        self.plugin_entries = [{"name": "pinball", "frequency": 100, "settings": {}}]

    def _create_default_config(self) -> None:
        """Create a default plugins.yaml file on disk."""
        try:
            import yaml

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                yaml.dump(
                    self.DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False
                )
            logger.info(f"Created default plugin config at {self.path}")
        except Exception as e:
            logger.warning(f"Could not create default config: {e}")

    def get_plugin_config(self, plugin_name: str) -> dict:
        """Get plugin-specific settings map.

        Args:
            plugin_name: The plugin name to look up.

        Returns:
            The settings dict for the plugin, or empty dict if not found.
        """
        for entry in self.plugin_entries:
            if entry["name"] == plugin_name:
                return entry.get("settings", {})
        return {}

    def get_frequency(self, plugin_name: str) -> int:
        """Get configured frequency for a plugin (0-100).

        Args:
            plugin_name: The plugin name to look up.

        Returns:
            The frequency value, or 0 if not found.
        """
        for entry in self.plugin_entries:
            if entry["name"] == plugin_name:
                return entry["frequency"]
        return 0
