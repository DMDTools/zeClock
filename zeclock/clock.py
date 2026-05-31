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
from .colors import COLOR_LIST, COLOR_MAP, COLOR_NAMES
from .overlay import colorize_grayscale
from .plugin_manager import PluginManager
from .readers import load_font

logger = logging.getLogger(__name__)


class ClockState(enum.Enum):
    """State machine states for the clock display."""

    CLOCK_ONLY = "clock_only"
    PLUGIN_SELECT = "plugin_select"
    PLUGIN_ACTIVE = "plugin_active"


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
        animation_color: Optional[str] = None,
        plugin_config_path: Optional[Path] = None,
        plugins_override: Optional[str] = None,
        upscale_mode: str = "epx",
        font: str = "STANDARD",
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

        # Animation color (defaults to same as clock if not specified)
        self.animation_color_name = animation_color
        self.animation_color = (
            COLOR_MAP.get(animation_color, COLOR_LIST[0])
            if animation_color
            else self.color
        )

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

    async def run(self) -> None:
        """Main asynchronous loop with plugin-driven state machine."""
        # Initial connection with retry loop
        if not self.dmd_client.connect():
            print("⚠️ DMD backend not available — waiting for device...")
            print(
                "👉 Check your backend configuration (--backend, --wifi-addr, --device)"
            )
            delay = 2.0
            while self.running:
                await asyncio.sleep(delay)
                if self.dmd_client.connect():
                    print("✅ DMD backend connected")
                    break
                delay = min(delay * 1.5, 30.0)
                logger.info("DMD still unavailable — next retry in %.0fs", delay)
            if not self.running:
                return

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

                # State machine transitions
                if self._state == ClockState.CLOCK_ONLY:
                    frame = self._render_clock_frame()
                    frame_time = 0.5  # Refresh every 500ms for colon blinking

                    # Check if clock-only duration has elapsed
                    clock_display_seconds = self._get_clock_display_seconds()
                    if now - self._clock_only_start >= clock_display_seconds:
                        self._state = ClockState.PLUGIN_SELECT

                elif self._state == ClockState.PLUGIN_SELECT:
                    frame = self._render_clock_frame()
                    frame_time = 0.5

                    # Try to select and activate a plugin
                    activated = await self._select_and_activate_plugin()
                    if activated:
                        self._state = ClockState.PLUGIN_ACTIVE
                    else:
                        # No plugins available - stay in clock-only
                        self._state = ClockState.CLOCK_ONLY
                        self._clock_only_start = now

                elif self._state == ClockState.PLUGIN_ACTIVE:
                    # Check if plugin should be deactivated
                    if (
                        self._plugin_manager
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

                # Send to DMD
                success = self.dmd_client.send_frame(frame)

                # Handle connection loss — backend manages reconnection
                if not success:
                    if not self._reconnect_logged:
                        print("⚠️ ZeDMD disconnected — attempting reconnection...")
                        self._reconnect_logged = True
                    # Slow down the loop while disconnected to avoid busy-waiting
                    await asyncio.sleep(1.0)
                    continue
                elif self._reconnect_logged:
                    print("✅ ZeDMD reconnected — resuming display")
                    self._reconnect_logged = False

                # Frame timing
                elapsed = time.monotonic() - t0
                sleep_time = max(0, frame_time - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n🛑 Stopping zeClock...")
        finally:
            # Cleanup active plugin if any
            if self._plugin_manager and self._plugin_manager.is_plugin_active():
                await self._plugin_manager.deactivate_plugin()
            self.dmd_client.disconnect()

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

        # Wire --color and --animation-color to PinballPlugin config
        clock_color_name = COLOR_NAMES.get(self.color, "orange")
        anim_color_name = self.animation_color_name or clock_color_name

        # Inject color settings into pinball plugin config
        pinball_entry = self._plugin_manager.registry.get_plugin("pinball")
        if pinball_entry:
            # Update the config that will be passed to pinball plugin on activation
            for entry in self._plugin_manager.config.plugin_entries:
                if entry["name"] == "pinball":
                    entry["settings"]["color"] = clock_color_name
                    entry["settings"]["animation_color"] = anim_color_name
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
                            "color": clock_color_name,
                            "animation_color": anim_color_name,
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
        "--animation-color",
        choices=["orange", "blue", "red", "purple", "green", "yellow", "cyan", "pink"],
        help="Animation color (default: same as clock)",
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

    clock = ZeClock(
        width=display_width,
        height=display_height,
        backend=backend,
        color=args.color,
        animation_color=args.animation_color,
        plugin_config_path=Path(args.plugin_config) if args.plugin_config else None,
        plugins_override=args.plugins,
        upscale_mode=backend_config.upscale_mode,
        font=backend_config.font,
    )
    asyncio.run(clock.run())


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
