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
        self._app: web.Application = web.Application()
        self._runner: Any = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Register API routes and web UI static file serving."""
        # Web UI routes
        self._app.router.add_get("/", self._handle_root_redirect)
        self._app.router.add_get("/ui", self._handle_ui_redirect)

        # API routes
        self._app.router.add_get("/api/status", self._handle_status)
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

        # Static files for web UI (must be last to avoid catching API routes)
        if WEB_UI_DIR.exists():
            self._app.router.add_get("/ui/", self._handle_ui_index)
            self._app.router.add_static("/ui/", WEB_UI_DIR, name="webui")

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
        return self._json_response(result)

    async def _handle_brightness_auto(self, request: web.Request) -> web.Response:
        """POST /api/brightness/auto — Resume automatic brightness scheduling."""
        cmd = RemoteCommand(
            type=CommandType.SET_BRIGHTNESS, params={"brightness": None}
        )
        result = await self._handler.execute(cmd)
        return self._json_response(result)

    # --- Web UI handlers ---

    async def _handle_root_redirect(self, request: web.Request) -> web.Response:
        """GET / — Redirect to web UI."""
        raise web.HTTPFound("/ui/")

    async def _handle_ui_redirect(self, request: web.Request) -> web.Response:
        """GET /ui — Redirect to /ui/ (with trailing slash)."""
        raise web.HTTPFound("/ui/")

    async def _handle_ui_index(self, request: web.Request) -> web.Response:
        """GET /ui/ — Serve index.html."""
        index_path = WEB_UI_DIR / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)  # type: ignore[return-value]
        return web.Response(text="Web UI not found", status=404)

    async def _handle_list_plugins(self, request: web.Request) -> web.Response:
        """GET /api/plugins — List all plugins with their status."""
        pm = self._handler._clock._plugin_manager
        if pm is None:
            return web.json_response(
                {"success": True, "data": {"plugins": []}},
            )

        plugins = []
        for entry in pm.registry.get_all_plugins():
            plugin_info: dict = {
                "name": entry.name,
                "description": entry.plugin.description,
                "state": entry.state,
                "frequency": entry.frequency,
                "source": entry.source,
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
                },
            }
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

        config_path = Path.home() / ".zeclock" / "config" / "zeclock.ini"
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

        config_path = Path.home() / ".zeclock" / "config" / "zeclock.ini"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        parser = configparser.RawConfigParser()
        for section, values in body.items():
            if not isinstance(values, dict):
                continue
            parser.add_section(section)
            for key, value in values.items():
                parser.set(section, str(key), str(value))

        with open(config_path, "w") as f:
            parser.write(f)

        logger.info("Configuration saved to %s", config_path)
        return web.json_response(
            {
                "success": True,
                "message": "Configuration saved. Restart zeClock to apply changes.",
            }
        )

    async def _handle_get_plugins_config(self, request: web.Request) -> web.Response:
        """GET /api/config/plugins — Return current plugins.yaml as JSON."""
        import yaml

        config_path = Path.home() / ".zeclock" / "config" / "plugins.yaml"
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

        config_path = Path.home() / ".zeclock" / "config" / "plugins.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            yaml.dump(body, f, default_flow_style=False, sort_keys=False)

        logger.info("Plugins configuration saved to %s", config_path)
        return web.json_response(
            {
                "success": True,
                "message": "Plugins configuration saved. Restart zeClock to apply changes.",
            }
        )
