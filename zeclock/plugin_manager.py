"""Plugin manager - orchestrates plugin discovery, loading, scheduling, and lifecycle."""

import asyncio
import importlib
import importlib.util
import inspect
import logging
import random
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from .plugin_config import PluginConfig
from .plugin_registry import PluginRegistry
from .plugins.base import (
    ClockPlugin,
    PluginContext,
    PluginNotConfiguredError,
    validate_frame_delay_ms,
    validate_plugin_name,
)
from .plugins.helpers import PluginHelpers

logger = logging.getLogger(__name__)


class PluginManager:
    """Discovers, loads, schedules, and drives plugins.

    Orchestrates the full plugin lifecycle: discovery from built-in and
    user directories, validation, registration, scheduling via weighted
    random selection, and frame rendering with error recovery.
    """

    def __init__(
        self,
        width: int,
        height: int,
        config_path: Optional[Path] = None,
        resources_path: Optional[Path] = None,
        upscale_mode: str = "epx",
        font: str = "STANDARD",
    ):
        """Initialize the PluginManager.

        Args:
            width: Display width in pixels (e.g. 128 or 256).
            height: Display height in pixels (e.g. 32 or 64).
            config_path: Optional path to plugins.yaml config file.
            resources_path: Optional path to resources directory (for PluginHelpers).
            upscale_mode: Upscaling algorithm for HD mode ("nearest", "epx", or "hq2x").
            font: Global font name (without .fnt extension, e.g. "STANDARD").
        """
        self.width = width
        self.height = height
        self.upscale_mode = upscale_mode
        self.font_name = font
        self.registry = PluginRegistry()
        self.config = PluginConfig(config_path)
        self.active_plugin: Optional[ClockPlugin] = None
        self.consecutive_errors: int = 0
        self.plugin_start_time: float = 0.0
        self.last_good_frame: Optional[Image.Image] = None
        self.init_timeout: float = 10.0  # seconds, configurable for testing

        # Set up resources path for PluginHelpers
        if resources_path is None:
            from .paths import get_resources_dir

            resources_path = get_resources_dir()
        self._resources_path = resources_path

        # Create the PluginHelpers instance to inject into plugins
        # Use bundled fonts directory for font loading
        from .resources.paths import get_fonts_dir

        fonts_parent = get_fonts_dir().parent
        self._helpers = PluginHelpers(
            width, height, fonts_parent, upscale_mode=upscale_mode, default_font=font
        )

        # Track last selected plugin to avoid consecutive repeats
        self._last_selected_plugin: Optional[ClockPlugin] = None

    async def discover_and_load(self) -> None:
        """Scan plugin directories, import modules, validate and register plugins.

        Loads built-in plugins first (from zeclock/plugins/ package), then
        user plugins (from ~/.zeclock/plugins/). User plugins with the same
        name as a built-in plugin will override the built-in.

        Import errors are logged at WARNING level and the file is skipped.
        Invalid plugin names are logged at WARNING level and the plugin is skipped.
        """
        # Load configuration
        self.config.load()

        # Load built-in plugins first
        builtin_dir = Path(__file__).parent / "plugins"
        self._load_plugins_from_directory(builtin_dir, source="builtin")

        # Ensure user plugin directory exists
        from .paths import get_plugins_dir

        user_plugin_dir = get_plugins_dir()
        if not user_plugin_dir.exists():
            try:
                user_plugin_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created user plugin directory: {user_plugin_dir}")
            except OSError as e:
                logger.warning(f"Could not create user plugin directory: {e}")

        # Load user plugins (can override built-in)
        if user_plugin_dir.exists():
            self._load_plugins_from_directory(user_plugin_dir, source="user")

        # Apply configured frequencies to registered plugins
        self._apply_config_frequencies()

    def _load_plugins_from_directory(self, directory: Path, source: str) -> None:
        """Scan a directory for plugin files and load valid plugins.

        Args:
            directory: Path to the directory to scan.
            source: "builtin" or "user" indicating the plugin origin.
        """
        if not directory.exists() or not directory.is_dir():
            return

        for filepath in sorted(directory.glob("*.py")):
            # Skip __init__.py, base.py, helpers.py (infrastructure files)
            if filepath.name.startswith("_") or filepath.name in (
                "base.py",
                "helpers.py",
            ):
                continue

            if source == "builtin":
                self._load_builtin_plugin(filepath)
            else:
                self._load_plugin_from_file(filepath, source)

    def _load_builtin_plugin(self, filepath: Path) -> None:
        """Load a built-in plugin using its package-qualified module name.

        Built-in plugins live inside the zeclock.plugins package and use
        relative imports, so they must be imported via their dotted module
        path rather than file-based loading.

        Args:
            filepath: Path to the .py file inside zeclock/plugins/.
        """
        module_name = f"zeclock.plugins.{filepath.stem}"

        try:
            # Use importlib.import_module with the package context to handle
            # relative imports correctly even in installed environments
            if module_name in sys.modules:
                module = sys.modules[module_name]
            else:
                module = importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"Failed to import built-in plugin {module_name}: {e}")
            return

        # Find ClockPlugin subclasses in the module
        plugin_classes = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ClockPlugin)
                and obj is not ClockPlugin
                and not inspect.isabstract(obj)
            ):
                plugin_classes.append(obj)

        for plugin_class in plugin_classes:
            self._register_plugin_class(plugin_class, filepath, "builtin")

    def _load_plugin_from_file(self, filepath: Path, source: str) -> None:
        """Attempt to load a plugin from a Python file.

        Args:
            filepath: Path to the .py file.
            source: "builtin" or "user".
        """
        module_name = f"zeclock_plugin_{source}_{filepath.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not create module spec for {filepath}")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning(f"Failed to import plugin file {filepath}: {e}")
            return

        # Find ClockPlugin subclasses in the module
        plugin_classes = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ClockPlugin)
                and obj is not ClockPlugin
                and not inspect.isabstract(obj)
            ):
                plugin_classes.append(obj)

        for plugin_class in plugin_classes:
            self._register_plugin_class(plugin_class, filepath, source)

    def _register_plugin_class(
        self, plugin_class: type, filepath: Path, source: str
    ) -> None:
        """Instantiate and register a plugin class after validation.

        Args:
            plugin_class: The ClockPlugin subclass to instantiate.
            filepath: Path to the source file (for logging).
            source: "builtin" or "user".
        """
        try:
            plugin = plugin_class()
        except Exception as e:
            logger.warning(
                f"Failed to instantiate plugin class {plugin_class.__name__} "
                f"from {filepath}: {e}"
            )
            return

        # Validate plugin name
        try:
            name = plugin.name
        except Exception as e:
            logger.warning(
                f"Plugin class {plugin_class.__name__} from {filepath} "
                f"raised error accessing name: {e}"
            )
            return

        if not validate_plugin_name(name):
            logger.warning(
                f"Plugin from {filepath} has invalid name '{name}' "
                f"(must be 1-64 lowercase alphanumeric/hyphens/underscores), skipping"
            )
            return

        # Validate frame_delay_ms
        try:
            delay = plugin.frame_delay_ms
            if not validate_frame_delay_ms(delay):
                logger.warning(
                    f"Plugin '{name}' from {filepath} has invalid frame_delay_ms={delay} "
                    f"(must be 20-5000), skipping"
                )
                return
        except Exception as e:
            logger.warning(
                f"Plugin '{name}' from {filepath} raised error accessing "
                f"frame_delay_ms: {e}"
            )
            return

        # Register or override
        if self.registry.has_plugin(name):
            if source == "user":
                # User plugins override built-in plugins
                self.registry.override_plugin(name, plugin, source)
                logger.info(
                    f"User plugin '{name}' from {filepath} overrides built-in plugin"
                )
            else:
                logger.warning(
                    f"Duplicate built-in plugin name '{name}' from {filepath}, skipping"
                )
        else:
            self.registry.register(plugin, source)

    def _apply_config_frequencies(self) -> None:
        """Apply frequency values from configuration to registered plugins."""
        for entry in self.config.plugin_entries:
            name = entry["name"]
            frequency = entry["frequency"]
            if self.registry.has_plugin(name):
                self.registry.set_frequency(name, frequency)
            else:
                logger.warning(
                    f"Plugin '{name}' referenced in config but not found in registry"
                )

    def get_plugin_config_with_helpers(self, plugin_name: str) -> dict:
        """Get plugin config with the PluginHelpers instance injected.

        Args:
            plugin_name: The plugin name to get config for.

        Returns:
            Config dict with "_helpers", "_upscale_mode", "_context" keys.
        """
        config = self.config.get_plugin_config(plugin_name)
        # Snapshot user settings before adding infrastructure keys
        user_settings = dict(config)

        # Inject current clock color when no explicit color is configured
        if "color" not in config:
            color = self._get_default_plugin_color()
            if color:
                config["_current_color"] = color

        config["_helpers"] = self._helpers
        config["_upscale_mode"] = self.upscale_mode
        config["_font"] = self.font_name
        config["_clock_display_seconds"] = self.config.clock_display_seconds
        config["_context"] = PluginContext(
            helpers=self._helpers,
            upscale_mode=self.upscale_mode,
            font=self.font_name,
            settings=user_settings,
        )
        return config

    def _get_default_plugin_color(self) -> Optional[Tuple[int, int, int]]:
        """Get the current color from the default plugin (clock).

        Reads _current_color from the default plugin instance if available.

        Returns:
            RGB tuple or None if unavailable.
        """
        plugin = self.get_default_plugin()
        if plugin and hasattr(plugin, "_current_color"):
            return plugin._current_color
        return None

    def _validate_config_schema(self, plugin: ClockPlugin) -> "Optional[str]":
        """Validate plugin config against its schema.

        Checks that all required fields (with no default) are present
        in the user settings.

        Args:
            plugin: The plugin to validate config for.

        Returns:
            The name of the first missing required field, or None if valid.
        """
        schema = plugin.config_schema
        if not schema:
            return None
        user_settings = self.config.get_plugin_config(plugin.name)
        for field in schema:
            if field.required and field.default is None:
                if field.name not in user_settings:
                    return field.name
        return None

    def select_next_plugin(self) -> Optional[ClockPlugin]:
        """Select next plugin using weighted random based on frequencies.

        Uses the normalized frequencies from the registry to perform
        weighted random selection among active (non-failed) plugins.
        Avoids selecting the same plugin twice in a row by excluding
        the last selected plugin from candidates (unless it's the only
        one available or has 100% of the total weight).

        The default plugin (configured via default_plugin in plugins.yaml)
        is excluded from rotation since it is shown between other plugins.

        Returns:
            A ClockPlugin instance, or None if no plugins are available.
        """
        normalized = self.registry.get_normalized_frequencies()
        if not normalized:
            return None

        # Exclude the default plugin from rotation candidates
        default_name = self.config.default_plugin
        filtered = [
            (plugin, freq) for plugin, freq in normalized if plugin.name != default_name
        ]
        if not filtered:
            return None

        plugins = [plugin for plugin, _freq in filtered]
        weights = [freq for _plugin, freq in filtered]

        # If more than one candidate and last plugin isn't at 100%, exclude it
        if (
            len(plugins) > 1
            and self._last_selected_plugin is not None
            and self._last_selected_plugin in plugins
        ):
            idx = plugins.index(self._last_selected_plugin)
            if weights[idx] < 100.0:
                # Remove last plugin and re-select from the rest
                remaining_plugins = plugins[:idx] + plugins[idx + 1 :]
                remaining_weights = weights[:idx] + weights[idx + 1 :]
                # Guard against all-zero remaining weights
                if sum(remaining_weights) > 0:
                    selected = random.choices(
                        remaining_plugins, weights=remaining_weights, k=1
                    )[0]
                    self._last_selected_plugin = selected
                    return selected

        selected = random.choices(plugins, weights=weights, k=1)[0]
        self._last_selected_plugin = selected
        return selected

    async def activate_plugin(self, plugin: ClockPlugin) -> bool:
        """Initialize plugin with its config. Returns False if init fails.

        Calls the plugin's initialize() method with a 10-second timeout.
        If initialization raises an exception or times out, the plugin is
        marked as failed in the registry.

        Args:
            plugin: The plugin to activate.

        Returns:
            True if activation succeeded, False otherwise.
        """
        config = self.get_plugin_config_with_helpers(plugin.name)

        # Validate required config fields from schema before calling initialize
        missing_field = self._validate_config_schema(plugin)
        if missing_field:
            logger.info(
                f"Plugin '{plugin.name}' missing required field "
                f"'{missing_field}', marking as unconfigured"
            )
            plugin._unconfigured = True
            self.active_plugin = plugin
            self.consecutive_errors = 0
            self.plugin_start_time = time.time()
            self.last_good_frame = None
            return True

        try:
            await asyncio.wait_for(plugin.initialize(config), timeout=self.init_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Plugin '{plugin.name}' initialization timed out (>{self.init_timeout}s), marking failed"
            )
            self.registry.mark_failed(plugin.name)
            return False
        except PluginNotConfiguredError:
            logger.info(
                f"Plugin '{plugin.name}' is not configured, marking as unconfigured"
            )
            plugin._unconfigured = True
            self.active_plugin = plugin
            self.consecutive_errors = 0
            self.plugin_start_time = time.time()
            self.last_good_frame = None
            return True
        except Exception as e:
            logger.error(f"Plugin '{plugin.name}' initialization failed: {e}")
            self.registry.mark_failed(plugin.name)
            return False

        self.active_plugin = plugin
        self.consecutive_errors = 0
        self.plugin_start_time = time.time()
        self.last_good_frame = None
        return True

    async def reconfigure_plugin(self, plugin_name: str) -> bool:
        """Reconfigure a plugin with fresh settings from plugins.yaml.

        Reloads config from disk and calls the plugin's reconfigure() method.
        If the plugin is currently active, it remains active with new config.

        Args:
            plugin_name: Name of the plugin to reconfigure.

        Returns:
            True if reconfiguration succeeded, False otherwise.
        """
        entry = self.registry.get_plugin(plugin_name)
        if not entry:
            logger.warning(f"Cannot reconfigure unknown plugin '{plugin_name}'")
            return False

        # Reload config from disk
        self.config.reload()
        config = self.get_plugin_config_with_helpers(plugin_name)

        # Validate required config fields from schema before reconfiguring
        missing_field = self._validate_config_schema(entry.plugin)
        if missing_field:
            logger.info(
                f"Plugin '{plugin_name}' missing required field "
                f"'{missing_field}' after config reload, marking as unconfigured"
            )
            entry.plugin._unconfigured = True
            return True

        try:
            await asyncio.wait_for(
                entry.plugin.reconfigure(config), timeout=self.init_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Plugin '{plugin_name}' reconfigure timed out, marking failed"
            )
            self.registry.mark_failed(plugin_name)
            return False
        except PluginNotConfiguredError:
            logger.info(f"Plugin '{plugin_name}' not configured after reconfigure")
            entry.plugin._unconfigured = True
            return True
        except Exception as e:
            logger.error(f"Plugin '{plugin_name}' reconfigure failed: {e}")
            return False

        # Clear unconfigured flag on success
        entry.plugin._unconfigured = False
        logger.info(f"Plugin '{plugin_name}' reconfigured successfully")
        return True

    async def get_frame(self) -> Optional[Image.Image]:
        """Get next frame from active plugin with timeout and error handling.

        Calls the active plugin's render_frame() with a 2-second timeout.
        On success, stores the frame as last_good_frame and resets the
        consecutive error counter. On failure (exception or timeout),
        increments the error counter and returns the last good frame.

        If render_frame returns None, the plugin signals completion.

        Returns:
            A PIL Image frame, or None if the plugin signals completion.
        """
        if self.active_plugin is None:
            return None

        if getattr(self.active_plugin, "_unconfigured", False):
            return self._render_configure_message(self.active_plugin.name)

        try:
            frame = await asyncio.wait_for(
                self.active_plugin.render_frame(self.width, self.height),
                timeout=2.0,
            )
        except asyncio.TimeoutError:
            self.consecutive_errors += 1
            logger.warning(
                f"Plugin '{self.active_plugin.name}' render_frame timed out "
                f"(>2s), consecutive errors: {self.consecutive_errors}"
            )
            return self.last_good_frame
        except Exception as e:
            self.consecutive_errors += 1
            logger.warning(
                f"Plugin '{self.active_plugin.name}' render_frame error: {e}, "
                f"consecutive errors: {self.consecutive_errors}"
            )
            return self.last_good_frame

        # Plugin signals completion by returning None
        if frame is None:
            return None

        # Success: store frame and reset error counter
        self.last_good_frame = frame
        self.consecutive_errors = 0
        return frame

    def _render_configure_message(self, name: str) -> Image.Image:
        """Render a 'please configure' message for an unconfigured plugin.

        Displays 'PLEASE CONFIGURE' on line 1, '<NAME> PLUGIN' on line 2,
        both centered using the MENU bitmap font.

        Args:
            name: The plugin's display name.

        Returns:
            PIL Image in RGB mode with the configure message.
        """
        truncated_name = name[:12].upper()
        text = f"PLEASE CONFIGURE\n{truncated_name} PLUGIN"
        return self._helpers.render_text(text, centered=True, font_name="MENU")

    def should_deactivate(self) -> bool:
        """Check if the active plugin should be deactivated.

        Returns True if the maximum duration (30 seconds) has been exceeded
        or if there have been 5 or more consecutive render errors.

        Returns:
            True if the plugin should be deactivated, False otherwise.
        """
        if self.active_plugin is None:
            return False

        # Check max duration (30 seconds)
        if time.time() - self.plugin_start_time >= 30:
            return True

        # Check consecutive errors threshold
        if self.consecutive_errors >= 5:
            return True

        return False

    async def deactivate_plugin(self) -> None:
        """Cleanup active plugin and reset state.

        Calls the active plugin's cleanup() method, then resets all
        plugin-related state (active_plugin, consecutive_errors, last_good_frame).
        """
        if self.active_plugin is not None:
            try:
                await self.active_plugin.cleanup()
            except Exception as e:
                logger.warning(f"Plugin '{self.active_plugin.name}' cleanup error: {e}")

            self.active_plugin = None
            self.consecutive_errors = 0
            self.last_good_frame = None

    def is_plugin_active(self) -> bool:
        """Check if a plugin is currently rendering.

        Returns:
            True if a plugin is currently active, False otherwise.
        """
        return self.active_plugin is not None

    def get_default_plugin(self) -> Optional[ClockPlugin]:
        """Get the configured default plugin instance.

        The default plugin is the one shown between other plugin rotations.
        It is identified by the ``default_plugin`` field in plugins.yaml.

        Returns:
            The default plugin instance, or None if not found in registry.
        """
        default_name = self.config.default_plugin
        entry = self.registry.get_plugin(default_name)
        if entry is None:
            return None
        return entry.plugin

    async def init_default_plugin(self) -> bool:
        """Initialize the default plugin for rendering.

        Calls activate logic (initialize with config) on the default plugin
        so it's ready to render frames immediately.

        Returns:
            True if the default plugin was initialized successfully.
        """
        plugin = self.get_default_plugin()
        if plugin is None:
            logger.warning(
                "Default plugin '%s' not found in registry",
                self.config.default_plugin,
            )
            return False

        config = self.get_plugin_config_with_helpers(plugin.name)
        try:
            await plugin.initialize(config)
            return True
        except Exception as e:
            logger.warning(
                "Default plugin '%s' initialization failed: %s", plugin.name, e
            )
            return False

    async def render_default_plugin_frame(self) -> Optional[Image.Image]:
        """Render a frame from the default plugin.

        Returns:
            A PIL Image frame, or None if the plugin signals page-cycle
            completion (caller should re-init and try again).
        """
        plugin = self.get_default_plugin()
        if plugin is None:
            return None
        try:
            return await plugin.render_frame(self.width, self.height)
        except Exception as e:
            logger.warning("Default plugin render error: %s", e)
            return None

    def get_default_plugin_frame_delay(self) -> float:
        """Get the frame delay for the default plugin.

        Returns:
            Frame delay in seconds, or 0.5s fallback.
        """
        plugin = self.get_default_plugin()
        if plugin is not None:
            return plugin.frame_delay_ms / 1000.0
        return 0.5
