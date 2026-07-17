"""
Horloge principale zeClock avec support multi-backend DMD
"""

import asyncio
import enum
import logging
import time
from pathlib import Path
from typing import Any, Optional

from PIL import Image

from .backends import DMDBackend, create_backend
from .brightness_scheduler import (
    BrightnessScheduler,
    apply_sw_dimming,
)
from .colors import COLOR_LIST, COLOR_MAP
from .overlay import colorize_grayscale
from .paths import get_config_dir
from .plugin_manager import PluginManager
from .readers import load_font

logger = logging.getLogger(__name__)

# Transliteration table: accented/special chars → ASCII equivalents
_TRANSLITERATE_MAP = str.maketrans(
    {
        "à": "a",
        "á": "a",
        "â": "a",
        "ã": "a",
        "ä": "a",
        "å": "a",
        "ç": "c",
        "è": "e",
        "é": "e",
        "ê": "e",
        "ë": "e",
        "ì": "i",
        "í": "i",
        "î": "i",
        "ï": "i",
        "ð": "d",
        "ñ": "n",
        "ò": "o",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ö": "o",
        "ù": "u",
        "ú": "u",
        "û": "u",
        "ü": "u",
        "ý": "y",
        "ÿ": "y",
        "ß": "ss",
        "À": "A",
        "Á": "A",
        "Â": "A",
        "Ã": "A",
        "Ä": "A",
        "Å": "A",
        "Ç": "C",
        "È": "E",
        "É": "E",
        "Ê": "E",
        "Ë": "E",
        "Ì": "I",
        "Í": "I",
        "Î": "I",
        "Ï": "I",
        "Ð": "D",
        "Ñ": "N",
        "Ò": "O",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ö": "O",
        "Ù": "U",
        "Ú": "U",
        "Û": "U",
        "Ü": "U",
        "Ý": "Y",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
    }
)


def _transliterate(text: str) -> str:
    """Replace accented and special characters with ASCII equivalents.

    Characters not in the translation table and not printable ASCII
    are stripped.
    """
    result = text.translate(_TRANSLITERATE_MAP)
    # Strip any remaining non-ASCII characters
    return "".join(ch for ch in result if 32 <= ord(ch) <= 126)


class ClockState(enum.Enum):
    """State machine states for the clock display."""

    CLOCK_ONLY = "clock_only"
    PLUGIN_SELECT = "plugin_select"
    PLUGIN_ACTIVE = "plugin_active"


def _persist_wifi_addr(ip: str) -> None:
    """Save discovered WiFi address to zeclock.ini so it's used on next boot."""
    import configparser

    config_path = get_config_dir() / "zeclock.ini"
    parser = configparser.RawConfigParser()
    if config_path.exists():
        parser.read(str(config_path))
    if not parser.has_section("zedmd"):
        parser.add_section("zedmd")
    parser.set("zedmd", "wifi_addr", ip)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        parser.write(f)
    logger.info("Persisted wifi_addr=%s to %s", ip, config_path)


class ZeClock:
    """Horloge animée avec affichage sur ZeDMD via DMDServer"""

    def __init__(
        self,
        width: int = 128,
        height: int = 32,
        fps: int = 25,
        backend: Optional[DMDBackend] = None,
        dmdserver_host: str = "localhost",
        dmdserver_port: int = 6789,
        test_mode: bool = False,
        color: str = "orange",
        plugin_config_path: Optional[Path] = None,
        plugins_override: Optional[str] = None,
        upscale_mode: str = "epx",
        font: str = "STANDARD",
        brightness_scheduler: Optional[BrightnessScheduler] = None,
        mqtt_config: Optional[Any] = None,
        rest_config: Optional[Any] = None,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.running = True
        self.upscale_mode = upscale_mode
        self.font_name = font

        # Color configuration
        self.color_mode = color
        if color == "auto":
            self.color = COLOR_LIST[0]
            self.last_color_change = time.time()
        else:
            self.color = COLOR_MAP.get(color, COLOR_LIST[0])

        # DMD backend (dependency injection with backward compatibility)
        if backend is not None:
            self.dmd_client = backend
        else:
            # Backward compatibility: create DMDServerBackend from host/port
            from .backends.dmdserver import DMDServerBackend

            self.dmd_client = DMDServerBackend(host=dmdserver_host, port=dmdserver_port)

        # Plugin system state
        self._state = ClockState.CLOCK_ONLY
        self._clock_only_start = time.time()
        self._plugin_config_path = plugin_config_path
        self._plugins_override = plugins_override
        self._plugin_manager: Optional[PluginManager] = None

        # Clock caching
        self.cached_clock_frame: Optional[Image.Image] = None
        self.cached_clock_rgb: Optional[Image.Image] = None
        self.last_clock_time = ""
        self.last_clock_color: Optional[tuple] = None

        # Reconnection state
        self._reconnect_logged = False
        self._reconnect_delay = 2.0

        # Brightness scheduler
        self._brightness_scheduler = brightness_scheduler
        self._last_brightness_check = 0.0
        self._current_sw_dimming = 0
        self._current_is_time_only = False

        # Load font — prefer HD variant for HD displays
        self.dotclk_font = None
        from .resources.paths import get_fonts_dir

        fonts_dir = get_fonts_dir()
        hd_font_path = fonts_dir / f"{self.font_name}_HD.fnt"
        sd_font_path = fonts_dir / f"{self.font_name}.fnt"

        # Use HD font if display is HD and the font file exists
        if self.width >= 256 and self.height >= 64 and hd_font_path.exists():
            font_path = hd_font_path
        else:
            font_path = sd_font_path

        if font_path.exists():
            try:
                self.dotclk_font = load_font(font_path)
                print(
                    f"✅ Loaded font: {self.dotclk_font.name} (upscale={self.upscale_mode})"
                )
            except Exception as e:
                print(f"⚠️ Failed to load font: {e}")
        else:
            print("❌ No font found")

        # Remote control
        self._mqtt_config = mqtt_config
        self._rest_config = rest_config
        self._command_handler: Optional[Any] = None
        self._mqtt_remote: Optional[Any] = None
        self._rest_remote: Optional[Any] = None
        self._text_overlay_font: Optional[Any] = None

    async def run(self) -> None:
        """Main asynchronous loop with plugin-driven state machine."""
        # Initialize remote control EARLY so the web UI is available
        # even while waiting for DMD connection
        await self._init_remote_control()

        # Initialize discovery state (shared with REST API for live UI updates)
        from .discovery import DiscoveryState, discover_zedmd

        self._discovery_state = DiscoveryState()

        # Initial connection attempt (USB or configured WiFi)
        if not self.dmd_client.connect():
            # If no WiFi addr configured, try auto-discovery
            if (
                hasattr(self.dmd_client, "_wifi_addr")
                and not self.dmd_client._wifi_addr
            ):
                print("⚠️ ZeDMD not found via USB — starting network discovery...")
                self._discovery_state.update(
                    "scanning", "ZeDMD not found via USB, starting network discovery..."
                )

                # Run discovery in a thread to not block the event loop
                result = await asyncio.get_event_loop().run_in_executor(
                    None, discover_zedmd, self._discovery_state
                )

                if result:
                    # Found via discovery — reconfigure the backend with the discovered IP
                    print(
                        f"✅ ZeDMD discovered at {result.ip}:{result.port} (v{result.version})"
                    )
                    self.dmd_client._wifi_addr = result.ip
                    if self.dmd_client.connect():
                        print("✅ ZeDMD connected via WiFi")
                        _persist_wifi_addr(result.ip)
                    else:
                        print(
                            "⚠️ Discovery found ZeDMD but connection failed — retrying..."
                        )
                else:
                    print("⚠️ ZeDMD not found on network — waiting for device...")

            if not self.dmd_client.connected:
                print(
                    "👉 Check your backend configuration (--backend, --wifi-addr, --device)"
                )
                self._discovery_state.update("waiting", "Waiting for ZeDMD...")
                delay = 3.0
                attempt = 0
                while self.running:
                    await asyncio.sleep(delay)
                    attempt += 1

                    # Alternate: odd attempts try USB, even attempts try mDNS
                    if attempt % 2 == 1:
                        # Try USB
                        if self.dmd_client.connect():
                            print("✅ DMD backend connected (USB)")
                            self._discovery_state.update("found", "ZeDMD connected")
                            break
                    else:
                        # Try mDNS discovery
                        if not self.dmd_client._wifi_addr:  # type: ignore[attr-defined]
                            self._discovery_state.update(
                                "scanning", "Retrying network discovery..."
                            )
                            result = await asyncio.get_event_loop().run_in_executor(
                                None, discover_zedmd, self._discovery_state
                            )
                            if result:
                                self.dmd_client._wifi_addr = result.ip  # type: ignore[attr-defined]
                                if self.dmd_client.connect():
                                    print(
                                        f"✅ ZeDMD discovered and connected at {result.ip}"
                                    )
                                    self._discovery_state.update(
                                        "found", f"ZeDMD connected at {result.ip}"
                                    )
                                    _persist_wifi_addr(result.ip)
                                    break
                        else:
                            # WiFi addr known but connection failed — retry connect
                            if self.dmd_client.connect():
                                print("✅ DMD backend connected (WiFi)")
                                self._discovery_state.update(
                                    "found", "ZeDMD connected"
                                )
                                break

                    delay = min(delay * 1.3, 10.0)
                    logger.info("DMD still unavailable — next retry in %.0fs", delay)
                if not self.running:
                    return
        else:
            self._discovery_state.update("found", "ZeDMD connected")

        # After connection, adapt to detected display resolution (ZeDMD HD auto-detect)
        if hasattr(self.dmd_client, "width") and hasattr(self.dmd_client, "height"):
            detected_w = self.dmd_client.width
            detected_h = self.dmd_client.height
            if detected_w > 0 and detected_h > 0:
                if detected_w != self.width or detected_h != self.height:
                    logger.info(
                        "Adapting clock to detected display resolution: %dx%d",
                        detected_w,
                        detected_h,
                    )
                    self.width = detected_w
                    self.height = detected_h
                    # Invalidate cached frames
                    self.cached_clock_frame = None
                    self.cached_clock_rgb = None
                    self.last_clock_time = ""

        # Initialize plugin system
        await self._init_plugin_system()

        # Initialize brightness scheduler (fetch sunrise/sunset if configured)
        if self._brightness_scheduler and self._brightness_scheduler._has_sun_config:
            await self._brightness_scheduler.update_sun_data()

        frame_time = 1 / self.fps
        print(f"🕒 Starting zeClock at {self.fps} FPS")

        try:
            while self.running:
                t0 = time.monotonic()
                now = time.time()

                # Change color every minute if auto mode
                if self.color_mode == "auto" and now - self.last_color_change >= 60:
                    self.color = COLOR_LIST[int(now // 60) % len(COLOR_LIST)]
                    self.last_color_change = now
                    self.last_clock_time = ""  # Force refresh

                # Remote control: check for text overlay
                if self._command_handler and self._command_handler.has_text_overlay:
                    frame = self._render_text_overlay()
                    frame_time = 0.5

                # Remote control: check for screen off override
                elif self._command_handler and self._command_handler.screen_is_off:
                    frame = Image.new("RGB", (self.width, self.height), (0, 0, 0))
                    frame_time = 1.0

                # State machine transitions
                elif self._state == ClockState.CLOCK_ONLY:
                    frame = self._render_clock_frame()
                    frame_time = 0.5  # Refresh every 500ms for colon blinking

                    # Check if clock-only duration has elapsed
                    # In "time only" mode, never transition to plugins
                    if not self._current_is_time_only:
                        clock_display_seconds = self._get_clock_display_seconds()
                        if now - self._clock_only_start >= clock_display_seconds:
                            self._state = ClockState.PLUGIN_SELECT

                elif self._state == ClockState.PLUGIN_SELECT:
                    frame = self._render_clock_frame()
                    frame_time = 0.5

                    # Check if a plugin is forced by remote control
                    if self._command_handler and self._command_handler.forced_plugin:
                        forced_name = self._command_handler.forced_plugin
                        if (
                            self._plugin_manager
                            and self._plugin_manager.registry.has_plugin(forced_name)
                        ):
                            entry = self._plugin_manager.registry.get_plugin(
                                forced_name
                            )
                            if entry:
                                success = await self._plugin_manager.activate_plugin(
                                    entry.plugin
                                )
                                if success:
                                    self._state = ClockState.PLUGIN_ACTIVE
                        else:
                            # Invalid forced plugin, clear it
                            self._command_handler._forced_plugin = None
                            self._state = ClockState.CLOCK_ONLY
                            self._clock_only_start = now
                    else:
                        # Try to select and activate a plugin
                        activated = await self._select_and_activate_plugin()
                        if activated:
                            self._state = ClockState.PLUGIN_ACTIVE
                        else:
                            # No plugins available - stay in clock-only
                            self._state = ClockState.CLOCK_ONLY
                            self._clock_only_start = now

                elif self._state == ClockState.PLUGIN_ACTIVE:
                    # Check if forced plugin changed (user clicked a different plugin)
                    forced_name = (
                        self._command_handler.forced_plugin
                        if self._command_handler
                        else None
                    )
                    current_name = (
                        self._plugin_manager.active_plugin.name
                        if self._plugin_manager and self._plugin_manager.active_plugin
                        else None
                    )
                    if forced_name and forced_name != current_name:
                        # Forced plugin changed — switch immediately
                        if self._plugin_manager:
                            await self._plugin_manager.deactivate_plugin()
                        self._state = ClockState.PLUGIN_SELECT
                        frame = self._render_clock_frame()
                        frame_time = 0.04  # minimal delay to re-enter loop fast
                    elif not forced_name and forced_name is not None:
                        # forced_plugin was cleared (resume) — let normal deactivation handle it
                        pass
                    else:
                        # Check if plugin should be deactivated
                        # Skip deactivation if plugin is forced by remote control
                        forced = forced_name is not None
                        if (
                            not forced
                            and self._plugin_manager
                            and self._plugin_manager.should_deactivate()
                        ):
                            await self._plugin_manager.deactivate_plugin()
                            self._state = ClockState.CLOCK_ONLY
                            self._clock_only_start = time.time()
                            frame = self._render_clock_frame()
                            frame_time = 0.5
                        else:
                            # Get frame from active plugin
                            assert self._plugin_manager is not None
                            plugin_frame = await self._plugin_manager.get_frame()
                            if plugin_frame is None:
                                # Plugin signals completion
                                if forced:
                                    # Forced plugin completed — re-activate immediately
                                    logger.debug(
                                        "Forced plugin completed, re-activating"
                                    )
                                    await self._plugin_manager.deactivate_plugin()
                                    self._state = ClockState.PLUGIN_SELECT
                                else:
                                    await self._plugin_manager.deactivate_plugin()
                                    self._state = ClockState.CLOCK_ONLY
                                    self._clock_only_start = time.time()
                                frame = self._render_clock_frame()
                                frame_time = 0.5
                            else:
                                frame = plugin_frame
                                # Use plugin's frame delay
                                active = self._plugin_manager.active_plugin
                                if active:
                                    frame_time = active.frame_delay_ms / 1000.0
                                else:
                                    frame_time = 0.04  # 40ms default

                # Brightness scheduling (checked once per minute)
                await self._update_brightness()

                # Apply software dimming if active
                if self._current_sw_dimming > 0:
                    frame = apply_sw_dimming(frame, self._current_sw_dimming)

                # Send to DMD
                success = self.dmd_client.send_frame(frame)

                # Handle connection loss — wait with backoff, then reconnect
                if not success:
                    if not self._reconnect_logged:
                        print("⚠️ ZeDMD disconnected — waiting to reconnect...")
                        self._reconnect_logged = True
                    await asyncio.sleep(self._reconnect_delay)
                    # Try to reconnect
                    if self.dmd_client.connect():
                        print("✅ ZeDMD reconnected — resuming display")
                        self._reconnect_logged = False
                        self._reconnect_delay = 2.0  # Reset backoff
                    else:
                        # Increase backoff
                        self._reconnect_delay = min(self._reconnect_delay * 1.5, 30.0)
                    continue
                elif self._reconnect_logged:
                    print("✅ ZeDMD reconnected — resuming display")
                    self._reconnect_logged = False
                    self._reconnect_delay = 2.0

                # Frame timing
                elapsed = time.monotonic() - t0
                sleep_time = max(0, frame_time - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n🛑 Stopping zeClock...")
        except asyncio.CancelledError:
            print("\n🛑 Stopping zeClock...")
        finally:
            # Stop remote control services
            if self._mqtt_remote:
                self._mqtt_remote.stop()
            if self._rest_remote:
                self._rest_remote.stop()
            # Cleanup active plugin if any
            if self._plugin_manager and self._plugin_manager.is_plugin_active():
                await self._plugin_manager.deactivate_plugin()
            self.dmd_client.disconnect()
            print("✅ ZeDMD disconnected")

    async def _init_plugin_system(self) -> None:
        """Initialize the PluginManager, discover and load plugins."""
        self._plugin_manager = PluginManager(
            width=self.width,
            height=self.height,
            config_path=self._plugin_config_path,
            upscale_mode=self.upscale_mode,
            font=self.font_name,
        )

        try:
            await self._plugin_manager.discover_and_load()
        except Exception as e:
            logger.error(f"Failed to initialize plugin system: {e}")
            return

        # Log discovered and active plugins with their configured frequency
        all_plugins = self._plugin_manager.registry.get_all_plugins()
        active_plugins = self._plugin_manager.registry.get_active_plugins()
        all_names = [e.name for e in all_plugins]
        active_with_freq = [
            f"{e.name} ({e.frequency}%)" for e in active_plugins if e.frequency > 0
        ]
        logger.info(f"Plugins found: {all_names}")
        logger.info(f"Plugins activated: {active_with_freq}")

        # Inject display dimensions into pinball plugin config (it needs width/height)
        pinball_entry = self._plugin_manager.registry.get_plugin("pinball")
        if pinball_entry:
            for entry in self._plugin_manager.config.plugin_entries:
                if entry["name"] == "pinball":
                    entry["settings"]["width"] = self.width
                    entry["settings"]["height"] = self.height
                    break
            else:
                # Pinball not in config entries, add it
                self._plugin_manager.config.plugin_entries.append(
                    {
                        "name": "pinball",
                        "frequency": 100,
                        "settings": {
                            "width": self.width,
                            "height": self.height,
                        },
                    }
                )

        # Apply --plugins override if specified
        if self._plugins_override:
            success = self._apply_plugins_override(self._plugins_override)
            if not success:
                logger.error("All plugin names unrecognized, no plugins active")

        # Check if any plugins are available
        active_plugins = self._plugin_manager.registry.get_active_plugins()
        if not active_plugins:
            logger.warning("No active plugins available, clock-only mode")

    async def _init_remote_control(self) -> None:
        """Initialize remote control services (MQTT and REST API).

        Starts MQTT and REST as background asyncio tasks if configured.
        Both share the same CommandHandler for consistent behavior.
        """
        from .remote.command_handler import CommandHandler

        self._command_handler = CommandHandler(self)

        # Start MQTT if configured
        if self._mqtt_config and self._mqtt_config.enabled:
            from .remote.mqtt_remote import MqttRemote, MqttConfig

            mqtt_cfg = MqttConfig(
                enabled=self._mqtt_config.enabled,
                host=self._mqtt_config.host,
                port=self._mqtt_config.port,
                username=self._mqtt_config.username,
                password=self._mqtt_config.password,
                device_id=self._mqtt_config.device_id,
                topic_prefix=self._mqtt_config.topic_prefix,
                ha_discovery=self._mqtt_config.ha_discovery,
                ha_discovery_prefix=self._mqtt_config.ha_discovery_prefix,
                state_interval=self._mqtt_config.state_interval,
            )
            self._mqtt_remote = MqttRemote(mqtt_cfg, self._command_handler)
            asyncio.create_task(self._mqtt_remote.run())

        # Start REST API if configured
        if self._rest_config and self._rest_config.enabled:
            from .remote.rest_remote import RestRemote, RestConfig

            rest_cfg = RestConfig(
                enabled=self._rest_config.enabled,
                host=self._rest_config.host,
                port=self._rest_config.port,
            )
            self._rest_remote = RestRemote(rest_cfg, self._command_handler)
            asyncio.create_task(self._rest_remote.run())

    def _render_text_overlay(self) -> Image.Image:
        """Render a text overlay frame centered on screen.

        Uses the largest DotClk font that can render the text.
        Priority: STANDARD (21px, digits only) > MENU (11px, uppercase) > SYSTEM (7px, full ASCII).
        Falls back to PIL for characters not in any DotClk font.
        """
        text = self._command_handler.text_overlay if self._command_handler else ""
        if not text:
            return Image.new("RGB", (self.width, self.height), (0, 0, 0))

        # Transliterate accented/special characters to ASCII equivalents
        text = _transliterate(text)

        # Try MENU font first (11px, uppercase + digits — good balance of size and charset)
        # Convert to uppercase since MENU only has uppercase
        upper_text = text.upper()

        if self._text_overlay_font is None:
            from .resources.paths import get_fonts_dir

            fonts_dir = get_fonts_dir()
            # Load MENU font for overlay text
            if self.width >= 256 and self.height >= 64:
                menu_path = fonts_dir / "MENU_HD.fnt"
            else:
                menu_path = fonts_dir / "MENU.fnt"
            if menu_path.exists():
                try:
                    self._text_overlay_font = load_font(menu_path)
                except Exception as e:
                    logger.warning(f"Failed to load MENU font: {e}")

        # Check if MENU font can render all characters
        if self._text_overlay_font and hasattr(self._text_overlay_font, "char_info"):
            can_render = all(
                ch in self._text_overlay_font.char_info for ch in upper_text
            )
            if can_render:
                gray_frame = self._text_overlay_font.render_text(
                    upper_text,
                    self.width,
                    self.height,
                    upscale_mode=self.upscale_mode,
                )
                return colorize_grayscale(gray_frame, self.color)

        # Fall back to PIL for full Unicode support
        from PIL import ImageDraw, ImageFont

        frame = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Use PIL's default font scaled up via repeated rendering
        # On a 32px display, target ~20px font height for readability
        try:
            font = ImageFont.load_default(size=self.height - 8)
        except TypeError:
            # Pillow < 10.1 doesn't support size parameter
            font = ImageFont.load_default()

        # Center the text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        # If too wide, let PIL wrap or we truncate
        if text_w > self.width - 4:
            # Try smaller size
            try:
                font = ImageFont.load_default(size=max(10, self.height - 16))
            except TypeError:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

        x = (self.width - text_w) // 2
        y = (self.height - text_h) // 2
        draw.text((x, y), text, fill=self.color, font=font)
        return frame

    def _apply_plugins_override(self, plugins_str: str) -> bool:
        """Apply --plugins CLI override to the plugin manager.

        Args:
            plugins_str: Comma-separated list of plugin names.

        Returns:
            True if at least one valid plugin was found, False otherwise.
        """
        assert self._plugin_manager is not None
        plugin_names = [name.strip() for name in plugins_str.split(",") if name.strip()]
        valid_names = []

        for name in plugin_names:
            if self._plugin_manager.registry.has_plugin(name):
                valid_names.append(name)
            else:
                logger.warning(f"Unrecognized plugin name: '{name}'")

        if not valid_names:
            return False

        # Set equal frequency for valid plugins, zero out others
        equal_frequency = 100 // len(valid_names)
        for entry in self._plugin_manager.registry.get_all_plugins():
            if entry.name in valid_names:
                self._plugin_manager.registry.set_frequency(entry.name, equal_frequency)
            else:
                self._plugin_manager.registry.set_frequency(entry.name, 0)

        return True

    def _get_clock_display_seconds(self) -> float:
        """Get the clock-only display duration from plugin config."""
        if self._plugin_manager:
            return self._plugin_manager.config.clock_display_seconds
        return 5.0  # Default fallback

    async def _select_and_activate_plugin(self) -> bool:
        """Select and activate the next plugin.

        Returns:
            True if a plugin was successfully activated, False otherwise.
        """
        if not self._plugin_manager:
            return False

        plugin = self._plugin_manager.select_next_plugin()
        if plugin is None:
            return False

        success = await self._plugin_manager.activate_plugin(plugin)
        return success

    def _render_clock_frame(self) -> Image.Image:
        """Render a clock-only frame with colon blinking.

        Uses two-level caching:
        1. Grayscale text frame (changes every 500ms on blink)
        2. Colorized RGB frame (invalidated on color or text change)
        """
        # Generate clock with 500ms blink timing
        milliseconds = int(time.time() * 1000)
        blink_state = (milliseconds // 500) % 2
        cache_key = f"{time.strftime('%H:%M:%S')}_{blink_state}"

        needs_colorize = False

        if cache_key != self.last_clock_time:
            if blink_state == 0:
                display_time = time.strftime("%H:%M")
            else:
                display_time = time.strftime("%H %M")

            # Standard centered positioning
            assert self.dotclk_font is not None
            self.cached_clock_frame = self.dotclk_font.render_text(
                display_time, self.width, self.height, upscale_mode=self.upscale_mode
            )
            self.last_clock_time = cache_key
            needs_colorize = True

        if self.last_clock_color != self.color:
            self.last_clock_color = self.color
            needs_colorize = True

        if needs_colorize or self.cached_clock_rgb is None:
            assert self.cached_clock_frame is not None
            self.cached_clock_rgb = colorize_grayscale(
                self.cached_clock_frame, self.color
            )

        return self.cached_clock_rgb

    async def _update_brightness(self) -> None:
        """Check and apply brightness schedule (once per minute).

        Updates hardware brightness via the backend and stores the
        software dimming level for frame processing.
        """
        if not self._brightness_scheduler:
            return

        # Skip scheduler if brightness is manually overridden via remote control
        if (
            self._command_handler
            and self._command_handler.brightness_override is not None
        ):
            return

        now_mono = time.monotonic()
        # Check once per minute (60 seconds)
        if now_mono - self._last_brightness_check < 60.0:
            return
        self._last_brightness_check = now_mono

        # Update sunrise/sunset data if configured
        if self._brightness_scheduler._has_sun_config:
            await self._brightness_scheduler.update_sun_data()
            # Log sunrise/sunset times
            sun = self._brightness_scheduler._sun_data
            if sun:
                logger.info(
                    "☀️  Sunrise: %02d:%02d / Sunset: %02d:%02d",
                    sun.sunrise_hour,
                    sun.sunrise_minute,
                    sun.sunset_hour,
                    sun.sunset_minute,
                )

        # Get current brightness from scheduler
        result = self._brightness_scheduler.get_brightness()

        # Log brightness state
        logger.info(
            "💡 Brightness: HW=%d/15, SW dimming=%d%%, screen_off=%s, time_only=%s",
            result.hw_brightness,
            result.sw_dimming_percent,
            result.is_screen_off,
            result.is_time_only,
        )

        # Apply hardware brightness if backend supports it
        if hasattr(self.dmd_client, "_lib") and hasattr(self.dmd_client, "_instance"):
            if self.dmd_client._instance:
                self.dmd_client._lib.ZeDMD_SetBrightness(
                    self.dmd_client._instance, result.hw_brightness
                )

        # Store SW dimming for frame processing
        self._current_sw_dimming = result.sw_dimming_percent

        # Handle screen off (send black frame)
        if result.is_screen_off:
            self._current_sw_dimming = 100

        # Update time-only mode flag
        was_time_only = self._current_is_time_only
        self._current_is_time_only = result.is_time_only

        # If entering time-only mode while a plugin is active, deactivate it
        if result.is_time_only and not was_time_only:
            if self._plugin_manager and self._plugin_manager.is_plugin_active():
                await self._plugin_manager.deactivate_plugin()
                self._state = ClockState.CLOCK_ONLY
                self._clock_only_start = time.time()
            start = self._brightness_scheduler._time_only_start
            end = self._brightness_scheduler._time_only_end
            logger.info(
                "Entering time-only mode (%02d:%02d → %02d:%02d)",
                start[0] if start else 0,
                start[1] if start else 0,
                end[0] if end else 0,
                end[1] if end else 0,
            )

        if not result.is_time_only and was_time_only:
            logger.info("Exiting time-only mode")

    def stop(self) -> None:
        """Stop the clock"""
        self.running = False


def main() -> None:
    """Point d'entrée principal"""
    import argparse
    import logging
    import sys
    from .backend_config import load_config
    from .installer import check_and_install_resources
    from .brightness_scheduler import BrightnessScheduler, parse_schedule_config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description="zeClock - Animated DMD clock")
    parser.add_argument(
        "--color",
        choices=[
            "orange",
            "blue",
            "red",
            "purple",
            "green",
            "yellow",
            "cyan",
            "pink",
            "auto",
        ],
        default="auto",
        help="Clock color (default: auto-rotate every minute)",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Automatically install dmdserver and all resources without running the clock",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Disable interactive prompt during automatic bootstrap",
    )

    # Backend selection arguments
    parser.add_argument(
        "--backend",
        choices=["auto", "zedmd", "dmdserver"],
        default=None,
        help="DMD backend to use (default: auto — try zedmd first, fall back to dmdserver)",
    )
    parser.add_argument(
        "--wifi-addr",
        type=str,
        default=None,
        help="ZeDMD WiFi IP address (e.g., 192.168.0.35)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="ZeDMD USB serial device path (e.g., /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=None,
        help="Display brightness (0-15, default: 10)",
    )
    parser.add_argument(
        "--hd",
        action="store_true",
        help="Use ZeDMD HD resolution (256x64) instead of standard (128x32)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Display width in pixels (default: 128, or 256 with --hd)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Display height in pixels (default: 32, or 64 with --hd)",
    )
    parser.add_argument(
        "--upscale",
        choices=["nearest", "epx", "hq2x"],
        default=None,
        help=(
            "Upscaling algorithm for HD mode (default: epx). "
            "'nearest' = fast pixel doubling; "
            "'epx' = EPX/Scale2x, smooths diagonals, no new colors; "
            "'hq2x' = High Quality 2x, smoother curves via interpolation (best quality). "
            "See https://en.wikipedia.org/wiki/Pixel-art_scaling_algorithms"
        ),
    )

    # Plugin management arguments
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List all discovered plugins with name, description, and active status, then exit",
    )
    parser.add_argument(
        "--plugins",
        type=str,
        default=None,
        help="Comma-separated list of plugin names to activate with equal frequency (overrides config)",
    )
    parser.add_argument(
        "--plugin-config",
        type=str,
        default=None,
        help="Path to custom plugin configuration YAML file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (shows libzedmd internal messages)",
    )

    args = parser.parse_args()

    # Set log level based on --debug flag
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle --plugin-config path validation (must check before any plugin operations)
    if args.plugin_config is not None:
        config_path = Path(args.plugin_config)
        if not config_path.exists():
            logger.error(f"Plugin config file not found: {args.plugin_config}")
            print(
                f"Error: plugin config file not found: {args.plugin_config}",
                file=sys.stderr,
            )
            sys.exit(1)

    # If --bootstrap flag is active, force installation and exit
    if args.bootstrap:
        success = check_and_install_resources(interactive=False)
        sys.exit(0 if success else 1)

    # Handle --list-plugins: discover plugins and print info, then exit
    if args.list_plugins:
        _handle_list_plugins(args)
        sys.exit(0)

    # Determine backend mode for resource check (dmdserver doesn't need libzedmd)
    backend_mode = args.backend or "auto"

    # Otherwise, check / initialize interactively (or non-interactively if --no-prompt)
    if not check_and_install_resources(
        interactive=not args.no_prompt, backend=backend_mode
    ):
        print("❌ Cannot start: required resources are missing.")
        sys.exit(1)

    # Load backend configuration (config file + CLI args merged)
    # Handle --hd flag: sets width=256, height=64 unless explicitly overridden
    cli_width = args.width
    cli_height = args.height
    if args.hd:
        if cli_width is None:
            cli_width = 256
        if cli_height is None:
            cli_height = 64

    backend_config = load_config(
        backend=args.backend,
        wifi_addr=args.wifi_addr,
        device=args.device,
        brightness=args.brightness,
        width=cli_width,
        height=cli_height,
        upscale_mode=args.upscale,
    )

    # Create the backend via factory
    backend = create_backend(
        backend=backend_config.backend,
        wifi_addr=backend_config.wifi_addr,
        device=backend_config.device,
        brightness=backend_config.brightness,
        dmdserver_host=backend_config.dmdserver_host,
        dmdserver_port=backend_config.dmdserver_port,
        width=backend_config.width,
        height=backend_config.height,
    )

    # After backend creation, check if the backend detected a different resolution
    # (ZeDMDBackend auto-detects hardware resolution on connect)
    display_width = backend_config.width
    display_height = backend_config.height
    if hasattr(backend, "width") and hasattr(backend, "height"):
        # Will be updated after connect() — for now use configured values
        display_width = backend_config.width
        display_height = backend_config.height

    # Create brightness scheduler from config
    bs_config = backend_config.brightness_schedule
    schedule = parse_schedule_config(bs_config.schedule_lines)

    # Use location from [location] section for sunrise/sunset
    loc = backend_config.location
    scheduler = BrightnessScheduler(
        max_brightness=bs_config.max_brightness,
        schedule=schedule if schedule else None,
        latitude=loc.latitude,
        longitude=loc.longitude,
        sunrise_brightness=bs_config.sunrise_brightness,
        sunset_brightness=bs_config.sunset_brightness,
        time_only=bs_config.time_only,
    )

    if scheduler.has_schedule:
        print("💡 Brightness scheduling enabled")

    clock = ZeClock(
        width=display_width,
        height=display_height,
        backend=backend,
        color=args.color,
        plugin_config_path=Path(args.plugin_config) if args.plugin_config else None,
        plugins_override=args.plugins,
        upscale_mode=backend_config.upscale_mode,
        font=backend_config.font,
        brightness_scheduler=scheduler if scheduler.has_schedule else None,
        mqtt_config=backend_config.mqtt if backend_config.mqtt.enabled else None,
        rest_config=(
            backend_config.rest_api if backend_config.rest_api.enabled else None
        ),
    )
    try:
        asyncio.run(clock.run())
    except KeyboardInterrupt:
        # asyncio.run() may re-raise KeyboardInterrupt after task cancellation.
        # The finally block inside clock.run() handles disconnect, but if it
        # was skipped due to aggressive cancellation, disconnect here as a safety net.
        if clock.dmd_client.connected:
            clock.dmd_client.disconnect()
            print("✅ ZeDMD disconnected")


def _handle_list_plugins(args: Any) -> None:
    """Discover plugins and print their name, description, and active status."""
    from .plugin_manager import PluginManager

    config_path = Path(args.plugin_config) if args.plugin_config else None
    manager = PluginManager(width=128, height=32, config_path=config_path)
    asyncio.run(manager.discover_and_load())

    all_plugins = manager.registry.get_all_plugins()
    if not all_plugins:
        print("No plugins discovered.")
        return

    for entry in all_plugins:
        status = "active" if entry.state != "failed" else "inactive"
        print(f"{entry.name}\t{entry.plugin.description}\t{status}")


def _handle_plugins_override(args: Any, manager: Any) -> bool:
    """Apply --plugins CLI override: activate only specified plugins with equal frequency.

    Args:
        args: Parsed CLI arguments (must have .plugins attribute).
        manager: The PluginManager instance (after discover_and_load).

    Returns:
        True if at least one valid plugin was found, False if all names are unrecognized.
    """
    plugin_names = [name.strip() for name in args.plugins.split(",") if name.strip()]
    valid_names = []

    for name in plugin_names:
        if manager.registry.has_plugin(name):
            valid_names.append(name)
        else:
            logger.warning(f"Unrecognized plugin name: '{name}'")

    if not valid_names:
        logger.error(
            f"All plugin names unrecognized: {plugin_names}. Falling back to pinball."
        )
        return False

    # Override registry: set equal frequency for valid plugins, zero out others
    equal_frequency = 100 // len(valid_names)
    for entry in manager.registry.get_all_plugins():
        if entry.name in valid_names:
            manager.registry.set_frequency(entry.name, equal_frequency)
        else:
            manager.registry.set_frequency(entry.name, 0)

    return True


if __name__ == "__main__":
    main()
