"""REST API remote control for zeClock.

Provides a simple HTTP API for controlling the clock. Uses aiohttp
(already a project dependency) to serve endpoints and a web UI.

All endpoints accept both GET and POST for convenience.
GET uses query parameters, POST uses JSON body.

Endpoints:
    GET       /                    — Web UI (redirects to /ui/)
    GET       /ui/                 — Web UI static files
    GET/POST  /api/status          — Get current clock status
    GET/POST  /api/screen/on       — Turn screen on
    GET/POST  /api/screen/off      — Turn screen off
    GET/POST  /api/plugin/force    — Force a specific plugin (?plugin=name)
    GET/POST  /api/plugin/resume   — Resume normal plugin rotation
    GET/POST  /api/plugins         — List all plugins with status
    GET/POST  /api/text            — Display text (?text=...&duration=10)
    GET       /api/speaker-timer/status  — Get timer status
    POST      /api/speaker-timer/start   — Start/resume timer
    POST      /api/speaker-timer/pause   — Pause timer
    POST      /api/speaker-timer/reset   — Reset timer
    POST      /api/speaker-timer/set     — Set duration (?seconds=N)
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiohttp import web

from .command_handler import CommandHandler, CommandResult, CommandType, RemoteCommand

logger = logging.getLogger(__name__)

# Path to the web UI static files
WEB_UI_DIR = Path(__file__).parent / "web"


@dataclass
class RestConfig:
    """REST API configuration."""

    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080


class RestRemote:
    """HTTP REST API server for zeClock remote control.

    Runs as an asyncio task alongside the main clock loop.
    Shares the same CommandHandler as MQTT for consistent behavior.
    Serves both the REST API and the web UI.
    """

    def __init__(self, config: RestConfig, handler: CommandHandler) -> None:
        self._config = config
        self._handler = handler
        self._app: web.Application = web.Application(
            middlewares=[self._no_cache_ui_middleware]
        )
        self._runner: Any = None
        self._setup_routes()

    @web.middleware
    async def _no_cache_ui_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        """Add no-cache headers to all /ui/ responses (JS, CSS, HTML)."""
        response = await handler(request)
        if request.path.startswith("/ui/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    def _setup_routes(self) -> None:
        """Register API routes and web UI static file serving."""
        # Web UI routes
        self._app.router.add_get("/", self._handle_root_redirect)
        self._app.router.add_get("/ui", self._handle_ui_redirect)

        # API routes
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/discovery", self._handle_discovery)
        self._app.router.add_get("/api/screen/on", self._handle_screen_on)
        self._app.router.add_post("/api/screen/on", self._handle_screen_on)
        self._app.router.add_get("/api/screen/off", self._handle_screen_off)
        self._app.router.add_post("/api/screen/off", self._handle_screen_off)
        self._app.router.add_get("/api/plugin/force", self._handle_force_plugin)
        self._app.router.add_post("/api/plugin/force", self._handle_force_plugin)
        self._app.router.add_get("/api/plugin/resume", self._handle_resume_plugin)
        self._app.router.add_post("/api/plugin/resume", self._handle_resume_plugin)
        self._app.router.add_get("/api/plugins", self._handle_list_plugins)
        self._app.router.add_get("/api/text", self._handle_display_text)
        self._app.router.add_post("/api/text", self._handle_display_text)
        self._app.router.add_post("/api/alert", self._handle_alert)

        # Brightness API routes
        self._app.router.add_get("/api/brightness", self._handle_get_brightness)
        self._app.router.add_post("/api/brightness", self._handle_set_brightness)
        self._app.router.add_post("/api/brightness/auto", self._handle_brightness_auto)

        # Speaker Timer API routes
        self._app.router.add_get(
            "/api/speaker-timer/status", self._handle_speaker_timer_status
        )
        self._app.router.add_post(
            "/api/speaker-timer/start", self._handle_speaker_timer_start
        )
        self._app.router.add_post(
            "/api/speaker-timer/pause", self._handle_speaker_timer_pause
        )
        self._app.router.add_post(
            "/api/speaker-timer/reset", self._handle_speaker_timer_reset
        )
        self._app.router.add_post(
            "/api/speaker-timer/set", self._handle_speaker_timer_set
        )

        # Configuration API routes
        self._app.router.add_get("/api/config", self._handle_get_config)
        self._app.router.add_post("/api/config", self._handle_save_config)
        self._app.router.add_get("/api/config/plugins", self._handle_get_plugins_config)
        self._app.router.add_post(
            "/api/config/plugins", self._handle_save_plugins_config
        )

        # Plugin config schema and geocode routes
        self._app.router.add_get(
            "/api/plugins/config-schema", self._handle_plugins_config_schema
        )
        self._app.router.add_get("/api/geocode/search", self._handle_geocode_search)
        self._app.router.add_get("/api/timezone", self._handle_resolve_timezone)

        # Settings export/import routes
        self._app.router.add_get("/api/config/export", self._handle_export_config)
        self._app.router.add_post("/api/config/import", self._handle_import_config)

        # GIF directory management routes
        self._app.router.add_get(
            "/api/gif/directories", self._handle_list_gif_directories
        )
        self._app.router.add_post("/api/gif/upload", self._handle_gif_upload)
        self._app.router.add_post(
            "/api/gif/directories/delete", self._handle_delete_gif_directory
        )
        self._app.router.add_post(
            "/api/gif/directories/create", self._handle_create_gif_directory
        )

        # Debug / Logs API routes
        self._app.router.add_get("/api/logs/stream", self._handle_logs_stream)
        self._app.router.add_get("/api/debug/info", self._handle_debug_info)

        # System management routes
        self._app.router.add_post("/api/restart", self._handle_restart)

        # Static files for web UI (must be last to avoid catching API routes)
        if WEB_UI_DIR.exists():
            self._app.router.add_get("/ui/", self._handle_ui_index)
            self._app.router.add_static(
                "/ui/", WEB_UI_DIR, name="webui", append_version=True
            )

    async def run(self) -> None:
        """Start the HTTP server."""
        # Suppress aiohttp access logs unless debug level is enabled
        access_log = logger if logger.isEnabledFor(logging.DEBUG) else None
        self._runner = web.AppRunner(self._app, access_log=access_log)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._config.host, self._config.port)
        try:
            await site.start()
            logger.info(
                f"REST API listening on http://{self._config.host}:{self._config.port}"
            )
            print(
                f"🌐 REST API listening on http://{self._config.host}:{self._config.port}"
            )
            # Keep running until cancelled
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("REST API shutting down")
        finally:
            await self._runner.cleanup()

    def stop(self) -> None:
        """Stop the REST server (cleanup handled by task cancellation)."""
        pass

    def _json_response(self, result: CommandResult, status: int = 200) -> web.Response:
        """Build a JSON response from a CommandResult."""
        body = {
            "success": result.success,
            "message": result.message,
        }
        if result.data:
            body["data"] = result.data
        return web.json_response(body, status=status)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """GET /api/status — Return current clock status."""
        cmd = RemoteCommand(type=CommandType.GET_STATUS)
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    async def _handle_discovery(self, request: web.Request) -> web.Response:
        """GET /api/discovery — Return live discovery state."""
        clock = self._handler._clock
        if hasattr(clock, "_discovery_state"):
            return web.json_response(
                {
                    "success": True,
                    "data": clock._discovery_state.to_dict(),
                }
            )
        return web.json_response(
            {
                "success": True,
                "data": {
                    "status": "idle",
                    "message": "",
                    "steps": [],
                    "candidates": [],
                    "result": None,
                },
            }
        )

    async def _handle_screen_on(self, request: web.Request) -> web.Response:
        """POST /api/screen/on — Turn screen on."""
        cmd = RemoteCommand(type=CommandType.SCREEN_ON)
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    async def _handle_screen_off(self, request: web.Request) -> web.Response:
        """POST /api/screen/off — Turn screen off."""
        cmd = RemoteCommand(type=CommandType.SCREEN_OFF)
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    async def _handle_force_plugin(self, request: web.Request) -> web.Response:
        """GET/POST /api/plugin/force — Force a specific plugin.

        GET:  /api/plugin/force?plugin=weather
        POST: {"plugin": "weather"}
        """
        if request.method == "GET":
            plugin_name = request.query.get("plugin")
        else:
            try:
                body = await request.json()
            except (json.JSONDecodeError, Exception):
                return web.json_response(
                    {"success": False, "message": "Invalid JSON body"},
                    status=400,
                )
            plugin_name = body.get("plugin")

        if not isinstance(plugin_name, str) or not plugin_name.strip():
            return web.json_response(
                {"success": False, "message": "Missing 'plugin' field"},
                status=400,
            )

        cmd = RemoteCommand(
            type=CommandType.FORCE_PLUGIN, params={"plugin": plugin_name.strip()}
        )
        result = await self._handler.execute(cmd)
        status = 200 if result.success else 404
        return self._json_response(result, status=status)

    async def _handle_resume_plugin(self, request: web.Request) -> web.Response:
        """POST /api/plugin/resume — Resume normal plugin rotation."""
        cmd = RemoteCommand(type=CommandType.FORCE_PLUGIN, params={"plugin": None})
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    async def _handle_display_text(self, request: web.Request) -> web.Response:
        """GET/POST /api/text — Display text on screen.

        GET:  /api/text?text=Hello!&duration=10
        POST: {"text": "Hello!", "duration": 10}
        """
        if request.method == "GET":
            text = request.query.get("text")
            duration_str = request.query.get("duration", "10")
            try:
                duration = int(duration_str)
            except (ValueError, TypeError):
                duration = 10
        else:
            try:
                body = await request.json()
            except (json.JSONDecodeError, Exception):
                return web.json_response(
                    {"success": False, "message": "Invalid JSON body"},
                    status=400,
                )
            text = body.get("text")
            duration = body.get("duration", 10)
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = 10

        if not isinstance(text, str) or not text.strip():
            return web.json_response(
                {"success": False, "message": "Missing 'text' field"},
                status=400,
            )

        duration = max(1, min(300, duration))

        cmd = RemoteCommand(
            type=CommandType.DISPLAY_TEXT,
            params={"text": text.strip(), "duration": duration},
        )
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    async def _handle_alert(self, request: web.Request) -> web.Response:
        """POST /api/alert — Display a rich alert with blinking border and icon.

        POST: {"text": "Person detected!", "duration": 15, "icon": "person", "color": [255,0,0]}

        Parameters:
            text (str): Alert message (auto-wrapped to fit display).
            duration (int): Display duration in seconds (1-300, default 15).
            icon (str): Optional icon name ("beacon", "person", "vehicle",
                        "animal", "motion", "warning", "camera").
            color (list): Optional border color as [R, G, B] (default: [255, 0, 0] red).
        """
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"},
                status=400,
            )

        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return web.json_response(
                {"success": False, "message": "Missing 'text' field"},
                status=400,
            )

        duration = body.get("duration", 15)
        try:
            duration = max(1, min(300, int(duration)))
        except (ValueError, TypeError):
            duration = 15

        icon = body.get("icon")
        if icon is not None and not isinstance(icon, str):
            icon = None

        color = body.get("color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            try:
                color = tuple(int(c) for c in color)
            except (ValueError, TypeError):
                color = (255, 0, 0)
        else:
            color = (255, 0, 0)

        # Set alert state on the command handler
        import time as _time

        self._handler._alert_text = text.strip()
        self._handler._alert_expires = _time.time() + duration
        self._handler._alert_icon = icon
        self._handler._alert_color = color
        self._handler._alert_frame_count = 0

        logger.info(
            "Alert displayed: '%s' for %ds (icon=%s)", text.strip(), duration, icon
        )
        return web.json_response(
            {
                "success": True,
                "message": f"Alert displayed for {duration}s",
                "data": {"text": text.strip(), "duration": duration, "icon": icon},
            }
        )

    # --- Brightness handlers ---

    async def _handle_get_brightness(self, request: web.Request) -> web.Response:
        """GET /api/brightness — Get current brightness state."""
        override = self._handler.brightness_override
        data = {
            "override": override,
            "sw_dimming": self._handler._clock._current_sw_dimming,
            "time_only": self._handler._clock._current_is_time_only,
            "mode": "manual" if override is not None else "auto",
        }
        return web.json_response({"success": True, "data": data})

    async def _handle_set_brightness(self, request: web.Request) -> web.Response:
        """POST /api/brightness — Set brightness manually (0-15).

        POST: {"brightness": 10}
        GET:  /api/brightness?value=10
        """
        if request.method == "GET":
            value_str = request.query.get("value")
            if value_str is None:
                return web.json_response(
                    {"success": False, "message": "Missing 'value' parameter"},
                    status=400,
                )
            try:
                brightness = int(value_str)
            except (ValueError, TypeError):
                return web.json_response(
                    {"success": False, "message": "Invalid brightness value"},
                    status=400,
                )
        else:
            try:
                body = await request.json()
            except (json.JSONDecodeError, Exception):
                return web.json_response(
                    {"success": False, "message": "Invalid JSON body"},
                    status=400,
                )
            brightness = body.get("brightness")
            if brightness is None:
                return web.json_response(
                    {"success": False, "message": "Missing 'brightness' field"},
                    status=400,
                )
            try:
                brightness = int(brightness)
            except (ValueError, TypeError):
                return web.json_response(
                    {"success": False, "message": "Invalid brightness value"},
                    status=400,
                )

        brightness = max(0, min(15, brightness))
        cmd = RemoteCommand(
            type=CommandType.SET_BRIGHTNESS, params={"brightness": brightness}
        )
        result = await self._handler.execute(cmd)

        # Persist brightness to zeclock.ini
        self._persist_brightness(brightness)

        return self._json_response(result)

    async def _handle_brightness_auto(self, request: web.Request) -> web.Response:
        """POST /api/brightness/auto — Resume automatic brightness scheduling."""
        cmd = RemoteCommand(
            type=CommandType.SET_BRIGHTNESS, params={"brightness": None}
        )
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    def _persist_brightness(self, brightness: int) -> None:
        """Persist brightness value to zeclock.ini [zedmd] section."""
        import configparser
        import io

        from ..atomic_write import atomic_write_text
        from ..paths import get_config_dir

        config_path = get_config_dir() / "zeclock.ini"
        parser = configparser.RawConfigParser()
        if config_path.exists():
            parser.read(str(config_path))
        if not parser.has_section("zedmd"):
            parser.add_section("zedmd")
        parser.set("zedmd", "brightness", str(brightness))
        config_path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        parser.write(buf)
        atomic_write_text(config_path, buf.getvalue())

    def _reload_brightness_scheduler(self, config_body: dict) -> None:
        """Rebuild the brightness scheduler from saved config without restart."""
        from ..brightness_scheduler import BrightnessScheduler, parse_schedule_config

        clock = self._handler._clock

        bs_section = config_body.get("brightness_schedule", {})
        loc_section = config_body.get("location", {})

        # Parse max brightness
        max_br = 7
        try:
            max_br = max(1, min(15, int(bs_section.get("max_brightness", 7))))
        except (ValueError, TypeError):
            pass

        # Parse schedule lines (exclude non-schedule keys)
        schedule_lines = {
            k: v
            for k, v in bs_section.items()
            if k not in ("max_brightness", "sunrise_brightness", "sunset_brightness")
        }
        schedule = parse_schedule_config(schedule_lines)

        # Parse location
        lat = None
        lng = None
        try:
            lat_str = loc_section.get("latitude", "")
            lng_str = loc_section.get("longitude", "")
            if lat_str:
                lat = float(lat_str)
            if lng_str:
                lng = float(lng_str)
        except (ValueError, TypeError):
            pass

        # Parse sunrise/sunset brightness
        sunrise_br = None
        sunset_br = None
        try:
            sr = bs_section.get("sunrise_brightness", "").rstrip("%")
            if sr:
                sunrise_br = max(0, min(100, int(sr)))
        except (ValueError, TypeError):
            pass
        try:
            ss = bs_section.get("sunset_brightness", "").rstrip("%")
            if ss:
                sunset_br = max(0, min(100, int(ss)))
        except (ValueError, TypeError):
            pass

        # Parse sun transition duration
        sun_transition = 30
        try:
            st = bs_section.get("sun_transition_minutes", "30")
            if st:
                sun_transition = max(0, min(120, int(st)))
        except (ValueError, TypeError):
            pass

        # Rebuild scheduler
        clock._brightness_scheduler = BrightnessScheduler(
            max_brightness=max_br,
            schedule=schedule,
            latitude=lat,
            longitude=lng,
            sunrise_brightness=sunrise_br,
            sunset_brightness=sunset_br,
            sun_transition_minutes=sun_transition,
        )
        # Reset check timer so it applies immediately
        clock._last_brightness_check = 0.0

        # Clear any manual override so scheduler takes over
        if self._handler._brightness_override is not None:
            self._handler._brightness_override = None

        logger.info("Brightness scheduler reloaded from config")

    # --- System management handlers ---

    async def _handle_restart(self, request: web.Request) -> web.Response:
        """POST /api/restart — Restart the zeClock service."""
        import subprocess

        logger.info("Restart requested via REST API")

        # Send response before restarting
        resp = web.json_response({"success": True, "message": "Restarting zeClock..."})
        await resp.prepare(request)
        await resp.write_eof()

        # Schedule restart after a short delay to let the response be sent
        async def _do_restart() -> None:
            await asyncio.sleep(1)
            try:
                subprocess.Popen(
                    ["sudo", "systemctl", "restart", "zeclock.service"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, OSError) as e:
                logger.warning(f"Could not restart service: {e}")

        asyncio.ensure_future(_do_restart())
        return resp

    # --- Web UI handlers ---

    async def _handle_root_redirect(self, request: web.Request) -> web.Response:
        """GET / — Redirect to web UI."""
        raise web.HTTPFound("/ui/")

    async def _handle_ui_redirect(self, request: web.Request) -> web.Response:
        """GET /ui — Redirect to /ui/ (with trailing slash)."""
        raise web.HTTPFound("/ui/")

    async def _handle_ui_index(self, request: web.Request) -> web.Response:
        """GET /ui/ — Serve index.html with no-cache headers."""
        index_path = WEB_UI_DIR / "index.html"
        if index_path.exists():
            resp = web.FileResponse(index_path)
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            return resp  # type: ignore[return-value]
        return web.Response(text="Web UI not found", status=404)

    async def _handle_list_plugins(self, request: web.Request) -> web.Response:
        """GET /api/plugins — List all plugins with their status."""
        pm = self._handler._clock._plugin_manager
        if pm is None:
            return web.json_response(
                {"success": True, "data": {"plugins": []}},
            )

        plugins = []
        default_plugin_name = pm.config.default_plugin
        for entry in pm.registry.get_all_plugins():
            plugin_info: dict = {
                "name": entry.name,
                "description": entry.plugin.description,
                "state": entry.state,
                "frequency": entry.frequency,
                "source": entry.source,
                "is_default": entry.name == default_plugin_name,
            }
            # Check if plugin has web controls
            if hasattr(entry.plugin, "get_web_controls"):
                plugin_info["web_controls"] = entry.plugin.get_web_controls()
            plugins.append(plugin_info)

        active_plugin = None
        if pm.active_plugin:
            active_plugin = pm.active_plugin.name

        forced_plugin = None
        if self._handler.forced_plugin:
            forced_plugin = self._handler.forced_plugin

        return web.json_response(
            {
                "success": True,
                "data": {
                    "plugins": plugins,
                    "active_plugin": active_plugin,
                    "forced_plugin": forced_plugin,
                    "default_plugin": default_plugin_name,
                },
            }
        )

    # --- Settings Export/Import handlers ---

    async def _handle_export_config(self, request: web.Request) -> web.Response:
        """GET /api/config/export — Export all settings as a JSON bundle."""
        import configparser

        import yaml

        from ..paths import get_config_dir

        config_dir = get_config_dir()
        bundle: dict = {"_version": 1}

        # Export zeclock.ini
        ini_path = config_dir / "zeclock.ini"
        if ini_path.exists():
            parser = configparser.RawConfigParser()
            parser.read(str(ini_path))
            ini_data: dict = {}
            for section in parser.sections():
                ini_data[section] = dict(parser.items(section))
            bundle["config"] = ini_data

        # Export plugins.yaml
        plugins_path = config_dir / "plugins.yaml"
        if plugins_path.exists():
            try:
                with open(plugins_path, "r") as f:
                    plugins_data = yaml.safe_load(f)
                bundle["plugins"] = plugins_data or {}
            except Exception as e:
                logger.warning("Failed to read plugins.yaml for export: %s", e)

        return web.json_response({"success": True, "data": bundle})

    async def _handle_import_config(self, request: web.Request) -> web.Response:
        """POST /api/config/import — Restore settings from a JSON bundle."""
        import configparser

        import yaml

        from ..paths import get_config_dir

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"}, status=400
            )

        if not isinstance(body, dict):
            return web.json_response(
                {"success": False, "message": "Body must be a JSON object"}, status=400
            )

        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        restored = []

        # Restore zeclock.ini
        if "config" in body and isinstance(body["config"], dict):
            import io

            from ..atomic_write import atomic_write_text

            ini_path = config_dir / "zeclock.ini"
            parser = configparser.RawConfigParser()
            for section, values in body["config"].items():
                if not isinstance(values, dict):
                    continue
                parser.add_section(section)
                for key, value in values.items():
                    parser.set(section, str(key), str(value))
            buf = io.StringIO()
            parser.write(buf)
            atomic_write_text(ini_path, buf.getvalue())
            restored.append("zeclock.ini")

        # Restore plugins.yaml
        if "plugins" in body and isinstance(body["plugins"], dict):
            from ..atomic_write import atomic_write_text as _atomic_write

            plugins_path = config_dir / "plugins.yaml"
            _atomic_write(
                plugins_path,
                yaml.dump(body["plugins"], default_flow_style=False, sort_keys=False),
            )
            restored.append("plugins.yaml")

            # Reload plugin config
            pm = self._handler._clock._plugin_manager
            if pm:
                pm.config.reload()

        if not restored:
            return web.json_response(
                {"success": False, "message": "No valid configuration found in file"},
                status=400,
            )

        logger.info("Configuration restored: %s", ", ".join(restored))
        return web.json_response(
            {
                "success": True,
                "message": f"Restored: {', '.join(restored)}. "
                "Restart zeClock for full effect.",
            }
        )

    # --- Plugin Config Schema and Geocode handlers ---

    async def _handle_plugins_config_schema(self, request: web.Request) -> web.Response:
        """GET /api/plugins/config-schema — Return aggregated config schemas."""
        pm = self._handler._clock._plugin_manager
        if pm is None:
            return web.json_response({"plugins": []})

        plugins = []
        for entry in pm.registry.get_all_plugins():
            schema = entry.plugin.config_schema
            plugins.append(
                {
                    "name": entry.name,
                    "description": entry.plugin.description,
                    "schema": [
                        {
                            "name": field.name,
                            "label": field.label,
                            "field_type": field.field_type,
                            "required": field.required,
                            "description": field.description,
                            "default": field.default,
                            "options": field.options if field.options else None,
                        }
                        for field in schema
                    ],
                }
            )

        return web.json_response({"plugins": plugins})

    async def _handle_geocode_search(self, request: web.Request) -> web.Response:
        """GET /api/geocode/search?q=<query> — Search cities via geocoder."""
        from ..geocoder import search_cities

        query = request.query.get("q", "")
        if len(query.strip()) < 3:
            return web.json_response(
                {"success": False, "message": "Query must be at least 3 characters"},
                status=400,
            )

        # Run blocking geocoder in a thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, search_cities, query)
        return web.json_response(
            {
                "results": [
                    {
                        "display_name": r.display_name,
                        "country": r.country,
                        "latitude": r.latitude,
                        "longitude": r.longitude,
                    }
                    for r in results
                ]
            }
        )

    async def _handle_resolve_timezone(self, request: web.Request) -> web.Response:
        """GET /api/timezone?lat=X&lon=Y — Resolve coordinates to IANA timezone."""
        from ..geocoder import resolve_timezone

        lat_str = request.query.get("lat", "")
        lon_str = request.query.get("lon", "")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except (ValueError, TypeError):
            return web.json_response(
                {"success": False, "message": "lat and lon must be numbers"},
                status=400,
            )

        loop = asyncio.get_event_loop()
        tz_name = await loop.run_in_executor(None, resolve_timezone, lat, lon)

        if tz_name is None:
            return web.json_response(
                {"success": False, "message": "Could not resolve timezone"},
                status=404,
            )

        return web.json_response({"success": True, "timezone": tz_name})

    # --- GIF Directory Management handlers ---

    def _get_gif_base_dir(self) -> Path:
        """Get the base GIF directory (plugins/gif/).

        Creates the directory if it doesn't exist (safe for first-time use
        and for persistent /data partition on read-only RPi deployments).
        """
        from ..paths import get_plugins_dir

        gif_dir = get_plugins_dir() / "gif"
        gif_dir.mkdir(parents=True, exist_ok=True)
        return gif_dir

    async def _handle_list_gif_directories(self, request: web.Request) -> web.Response:
        """GET /api/gif/directories — List GIF directories with file counts."""
        gif_base = self._get_gif_base_dir()

        directories = []
        if gif_base.exists() and gif_base.is_dir():
            # List immediate subdirectories
            for item in sorted(gif_base.iterdir()):
                if item.is_dir():
                    # Count GIF files (recursive)
                    gif_count = len(
                        list(item.rglob("*.gif")) + list(item.rglob("*.GIF"))
                    )
                    directories.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "gif_count": gif_count,
                        }
                    )

            # Also count GIFs directly in the base dir (not in subdirectories)
            root_gifs = list(gif_base.glob("*.gif")) + list(gif_base.glob("*.GIF"))
            if root_gifs:
                directories.insert(
                    0,
                    {
                        "name": "(root)",
                        "path": str(gif_base),
                        "gif_count": len(root_gifs),
                    },
                )

        return web.json_response(
            {
                "success": True,
                "data": {
                    "base_path": str(gif_base),
                    "directories": directories,
                },
            }
        )

    async def _handle_gif_upload(self, request: web.Request) -> web.Response:
        """POST /api/gif/upload — Upload GIF files to a directory.

        Accepts multipart/form-data with:
            - directory: target subdirectory name (optional, defaults to root)
            - files: one or more GIF files

        Files are saved to plugins/gif/<directory>/.
        The directory is created if it doesn't exist.
        """
        gif_base = self._get_gif_base_dir()

        try:
            reader = await request.multipart()
        except Exception:
            return web.json_response(
                {"success": False, "message": "Expected multipart/form-data"},
                status=400,
            )

        directory_name = ""
        uploaded_files = []
        errors = []

        while True:
            part = await reader.next()
            if part is None:
                break

            # Skip nested multipart readers (only handle body parts)
            from aiohttp.multipart import BodyPartReader

            if not isinstance(part, BodyPartReader):
                continue

            if part.name == "directory":
                directory_name = (await part.text()).strip()
            elif part.name == "files" or part.name == "file":
                filename = part.filename
                if not filename:
                    continue

                # Validate file extension
                if not filename.lower().endswith(".gif"):
                    errors.append(f"Skipped '{filename}': not a .gif file")
                    # Drain the part data
                    await part.read()
                    continue

                # Sanitize filename (remove path separators)
                safe_filename = Path(filename).name
                if not safe_filename:
                    continue

                # Determine target directory
                if directory_name:
                    # Sanitize directory name
                    safe_dir = "".join(
                        c for c in directory_name if c.isalnum() or c in "-_ "
                    ).strip()
                    if not safe_dir:
                        safe_dir = "uploads"
                    target_dir = gif_base / safe_dir
                else:
                    target_dir = gif_base

                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / safe_filename

                # Read and write file
                try:
                    data = await part.read()
                    # Basic GIF validation: check magic bytes
                    if not data[:6] in (b"GIF87a", b"GIF89a"):
                        errors.append(f"Skipped '{filename}': not a valid GIF file")
                        continue

                    with open(target_path, "wb") as f:
                        f.write(data)
                    uploaded_files.append(
                        {
                            "filename": safe_filename,
                            "path": str(target_path),
                            "size": len(data),
                        }
                    )
                except Exception as e:
                    errors.append(f"Failed to save '{filename}': {e}")

        if not uploaded_files and not errors:
            return web.json_response(
                {"success": False, "message": "No files uploaded"},
                status=400,
            )

        return web.json_response(
            {
                "success": len(uploaded_files) > 0,
                "message": f"Uploaded {len(uploaded_files)} file(s)"
                + (f", {len(errors)} error(s)" if errors else ""),
                "data": {
                    "uploaded": uploaded_files,
                    "errors": errors,
                },
            }
        )

    async def _handle_create_gif_directory(self, request: web.Request) -> web.Response:
        """POST /api/gif/directories/create — Create a new GIF directory.

        POST: {"name": "my-gifs"}
        """
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"},
                status=400,
            )

        name = body.get("name", "").strip()
        if not name:
            return web.json_response(
                {"success": False, "message": "Missing 'name' field"},
                status=400,
            )

        # Sanitize directory name
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
        if not safe_name:
            return web.json_response(
                {"success": False, "message": "Invalid directory name"},
                status=400,
            )

        gif_base = self._get_gif_base_dir()
        target_dir = gif_base / safe_name
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Created GIF directory: %s", target_dir)
        return web.json_response(
            {
                "success": True,
                "message": f"Directory '{safe_name}' created",
                "data": {"name": safe_name, "path": str(target_dir)},
            }
        )

    async def _handle_delete_gif_directory(self, request: web.Request) -> web.Response:
        """POST /api/gif/directories/delete — Delete a GIF directory.

        POST: {"path": "/path/to/dir"} or {"name": "dirname"}
        """
        import shutil

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"},
                status=400,
            )

        gif_base = self._get_gif_base_dir()
        target_path = None

        # Accept either full path or name
        if body.get("name"):
            name = body["name"].strip()
            safe_name = "".join(c for c in name if c.isalnum() or c in "-_ ").strip()
            target_path = gif_base / safe_name
        elif body.get("path"):
            target_path = Path(body["path"])

        if not target_path:
            return web.json_response(
                {"success": False, "message": "Missing 'name' or 'path' field"},
                status=400,
            )

        # Security: ensure path is under gif_base
        try:
            target_path.resolve().relative_to(gif_base.resolve())
        except ValueError:
            return web.json_response(
                {"success": False, "message": "Invalid path: outside GIF directory"},
                status=403,
            )

        if not target_path.exists():
            return web.json_response(
                {"success": False, "message": "Directory does not exist"},
                status=404,
            )

        if not target_path.is_dir():
            return web.json_response(
                {"success": False, "message": "Path is not a directory"},
                status=400,
            )

        # Don't allow deleting the base gif directory itself
        if target_path.resolve() == gif_base.resolve():
            return web.json_response(
                {"success": False, "message": "Cannot delete the root GIF directory"},
                status=400,
            )

        try:
            shutil.rmtree(target_path)
            logger.info("Deleted GIF directory: %s", target_path)
        except Exception as e:
            return web.json_response(
                {"success": False, "message": f"Failed to delete: {e}"},
                status=500,
            )

        return web.json_response(
            {"success": True, "message": f"Directory '{target_path.name}' deleted"}
        )

    # --- Speaker Timer handlers ---

    async def _handle_speaker_timer_status(self, request: web.Request) -> web.Response:
        """GET /api/speaker-timer/status — Get timer status."""
        from ..plugins.speaker_timer_plugin import SpeakerTimerPlugin

        status = SpeakerTimerPlugin.get_status()
        return web.json_response({"success": True, "data": status})

    async def _handle_speaker_timer_start(self, request: web.Request) -> web.Response:
        """POST /api/speaker-timer/start — Start/resume the timer.

        Also forces the speaker-timer plugin to be displayed.
        """
        from ..plugins.speaker_timer_plugin import SpeakerTimerPlugin

        # Force the speaker-timer plugin active
        cmd = RemoteCommand(
            type=CommandType.FORCE_PLUGIN, params={"plugin": "speaker-timer"}
        )
        await self._handler.execute(cmd)

        status = SpeakerTimerPlugin.start()
        return web.json_response({"success": True, "data": status})

    async def _handle_speaker_timer_pause(self, request: web.Request) -> web.Response:
        """POST /api/speaker-timer/pause — Pause the timer."""
        from ..plugins.speaker_timer_plugin import SpeakerTimerPlugin

        status = SpeakerTimerPlugin.pause()
        return web.json_response({"success": True, "data": status})

    async def _handle_speaker_timer_reset(self, request: web.Request) -> web.Response:
        """POST /api/speaker-timer/reset — Reset the timer.

        Also resumes normal plugin rotation.
        """
        from ..plugins.speaker_timer_plugin import SpeakerTimerPlugin

        status = SpeakerTimerPlugin.reset()

        # Resume normal rotation
        cmd = RemoteCommand(type=CommandType.FORCE_PLUGIN, params={"plugin": None})
        await self._handler.execute(cmd)

        return web.json_response({"success": True, "data": status})

    async def _handle_speaker_timer_set(self, request: web.Request) -> web.Response:
        """POST /api/speaker-timer/set — Set timer duration.

        POST: {"seconds": 1200} or {"minutes": 20}
        """
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"},
                status=400,
            )

        from ..plugins.speaker_timer_plugin import SpeakerTimerPlugin

        seconds = body.get("seconds")
        minutes = body.get("minutes")

        if seconds is not None:
            try:
                seconds = int(seconds)
            except (ValueError, TypeError):
                return web.json_response(
                    {"success": False, "message": "Invalid 'seconds' value"},
                    status=400,
                )
        elif minutes is not None:
            try:
                seconds = int(minutes) * 60
            except (ValueError, TypeError):
                return web.json_response(
                    {"success": False, "message": "Invalid 'minutes' value"},
                    status=400,
                )
        else:
            return web.json_response(
                {"success": False, "message": "Provide 'seconds' or 'minutes'"},
                status=400,
            )

        status = SpeakerTimerPlugin.set_duration(seconds)
        return web.json_response({"success": True, "data": status})

    # --- Configuration handlers ---

    async def _handle_get_config(self, request: web.Request) -> web.Response:
        """GET /api/config — Return current zeclock.ini as structured JSON."""
        import configparser

        from ..paths import get_config_dir

        config_path = get_config_dir() / "zeclock.ini"
        if not config_path.exists():
            return web.json_response(
                {"success": True, "data": {}},
            )

        parser = configparser.RawConfigParser()
        parser.read(str(config_path))

        # Convert to nested dict
        data = {}
        for section in parser.sections():
            data[section] = dict(parser.items(section))

        return web.json_response({"success": True, "data": data})

    async def _handle_save_config(self, request: web.Request) -> web.Response:
        """POST /api/config — Save zeclock.ini from structured JSON.

        Body: {"zedmd": {"wifi_addr": "...", "brightness": "10"}, "display": {...}, ...}
        """
        import configparser

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"}, status=400
            )

        if not isinstance(body, dict):
            return web.json_response(
                {"success": False, "message": "Body must be a JSON object"}, status=400
            )

        from ..paths import get_config_dir

        config_path = get_config_dir() / "zeclock.ini"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        parser = configparser.RawConfigParser()
        for section, values in body.items():
            if not isinstance(values, dict):
                continue
            parser.add_section(section)
            for key, value in values.items():
                parser.set(section, str(key), str(value))

        import io

        from ..atomic_write import atomic_write_text

        buf = io.StringIO()
        parser.write(buf)
        atomic_write_text(config_path, buf.getvalue())

        logger.info("Configuration saved to %s", config_path)

        # Hot-reload brightness scheduler from the new config
        self._reload_brightness_scheduler(body)

        return web.json_response(
            {
                "success": True,
                "message": "Configuration saved and applied.",
            }
        )

    async def _handle_get_plugins_config(self, request: web.Request) -> web.Response:
        """GET /api/config/plugins — Return current plugins.yaml as JSON."""
        import yaml

        from ..paths import get_config_dir

        config_path = get_config_dir() / "plugins.yaml"
        if not config_path.exists():
            return web.json_response({"success": True, "data": {}})

        try:
            with open(config_path, "r") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return web.json_response(
                {"success": False, "message": f"Failed to parse plugins.yaml: {e}"},
                status=500,
            )

        return web.json_response({"success": True, "data": data or {}})

    async def _handle_save_plugins_config(self, request: web.Request) -> web.Response:
        """POST /api/config/plugins — Save plugins.yaml from JSON.

        Body: {"clock_display_seconds": 5, "plugins": [...]}
        """
        import yaml

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"success": False, "message": "Invalid JSON body"}, status=400
            )

        if not isinstance(body, dict):
            return web.json_response(
                {"success": False, "message": "Body must be a JSON object"}, status=400
            )

        from ..paths import get_config_dir

        config_path = get_config_dir() / "plugins.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        from ..atomic_write import atomic_write_text

        atomic_write_text(
            config_path, yaml.dump(body, default_flow_style=False, sort_keys=False)
        )

        logger.info("Plugins configuration saved to %s", config_path)

        # Reload plugin config to pick up global settings (language, etc.)
        pm = self._handler._clock._plugin_manager
        if pm:
            pm.config.reload()
            pm._apply_config_frequencies()

        # Reconfigure affected plugins without restart
        reconfigured = []
        if pm and body.get("plugins"):
            for plugin_entry in body["plugins"]:
                name = plugin_entry.get("name", "")
                if name and pm.registry.has_plugin(name):
                    success = await pm.reconfigure_plugin(name)
                    if success:
                        reconfigured.append(name)

        if reconfigured:
            msg = f"Configuration saved and applied to: {', '.join(reconfigured)}"
        else:
            msg = "Configuration saved."

        return web.json_response({"success": True, "message": msg})

    # --- Debug & Logs ---

    async def _handle_logs_stream(self, request: web.Request) -> web.StreamResponse:
        """GET /api/logs/stream — SSE endpoint for real-time log streaming."""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        class SSEHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass  # drop oldest if consumer is slow

        handler = SSEHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        handler.setLevel(logging.DEBUG)

        # Attach to root logger to capture all log output
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    await response.write(f"data: {msg}\n\n".encode("utf-8"))
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    await response.write(b": keepalive\n\n")
                except ConnectionResetError:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            root_logger.removeHandler(handler)

        return response

    async def _handle_debug_info(self, request: web.Request) -> web.Response:
        """GET /api/debug/info — Return system and clock debug information."""
        import platform
        import shutil
        import subprocess
        import sys
        import os

        try:
            clock = self._handler._clock

            # Gather plugin info
            plugins_info = []
            pm = getattr(clock, "_plugin_manager", None)
            if pm:
                registry = getattr(pm, "registry", None)
                if registry:
                    for entry in registry.get_all_plugins():
                        plugins_info.append(
                            {
                                "name": entry.name,
                                "state": entry.state,
                                "source": entry.source,
                                "frequency": entry.frequency,
                                "active": (
                                    pm._current_plugin_name == entry.name
                                    if hasattr(pm, "_current_plugin_name")
                                    else False
                                ),
                            }
                        )

            # Backend info
            backend_info = {}
            backend = getattr(clock, "_backend", None)
            if backend:
                backend_info = {
                    "type": type(backend).__name__,
                    "connected": getattr(backend, "_connected", False),
                }

            info = {
                "system": {
                    "platform": platform.platform(),
                    "python": sys.version.split()[0],
                    "arch": platform.machine(),
                    "pid": os.getpid(),
                    "cwd": os.getcwd(),
                },
                "clock": {
                    "running": True,
                    "state": (
                        clock._state.value if hasattr(clock, "_state") else "unknown"
                    ),
                    "backend": backend_info,
                    "plugins_loaded": len(plugins_info),
                    "plugins": plugins_info,
                },
                "memory": {},
                "storage": {},
                "health": {},
            }

            # --- Health: CPU, temperature, throttle, uptime (Raspberry Pi) ---
            health: dict = {}
            try:
                # CPU usage (1-second sample via /proc/stat)
                try:
                    with open("/proc/stat") as f:
                        line1 = f.readline()
                    import asyncio

                    await asyncio.sleep(0.5)
                    with open("/proc/stat") as f:
                        line2 = f.readline()

                    def _parse_cpu(line: str) -> tuple:
                        parts = line.split()[1:]
                        idle = int(parts[3]) + int(parts[4])
                        total = sum(int(p) for p in parts)
                        return idle, total

                    idle1, total1 = _parse_cpu(line1)
                    idle2, total2 = _parse_cpu(line2)
                    delta_total = total2 - total1
                    delta_idle = idle2 - idle1
                    if delta_total > 0:
                        cpu_percent = round((1.0 - delta_idle / delta_total) * 100, 1)
                        health["cpu_percent"] = cpu_percent
                except (OSError, IndexError, ValueError):
                    pass

                # CPU temperature
                try:
                    with open("/sys/class/thermal/thermal_zone0/temp") as f:
                        temp_milli = int(f.read().strip())
                    health["cpu_temp_c"] = round(temp_milli / 1000.0, 1)
                except (OSError, ValueError):
                    # Fallback: vcgencmd (Raspberry Pi specific)
                    try:
                        result = subprocess.run(
                            ["vcgencmd", "measure_temp"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if result.returncode == 0:
                            # Output: temp=42.8'C
                            temp_str = result.stdout.strip()
                            temp_val = float(temp_str.split("=")[1].split("'")[0])
                            health["cpu_temp_c"] = temp_val
                    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                        pass

                # Throttle status (Raspberry Pi specific — vcgencmd)
                try:
                    result = subprocess.run(
                        ["vcgencmd", "get_throttled"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if result.returncode == 0:
                        # Output: throttled=0x0
                        hex_str = result.stdout.strip().split("=")[1]
                        throttle_val = int(hex_str, 16)
                        health["throttle_raw"] = hex_str
                        # Decode throttle bits
                        health["throttle_flags"] = {
                            "under_voltage_now": bool(throttle_val & 0x1),
                            "freq_capped_now": bool(throttle_val & 0x2),
                            "throttled_now": bool(throttle_val & 0x4),
                            "soft_temp_limit_now": bool(throttle_val & 0x8),
                            "under_voltage_occurred": bool(throttle_val & 0x10000),
                            "freq_capped_occurred": bool(throttle_val & 0x20000),
                            "throttled_occurred": bool(throttle_val & 0x40000),
                            "soft_temp_limit_occurred": bool(throttle_val & 0x80000),
                        }
                        health["throttle_ok"] = throttle_val == 0
                except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
                    pass

                # Uptime
                try:
                    with open("/proc/uptime") as f:
                        uptime_secs = float(f.read().split()[0])
                    health["uptime_seconds"] = round(uptime_secs)
                    # Human-readable
                    days = int(uptime_secs // 86400)
                    hours = int((uptime_secs % 86400) // 3600)
                    mins = int((uptime_secs % 3600) // 60)
                    if days > 0:
                        health["uptime_human"] = f"{days}d {hours}h {mins}m"
                    elif hours > 0:
                        health["uptime_human"] = f"{hours}h {mins}m"
                    else:
                        health["uptime_human"] = f"{mins}m"
                except (OSError, ValueError):
                    pass

            except Exception:
                pass

            info["health"] = health

            # Memory info — cross-platform (Windows + Linux + macOS)
            try:
                # Try psutil first (most accurate, cross-platform)
                import psutil

                proc = psutil.Process(os.getpid())
                mem = proc.memory_info()
                sys_mem = psutil.virtual_memory()
                info["memory"] = {
                    "process_rss_mb": round(mem.rss / (1024 * 1024), 1),
                    "system_total_mb": round(sys_mem.total / (1024 * 1024), 0),
                    "system_available_mb": round(sys_mem.available / (1024 * 1024), 0),
                    "system_percent_used": sys_mem.percent,
                }
            except ImportError:
                # Fallback: resource module (Linux/macOS only)
                try:
                    import resource

                    rusage = resource.getrusage(resource.RUSAGE_SELF)
                    # On Linux ru_maxrss is in KB, on macOS in bytes
                    rss_kb = rusage.ru_maxrss
                    if platform.system() == "Darwin":
                        rss_kb = rss_kb // 1024
                    info["memory"] = {
                        "process_rss_mb": round(rss_kb / 1024, 1),
                    }
                except (ImportError, Exception):
                    pass

            # Storage info — cross-platform via shutil.disk_usage
            try:
                # Disk where zeClock data lives
                data_path = os.getcwd()
                usage = shutil.disk_usage(data_path)
                info["storage"] = {
                    "path": data_path,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "used_gb": round(usage.used / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                    "percent_used": round((usage.used / usage.total) * 100, 1),
                }
            except (OSError, Exception):
                pass

            # Network info — cross-platform
            import socket

            network_info: dict = {}
            try:
                # Get hostname
                hostname = socket.gethostname()
                network_info["hostname"] = hostname

                # Get primary IP (cross-platform trick: connect to external addr)
                ip_addr = "127.0.0.1"
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.settimeout(0.5)
                    s.connect(("8.8.8.8", 80))
                    ip_addr = s.getsockname()[0]
                    s.close()
                except Exception:
                    pass
                network_info["ip"] = ip_addr

                # Detect interface type and SSID
                interface_type = "unknown"
                ssid = None
                try:
                    import subprocess

                    if platform.system() == "Linux":
                        # Check if connected via WiFi
                        try:
                            result = subprocess.run(
                                ["iwgetid", "-r"],
                                capture_output=True,
                                text=True,
                                timeout=2,
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                interface_type = "wifi"
                                ssid = result.stdout.strip()
                            else:
                                interface_type = "ethernet"
                        except FileNotFoundError:
                            # iwgetid not installed, try nmcli
                            try:
                                result = subprocess.run(
                                    [
                                        "nmcli",
                                        "-t",
                                        "-f",
                                        "ACTIVE,SSID,TYPE",
                                        "connection",
                                        "show",
                                        "--active",
                                    ],
                                    capture_output=True,
                                    text=True,
                                    timeout=2,
                                )
                                if result.returncode == 0:
                                    for line in result.stdout.strip().split("\n"):
                                        parts = line.split(":")
                                        if (
                                            len(parts) >= 3
                                            and "wireless" in parts[2].lower()
                                        ):
                                            interface_type = "wifi"
                                            ssid = parts[1]
                                            break
                                    else:
                                        interface_type = "ethernet"
                            except FileNotFoundError:
                                interface_type = "ethernet"
                    elif platform.system() == "Windows":
                        result = subprocess.run(
                            ["netsh", "wlan", "show", "interfaces"],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                        if result.returncode == 0 and "SSID" in result.stdout:
                            interface_type = "wifi"
                            for line in result.stdout.split("\n"):
                                stripped = line.strip()
                                if (
                                    stripped.startswith("SSID")
                                    and "BSSID" not in stripped
                                ):
                                    ssid = stripped.split(":", 1)[1].strip()
                                    break
                        else:
                            interface_type = "ethernet"
                    elif platform.system() == "Darwin":
                        result = subprocess.run(
                            [
                                "/System/Library/PrivateFrameworks/"
                                "Apple80211.framework/Versions/Current/"
                                "Resources/airport",
                                "-I",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if result.returncode == 0 and "SSID" in result.stdout:
                            interface_type = "wifi"
                            for line in result.stdout.split("\n"):
                                if "SSID" in line and "BSSID" not in line:
                                    ssid = line.split(":", 1)[1].strip()
                                    break
                        else:
                            interface_type = "ethernet"
                except Exception:
                    pass

                network_info["interface"] = interface_type
                if ssid:
                    network_info["ssid"] = ssid

                # Service URLs
                rest_port = self._config.port
                network_info["urls"] = {
                    "webui": f"http://{ip_addr}:{rest_port}/ui/",
                    "api": f"http://{ip_addr}:{rest_port}/api/",
                }

                # SSH info only on Raspberry Pi (ARM Linux)
                if platform.system() == "Linux" and platform.machine().startswith(
                    ("arm", "aarch64")
                ):
                    network_info["urls"][
                        "ssh"
                    ] = f"ssh zeclock@{ip_addr}  (pwd: zeclock)"

                # MQTT info
                mqtt_config = getattr(clock, "_mqtt_config", None)
                if mqtt_config and getattr(mqtt_config, "enabled", False):
                    mqtt_host = getattr(mqtt_config, "host", "localhost")
                    mqtt_port = getattr(mqtt_config, "port", 1883)
                    network_info["urls"]["mqtt"] = f"mqtt://{mqtt_host}:{mqtt_port}"
                else:
                    network_info["urls"]["mqtt"] = "disabled"

            except Exception:
                pass

            info["network"] = network_info

            return web.json_response({"success": True, "data": info})
        except Exception as e:
            return web.json_response({"success": False, "message": str(e)}, status=500)
