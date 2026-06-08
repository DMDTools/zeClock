"""Protocol-agnostic command handler for zeClock remote control.

This module defines the shared command logic used by both MQTT and REST
interfaces. Commands are validated and executed against the ZeClock instance.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..clock import ZeClock

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Supported remote control commands."""

    SCREEN_ON = "screen_on"
    SCREEN_OFF = "screen_off"
    FORCE_PLUGIN = "force_plugin"
    DISPLAY_TEXT = "display_text"
    GET_STATUS = "get_status"
    SET_BRIGHTNESS = "set_brightness"


@dataclass
class RemoteCommand:
    """A validated remote control command."""

    type: CommandType
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandResult:
    """Result of executing a remote command."""

    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


class CommandHandler:
    """Executes remote commands against a ZeClock instance.

    This class is protocol-agnostic — it receives parsed commands and
    applies them to the clock. Both MQTT and REST use this same handler.
    """

    def __init__(self, clock: "ZeClock") -> None:
        self._clock = clock
        # Override state for screen on/off (None = no override, use scheduler)
        self._screen_override: Optional[bool] = None  # True = on, False = off
        # Text overlay state
        self._text_overlay: Optional[str] = None
        self._text_overlay_expires: float = 0.0
        # Forced plugin name (None = normal rotation)
        self._forced_plugin: Optional[str] = None
        # Brightness override (None = use scheduler, 0-15 = manual HW brightness)
        self._brightness_override: Optional[int] = None

    @property
    def screen_is_off(self) -> bool:
        """Whether the screen is currently forced off by remote command."""
        return self._screen_override is False

    @property
    def has_text_overlay(self) -> bool:
        """Whether a text overlay is currently active."""
        if self._text_overlay is None:
            return False
        if time.time() >= self._text_overlay_expires:
            self._text_overlay = None
            return False
        return True

    @property
    def text_overlay(self) -> Optional[str]:
        """Current text overlay content, or None if expired/inactive."""
        if self.has_text_overlay:
            return self._text_overlay
        return None

    @property
    def forced_plugin(self) -> Optional[str]:
        """Name of the forced plugin, or None for normal rotation."""
        return self._forced_plugin

    @property
    def brightness_override(self) -> Optional[int]:
        """Manual brightness override (0-15), or None to use scheduler."""
        return self._brightness_override

    def parse_command(self, payload: Dict[str, Any]) -> Optional[RemoteCommand]:
        """Parse a JSON command payload into a RemoteCommand.

        Expected payload formats:
            {"command": "screen_on"}
            {"command": "screen_off"}
            {"command": "force_plugin", "plugin": "weather"}
            {"command": "force_plugin", "plugin": null}  # resume rotation
            {"command": "display_text", "text": "Hello!", "duration": 10}
            {"command": "get_status"}

        Args:
            payload: Parsed JSON dict from MQTT or REST.

        Returns:
            A RemoteCommand if valid, None if the payload is malformed.
        """
        cmd_str = payload.get("command")
        if not isinstance(cmd_str, str):
            logger.warning("Invalid command payload: missing 'command' key")
            return None

        try:
            cmd_type = CommandType(cmd_str)
        except ValueError:
            logger.warning(f"Unknown command: '{cmd_str}'")
            return None

        params: Dict[str, Any] = {}

        if cmd_type == CommandType.FORCE_PLUGIN:
            plugin_name = payload.get("plugin")
            # None means "resume normal rotation"
            params["plugin"] = plugin_name

        elif cmd_type == CommandType.DISPLAY_TEXT:
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                logger.warning("display_text command missing 'text' field")
                return None
            params["text"] = text.strip()
            # Duration in seconds (default 10, max 300)
            duration = payload.get("duration", 10)
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = 10
            params["duration"] = max(1, min(300, duration))

        elif cmd_type == CommandType.SET_BRIGHTNESS:
            brightness = payload.get("brightness")
            if brightness is None:
                # None means "resume automatic scheduling"
                params["brightness"] = None
            else:
                try:
                    params["brightness"] = max(0, min(15, int(brightness)))
                except (ValueError, TypeError):
                    logger.warning(
                        "set_brightness command has invalid 'brightness' value"
                    )
                    return None

        return RemoteCommand(type=cmd_type, params=params)

    async def execute(self, command: RemoteCommand) -> CommandResult:
        """Execute a remote command against the clock.

        Args:
            command: The validated command to execute.

        Returns:
            CommandResult indicating success/failure and any response data.
        """
        if command.type == CommandType.SCREEN_ON:
            return await self._handle_screen_on()
        elif command.type == CommandType.SCREEN_OFF:
            return await self._handle_screen_off()
        elif command.type == CommandType.FORCE_PLUGIN:
            return await self._handle_force_plugin(command.params)
        elif command.type == CommandType.DISPLAY_TEXT:
            return self._handle_display_text(command.params)
        elif command.type == CommandType.GET_STATUS:
            return self._handle_get_status()
        elif command.type == CommandType.SET_BRIGHTNESS:
            return self._handle_set_brightness(command.params)

        return CommandResult(success=False, message=f"Unhandled command: {command.type}")  # type: ignore[unreachable]

    async def _handle_screen_on(self) -> CommandResult:
        """Turn the screen on (clear the off override)."""
        self._screen_override = True
        # Reset SW dimming override — let scheduler take over again
        self._clock._current_sw_dimming = 0
        logger.info("Remote: screen ON")
        return CommandResult(success=True, message="Screen turned on")

    async def _handle_screen_off(self) -> CommandResult:
        """Turn the screen off (all black)."""
        self._screen_override = False
        # Force 100% SW dimming = all black
        self._clock._current_sw_dimming = 100
        logger.info("Remote: screen OFF")
        return CommandResult(success=True, message="Screen turned off")

    async def _handle_force_plugin(self, params: Dict[str, Any]) -> CommandResult:
        """Force display of a specific plugin or resume rotation."""
        plugin_name = params.get("plugin")

        if plugin_name is None:
            # Resume normal rotation
            self._forced_plugin = None
            logger.info("Remote: resumed normal plugin rotation")
            return CommandResult(success=True, message="Resumed normal rotation")

        if not isinstance(plugin_name, str):
            return CommandResult(success=False, message="Invalid plugin name")

        # Check if plugin exists
        pm = self._clock._plugin_manager
        if pm is None:
            return CommandResult(success=False, message="Plugin system not initialized")

        if not pm.registry.has_plugin(plugin_name):
            available = [e.name for e in pm.registry.get_all_plugins()]
            return CommandResult(
                success=False,
                message=f"Plugin '{plugin_name}' not found",
                data={"available_plugins": available},
            )

        self._forced_plugin = plugin_name

        # Deactivate current plugin and force the requested one
        if pm.is_plugin_active():
            await pm.deactivate_plugin()

        entry = pm.registry.get_plugin(plugin_name)
        if entry:
            success = await pm.activate_plugin(entry.plugin)
            if success:
                from ..clock import ClockState

                self._clock._state = ClockState.PLUGIN_ACTIVE
                logger.info(f"Remote: forced plugin '{plugin_name}'")
                return CommandResult(
                    success=True, message=f"Displaying plugin '{plugin_name}'"
                )
            else:
                self._forced_plugin = None
                return CommandResult(
                    success=False, message=f"Plugin '{plugin_name}' failed to activate"
                )

        return CommandResult(success=False, message=f"Plugin '{plugin_name}' not found")

    def _handle_display_text(self, params: Dict[str, Any]) -> CommandResult:
        """Display free text on the screen for a given duration."""
        text = params["text"]
        duration = params["duration"]

        self._text_overlay = text
        self._text_overlay_expires = time.time() + duration
        # Do NOT clear forced plugin — text is a temporary overlay,
        # the forced plugin should resume after the text expires.

        logger.info(f"Remote: display text '{text}' for {duration}s")
        return CommandResult(
            success=True,
            message=f"Displaying text for {duration}s",
            data={"text": text, "duration": duration},
        )

    def _handle_set_brightness(self, params: Dict[str, Any]) -> CommandResult:
        """Set brightness manually or resume automatic scheduling.

        When brightness is set manually, the scheduler is bypassed until
        the override is cleared (by setting brightness to null/auto).
        """
        brightness = params.get("brightness")

        if brightness is None:
            # Clear override — resume automatic scheduling
            self._brightness_override = None
            logger.info("Remote: brightness override cleared, resuming scheduler")
            return CommandResult(
                success=True,
                message="Brightness control returned to scheduler",
                data={"brightness": "auto"},
            )

        self._brightness_override = int(brightness)

        # Apply HW brightness immediately if backend supports it
        clock = self._clock
        if hasattr(clock.dmd_client, "_lib") and hasattr(clock.dmd_client, "_instance"):
            if clock.dmd_client._instance:
                clock.dmd_client._lib.ZeDMD_SetBrightness(
                    clock.dmd_client._instance, self._brightness_override
                )

        # Clear SW dimming — manual brightness means full display
        clock._current_sw_dimming = 0

        logger.info(f"Remote: brightness set to {self._brightness_override}/15")
        return CommandResult(
            success=True,
            message=f"Brightness set to {self._brightness_override}/15",
            data={"brightness": self._brightness_override},
        )

    def _handle_get_status(self) -> CommandResult:
        """Return current clock status."""
        pm = self._clock._plugin_manager
        active_plugin = None
        available_plugins: List[str] = []

        if pm:
            if pm.active_plugin:
                active_plugin = pm.active_plugin.name
            available_plugins = [e.name for e in pm.registry.get_all_plugins()]

        screen_state = "off" if self.screen_is_off else "on"
        if self.has_text_overlay:
            display_mode = "text_overlay"
        elif self._forced_plugin:
            display_mode = "forced_plugin"
        else:
            display_mode = self._clock._state.value

        # Backend connection status
        backend = self._clock.dmd_client
        backend_connected = backend.connected if hasattr(backend, "connected") else False
        backend_type = type(backend).__name__

        data = {
            "screen": screen_state,
            "display_mode": display_mode,
            "active_plugin": active_plugin,
            "forced_plugin": self._forced_plugin,
            "available_plugins": available_plugins,
            "text_overlay": self._text_overlay if self.has_text_overlay else None,
            "backend": {
                "type": backend_type,
                "connected": backend_connected,
            },
            "brightness": {
                "sw_dimming": self._clock._current_sw_dimming,
                "time_only": self._clock._current_is_time_only,
                "override": self._brightness_override,
            },
            "resolution": {
                "width": self._clock.width,
                "height": self._clock.height,
            },
        }

        return CommandResult(success=True, message="ok", data=data)

    def get_state_payload(self) -> Dict[str, Any]:
        """Build a state payload for MQTT publishing.

        Returns a dict suitable for JSON serialization and publishing
        to the MQTT state topic.
        """
        result = self._handle_get_status()
        return result.data
