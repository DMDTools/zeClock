"""REST API remote control for zeClock.

Provides a simple HTTP API for controlling the clock. Uses aiohttp
(already a project dependency) to serve endpoints.

All endpoints accept both GET and POST for convenience.
GET uses query parameters, POST uses JSON body.

Endpoints:
    GET/POST  /api/status          — Get current clock status
    GET/POST  /api/screen/on       — Turn screen on
    GET/POST  /api/screen/off      — Turn screen off
    GET/POST  /api/plugin/force    — Force a specific plugin (?plugin=name)
    GET/POST  /api/plugin/resume   — Resume normal plugin rotation
    GET/POST  /api/text            — Display text (?text=...&duration=10)
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import web

from .command_handler import CommandHandler, CommandResult, CommandType, RemoteCommand

logger = logging.getLogger(__name__)


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
    """

    def __init__(self, config: RestConfig, handler: CommandHandler) -> None:
        self._config = config
        self._handler = handler
        self._app: web.Application = web.Application()
        self._runner: Any = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Register API routes (GET and POST for all endpoints)."""
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/screen/on", self._handle_screen_on)
        self._app.router.add_post("/api/screen/on", self._handle_screen_on)
        self._app.router.add_get("/api/screen/off", self._handle_screen_off)
        self._app.router.add_post("/api/screen/off", self._handle_screen_off)
        self._app.router.add_get("/api/plugin/force", self._handle_force_plugin)
        self._app.router.add_post("/api/plugin/force", self._handle_force_plugin)
        self._app.router.add_get("/api/plugin/resume", self._handle_resume_plugin)
        self._app.router.add_post("/api/plugin/resume", self._handle_resume_plugin)
        self._app.router.add_get("/api/text", self._handle_display_text)
        self._app.router.add_post("/api/text", self._handle_display_text)

    async def run(self) -> None:
        """Start the HTTP server."""
        self._runner = web.AppRunner(self._app)
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
