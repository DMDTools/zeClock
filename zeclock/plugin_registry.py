"""Plugin registry for tracking discovered plugins and their states."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .plugins.base import ClockPlugin

logger = logging.getLogger(__name__)


@dataclass
class PluginEntry:
    """Runtime state for a registered plugin."""

    plugin: ClockPlugin
    name: str
    source: str  # "builtin" or "user"
    state: str = "available"  # "available" | "active" | "failed"
    frequency: int = 100  # 0-100
    error_count: int = 0
    last_error: Optional[str] = None


class PluginRegistry:
    """Maintains the collection of discovered plugins and their states.

    Handles registration, override logic, failure tracking, and
    frequency normalization for scheduling.
    """

    def __init__(self):
        self._plugins: Dict[str, PluginEntry] = {}

    def register(self, plugin: ClockPlugin, source: str, frequency: int = 100) -> None:
        """Register a plugin in the registry.

        Args:
            plugin: The plugin instance.
            source: "builtin" or "user".
            frequency: Configured frequency (0-100).
        """
        name = plugin.name
        self._plugins[name] = PluginEntry(
            plugin=plugin,
            name=name,
            source=source,
            state="available",
            frequency=frequency,
        )

    def override_plugin(self, name: str, plugin: ClockPlugin, source: str) -> None:
        """Override an existing plugin with a new instance.

        Args:
            name: The plugin name to override.
            plugin: The new plugin instance.
            source: Source of the new plugin ("user").
        """
        if name in self._plugins:
            old_entry = self._plugins[name]
            self._plugins[name] = PluginEntry(
                plugin=plugin,
                name=name,
                source=source,
                state="available",
                frequency=old_entry.frequency,
            )
            logger.info(f"Plugin '{name}' overridden by {source} plugin")
        else:
            self.register(plugin, source)

    def get_plugin(self, name: str) -> Optional[PluginEntry]:
        """Get a plugin entry by name."""
        return self._plugins.get(name)

    def get_all_plugins(self) -> List[PluginEntry]:
        """Get all registered plugins."""
        return list(self._plugins.values())

    def get_active_plugins(self) -> List[PluginEntry]:
        """Get plugins that are available for scheduling (not failed)."""
        return [e for e in self._plugins.values() if e.state != "failed"]

    def mark_failed(self, name: str, error: str = "") -> None:
        """Mark a plugin as failed, excluding it from scheduling.

        Args:
            name: The plugin name.
            error: Description of the failure.
        """
        if name in self._plugins:
            self._plugins[name].state = "failed"
            self._plugins[name].last_error = error
            logger.warning(f"Plugin '{name}' marked as failed: {error}")

    def set_frequency(self, name: str, frequency: int) -> None:
        """Set the frequency for a plugin.

        Args:
            name: The plugin name.
            frequency: Frequency value (0-100).
        """
        if name in self._plugins:
            self._plugins[name].frequency = frequency

    def get_normalized_frequencies(self) -> List[Tuple[ClockPlugin, float]]:
        """Get active plugins with normalized frequency weights.

        Returns a list of (plugin, probability) tuples where probabilities
        sum to 1.0. If only one plugin is active, it gets probability 1.0.

        Returns:
            List of (plugin, normalized_weight) tuples.
        """
        active = self.get_active_plugins()
        if not active:
            return []

        total = sum(e.frequency for e in active)
        if total == 0:
            # Equal distribution if all frequencies are 0
            weight = 1.0 / len(active)
            return [(e.plugin, weight) for e in active]

        return [(e.plugin, e.frequency / total) for e in active]

    def has_plugin(self, name: str) -> bool:
        """Check if a plugin name is registered."""
        return name in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)
