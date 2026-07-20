"""Tests for settings export/import API endpoints."""

import configparser
from unittest.mock import MagicMock

import pytest
import yaml
from aiohttp.test_utils import TestClient, TestServer

from zeclock.remote.rest_remote import RestConfig, RestRemote


def _make_rest_remote(tmp_path):
    """Create a RestRemote with mocked clock pointing to tmp config dir."""
    from zeclock.plugin_config import PluginConfig

    plugin_config = PluginConfig(config_path=tmp_path / "plugins.yaml")

    pm = MagicMock()
    pm.config = plugin_config

    clock = MagicMock()
    clock._plugin_manager = pm

    handler = MagicMock()
    handler._clock = clock
    handler.forced_plugin = None

    config = RestConfig(enabled=True, host="127.0.0.1", port=0)
    return RestRemote(config, handler)


@pytest.fixture
def config_dir(tmp_path):
    """Create a temp config directory with sample config files."""
    # Create zeclock.ini
    ini_path = tmp_path / "zeclock.ini"
    parser = configparser.RawConfigParser()
    parser.add_section("zedmd")
    parser.set("zedmd", "wifi_addr", "192.168.1.100")
    parser.set("zedmd", "brightness", "7")
    parser.add_section("display")
    parser.set("display", "font", "BOLD")
    with open(ini_path, "w") as f:
        parser.write(f)

    # Create plugins.yaml
    plugins_path = tmp_path / "plugins.yaml"
    plugins_data = {
        "default_plugin": "clock",
        "language": "fr",
        "clock_display_seconds": 10,
        "plugins": [
            {"name": "clock", "frequency": 0, "settings": {}},
            {"name": "weather", "frequency": 50, "settings": {"city": "Paris"}},
        ],
    }
    with open(plugins_path, "w") as f:
        yaml.dump(plugins_data, f, default_flow_style=False)

    return tmp_path


@pytest.fixture
def rest(config_dir):
    """RestRemote wired to the temp config directory."""
    return _make_rest_remote(config_dir)


# --- GET /api/config/export ---


@pytest.mark.asyncio
async def test_export_returns_both_configs(rest, config_dir):
    """Export includes both config and plugins sections."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "zeclock.remote.rest_remote.RestRemote._get_config_dir", None, raising=False
        )
        # Patch get_config_dir to return our tmp dir
        import zeclock.paths

        mp.setattr(zeclock.paths, "get_config_dir", lambda: config_dir)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.get("/api/config/export")
            assert resp.status == 200
            data = await resp.json()

    assert data["success"] is True
    bundle = data["data"]
    assert bundle["_version"] == 1
    assert "config" in bundle
    assert "plugins" in bundle

    # Check ini content
    assert bundle["config"]["zedmd"]["wifi_addr"] == "192.168.1.100"
    assert bundle["config"]["zedmd"]["brightness"] == "7"
    assert bundle["config"]["display"]["font"] == "BOLD"

    # Check plugins content
    assert bundle["plugins"]["language"] == "fr"
    assert bundle["plugins"]["clock_display_seconds"] == 10
    assert len(bundle["plugins"]["plugins"]) == 2


@pytest.mark.asyncio
async def test_export_empty_config_dir(tmp_path):
    """Export with no config files returns minimal bundle."""
    import zeclock.paths

    rest = _make_rest_remote(tmp_path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: tmp_path)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.get("/api/config/export")
            assert resp.status == 200
            data = await resp.json()

    assert data["success"] is True
    bundle = data["data"]
    assert bundle["_version"] == 1
    # No config or plugins keys expected when files don't exist
    assert "config" not in bundle
    assert "plugins" not in bundle


# --- POST /api/config/import ---


@pytest.mark.asyncio
async def test_import_restores_both_configs(tmp_path):
    """Import writes both zeclock.ini and plugins.yaml."""
    import zeclock.paths

    rest = _make_rest_remote(tmp_path)

    bundle = {
        "_version": 1,
        "config": {
            "zedmd": {"wifi_addr": "10.0.0.5", "brightness": "12"},
            "location": {"latitude": "45.0", "longitude": "5.7", "city_name": "Lyon"},
        },
        "plugins": {
            "default_plugin": "weather",
            "language": "en",
            "clock_display_seconds": 5,
            "plugins": [{"name": "weather", "frequency": 100, "settings": {}}],
        },
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: tmp_path)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.post("/api/config/import", json=bundle)
            assert resp.status == 200
            data = await resp.json()

    assert data["success"] is True
    assert "zeclock.ini" in data["message"]
    assert "plugins.yaml" in data["message"]

    # Verify zeclock.ini was written
    ini_path = tmp_path / "zeclock.ini"
    assert ini_path.exists()
    parser = configparser.RawConfigParser()
    parser.read(str(ini_path))
    assert parser.get("zedmd", "wifi_addr") == "10.0.0.5"
    assert parser.get("location", "city_name") == "Lyon"

    # Verify plugins.yaml was written
    plugins_path = tmp_path / "plugins.yaml"
    assert plugins_path.exists()
    with open(plugins_path) as f:
        plugins_data = yaml.safe_load(f)
    assert plugins_data["default_plugin"] == "weather"
    assert plugins_data["language"] == "en"
    assert len(plugins_data["plugins"]) == 1


@pytest.mark.asyncio
async def test_import_invalid_json(tmp_path):
    """Import with invalid JSON returns 400."""
    import zeclock.paths

    rest = _make_rest_remote(tmp_path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: tmp_path)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.post(
                "/api/config/import",
                data="not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            data = await resp.json()
            assert data["success"] is False


@pytest.mark.asyncio
async def test_import_empty_body(tmp_path):
    """Import with empty object returns 400 (no valid config found)."""
    import zeclock.paths

    rest = _make_rest_remote(tmp_path)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: tmp_path)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.post("/api/config/import", json={})
            assert resp.status == 400
            data = await resp.json()
            assert data["success"] is False
            assert "No valid configuration" in data["message"]


@pytest.mark.asyncio
async def test_import_only_plugins(tmp_path):
    """Import with only plugins section restores just plugins.yaml."""
    import zeclock.paths

    rest = _make_rest_remote(tmp_path)

    bundle = {
        "plugins": {
            "default_plugin": "clock",
            "clock_display_seconds": 3,
            "plugins": [],
        }
    }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: tmp_path)

        async with TestClient(TestServer(rest._app)) as client:
            resp = await client.post("/api/config/import", json=bundle)
            assert resp.status == 200
            data = await resp.json()

    assert data["success"] is True
    assert "plugins.yaml" in data["message"]
    assert "zeclock.ini" not in data["message"]

    # plugins.yaml exists, zeclock.ini does not
    assert (tmp_path / "plugins.yaml").exists()
    assert not (tmp_path / "zeclock.ini").exists()


@pytest.mark.asyncio
async def test_roundtrip_export_import(config_dir):
    """Exported settings can be imported back to recreate the same config."""
    import zeclock.paths

    rest = _make_rest_remote(config_dir)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(zeclock.paths, "get_config_dir", lambda: config_dir)

        async with TestClient(TestServer(rest._app)) as client:
            # Export
            export_resp = await client.get("/api/config/export")
            assert export_resp.status == 200
            export_data = await export_resp.json()
            bundle = export_data["data"]

            # Delete config files
            (config_dir / "zeclock.ini").unlink()
            (config_dir / "plugins.yaml").unlink()

            # Import
            import_resp = await client.post("/api/config/import", json=bundle)
            assert import_resp.status == 200

            # Export again and compare
            export_resp2 = await client.get("/api/config/export")
            export_data2 = await export_resp2.json()
            bundle2 = export_data2["data"]

    # The two bundles should match
    assert bundle["config"] == bundle2["config"]
    assert bundle["plugins"] == bundle2["plugins"]
