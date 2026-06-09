"""Tests for REST API config-schema and geocode/search endpoints."""

from unittest.mock import MagicMock, patch
from typing import List, Optional

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from zeclock.plugins.base import ClockPlugin, ConfigField
from zeclock.plugin_registry import PluginEntry, PluginRegistry
from zeclock.remote.rest_remote import RestRemote, RestConfig


class FakePlugin(ClockPlugin):
    """Fake plugin with config_schema for testing."""

    def __init__(self, name: str, description: str, schema: List[ConfigField]):
        self._name = name
        self._description = description
        self._schema = schema

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def frame_delay_ms(self) -> int:
        return 100

    @property
    def config_schema(self) -> List[ConfigField]:
        return self._schema

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int):
        return None

    async def cleanup(self) -> None:
        pass


def _make_rest_remote(plugins: List[FakePlugin]) -> RestRemote:
    """Create a RestRemote with mocked clock and plugin manager."""
    registry = PluginRegistry()
    for p in plugins:
        registry.register(p, source="builtin")

    pm = MagicMock()
    pm.registry = registry

    clock = MagicMock()
    clock._plugin_manager = pm

    handler = MagicMock()
    handler._clock = clock
    handler.forced_plugin = None

    config = RestConfig(enabled=True, host="127.0.0.1", port=0)
    return RestRemote(config, handler)


@pytest.fixture
def rest_with_plugins():
    """RestRemote with sample plugins."""
    plugins = [
        FakePlugin(
            "weather",
            "Displays current weather conditions",
            [
                ConfigField(
                    name="city",
                    label="City",
                    field_type="city",
                    required=True,
                    description="Location for weather data",
                )
            ],
        ),
        FakePlugin(
            "stock",
            "Displays stock prices",
            [
                ConfigField(
                    name="symbols",
                    label="Stock Symbols",
                    field_type="text",
                    required=True,
                    description="Comma-separated tickers",
                    default=None,
                )
            ],
        ),
        FakePlugin("clock", "Shows time", []),
    ]
    return _make_rest_remote(plugins)


@pytest.fixture
def rest_no_plugins():
    """RestRemote with no plugin manager."""
    handler = MagicMock()
    handler._clock._plugin_manager = None
    config = RestConfig(enabled=True, host="127.0.0.1", port=0)
    return RestRemote(config, handler)


# --- /api/plugins/config-schema tests ---


@pytest.mark.asyncio
async def test_config_schema_returns_all_plugins(rest_with_plugins):
    """GET /api/plugins/config-schema returns all registered plugin schemas."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/plugins/config-schema")
        assert resp.status == 200
        data = await resp.json()
        assert "plugins" in data
        assert len(data["plugins"]) == 3


@pytest.mark.asyncio
async def test_config_schema_plugin_structure(rest_with_plugins):
    """Each plugin entry has name, description, and schema fields."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/plugins/config-schema")
        data = await resp.json()

        weather = next(p for p in data["plugins"] if p["name"] == "weather")
        assert weather["description"] == "Displays current weather conditions"
        assert len(weather["schema"]) == 1
        field = weather["schema"][0]
        assert field["name"] == "city"
        assert field["label"] == "City"
        assert field["field_type"] == "city"
        assert field["required"] is True
        assert field["description"] == "Location for weather data"
        assert field["default"] is None


@pytest.mark.asyncio
async def test_config_schema_empty_schema_plugin(rest_with_plugins):
    """Plugin with no config_schema returns empty schema list."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/plugins/config-schema")
        data = await resp.json()

        clock = next(p for p in data["plugins"] if p["name"] == "clock")
        assert clock["schema"] == []


@pytest.mark.asyncio
async def test_config_schema_no_plugin_manager(rest_no_plugins):
    """Returns empty plugins list when no plugin manager is available."""
    async with TestClient(TestServer(rest_no_plugins._app)) as client:
        resp = await client.get("/api/plugins/config-schema")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"plugins": []}


# --- /api/geocode/search tests ---


@pytest.mark.asyncio
async def test_geocode_search_returns_400_for_short_query(rest_with_plugins):
    """Returns 400 if query is less than 3 characters."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/geocode/search?q=ab")
        assert resp.status == 400
        data = await resp.json()
        assert data["success"] is False
        assert "3 characters" in data["message"]


@pytest.mark.asyncio
async def test_geocode_search_returns_400_for_empty_query(rest_with_plugins):
    """Returns 400 if query is empty."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/geocode/search?q=")
        assert resp.status == 400


@pytest.mark.asyncio
async def test_geocode_search_returns_400_for_missing_query(rest_with_plugins):
    """Returns 400 if q parameter is missing entirely."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/geocode/search")
        assert resp.status == 400


@pytest.mark.asyncio
async def test_geocode_search_returns_400_for_whitespace_query(rest_with_plugins):
    """Returns 400 if query is only whitespace (less than 3 chars after trim)."""
    async with TestClient(TestServer(rest_with_plugins._app)) as client:
        resp = await client.get("/api/geocode/search?q=  ")
        assert resp.status == 400


@pytest.mark.asyncio
async def test_geocode_search_calls_search_cities(rest_with_plugins):
    """Valid query (3+ chars) calls search_cities and returns results."""
    from zeclock.geocoder import GeoResult

    mock_results = [
        GeoResult(
            latitude=48.8566,
            longitude=2.3522,
            display_name="Paris, Île-de-France, France",
            country="France",
        ),
    ]

    with patch("zeclock.geocoder.search_cities", return_value=mock_results):
        async with TestClient(TestServer(rest_with_plugins._app)) as client:
            resp = await client.get("/api/geocode/search?q=Paris")
            assert resp.status == 200
            data = await resp.json()
            assert "results" in data
            assert len(data["results"]) == 1
            result = data["results"][0]
            assert result["display_name"] == "Paris, Île-de-France, France"
            assert result["country"] == "France"
            assert result["latitude"] == 48.8566
            assert result["longitude"] == 2.3522


@pytest.mark.asyncio
async def test_geocode_search_empty_results(rest_with_plugins):
    """Returns empty results list when no cities match."""
    with patch("zeclock.geocoder.search_cities", return_value=[]):
        async with TestClient(TestServer(rest_with_plugins._app)) as client:
            resp = await client.get("/api/geocode/search?q=xyznonexistent")
            assert resp.status == 200
            data = await resp.json()
            assert data["results"] == []
