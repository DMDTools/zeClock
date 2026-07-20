"""Property-based tests for configuration round-trip.

Feature: plugin-system, Property 11: Configuration Round-Trip
Validates: Requirements 4.3
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from zeclock.plugin_config import PluginConfig

# Strategy for valid plugin names
plugin_name_st = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=30,
)

# Strategy for valid plugin entries
plugin_entry_st = st.fixed_dictionaries(
    {
        "name": plugin_name_st,
        "frequency": st.integers(min_value=0, max_value=100),
        "settings": st.dictionaries(
            keys=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=20
            ),
            values=st.one_of(
                st.text(min_size=0, max_size=50),
                st.integers(min_value=-1000, max_value=1000),
                st.floats(
                    min_value=-180.0,
                    max_value=180.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
                st.booleans(),
            ),
            max_size=5,
        ),
    }
)

# Strategy for valid config
config_st = st.fixed_dictionaries(
    {
        "clock_display_seconds": st.integers(min_value=1, max_value=300),
        "plugins": st.lists(plugin_entry_st, min_size=1, max_size=5),
    }
)


# --- Property-Based Tests ---


@given(config_st)
@settings(max_examples=100)
def test_config_roundtrip_preserves_structure(config_data: dict):
    """Serializing to YAML and parsing back produces equivalent config."""
    pytest.importorskip("yaml")
    import yaml

    # Ensure unique plugin names
    names = [e["name"] for e in config_data["plugins"]]
    assume(len(names) == len(set(names)))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f, default_flow_style=False)
        tmp_path = Path(f.name)

    try:
        plugin_config = PluginConfig(config_path=tmp_path)
        plugin_config.load()

        # Verify clock_display_seconds preserved
        assert (
            plugin_config.clock_display_seconds == config_data["clock_display_seconds"]
        )

        # Verify plugin entries preserved
        assert len(plugin_config.plugin_entries) == len(config_data["plugins"])

        for original, loaded in zip(
            config_data["plugins"], plugin_config.plugin_entries
        ):
            assert loaded["name"] == original["name"]
            assert loaded["frequency"] == original["frequency"]
            # Settings should be equivalent (YAML may change types slightly)
            assert loaded["settings"] == original["settings"]
    finally:
        tmp_path.unlink()


# --- Example-Based Tests ---


class TestConfigRoundtrip:
    """Example-based tests for config loading."""

    def test_default_config_created_when_missing(self):
        """When config file doesn't exist, defaults are used."""
        pytest.importorskip("yaml")

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent" / "plugins.yaml"
            config = PluginConfig(config_path=config_path)
            config.load()

            assert config.clock_display_seconds == 5
            assert config.default_plugin == "clock"
            assert len(config.plugin_entries) == 2
            assert config.plugin_entries[0]["name"] == "clock"
            assert config.plugin_entries[0]["frequency"] == 0
            assert config.plugin_entries[1]["name"] == "pinball"
            assert config.plugin_entries[1]["frequency"] == 100

    def test_invalid_yaml_falls_back_to_defaults(self):
        """Invalid YAML syntax triggers fallback to defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: [unclosed bracket")
            tmp_path = Path(f.name)

        try:
            config = PluginConfig(config_path=tmp_path)
            config.load()

            assert config.clock_display_seconds == 5
            assert config.default_plugin == "clock"
            assert len(config.plugin_entries) == 2
            assert config.plugin_entries[0]["name"] == "clock"
            assert config.plugin_entries[1]["name"] == "pinball"
        finally:
            tmp_path.unlink()

    def test_frequency_clamping_on_load(self):
        """Out-of-range frequencies are clamped during load."""
        pytest.importorskip("yaml")
        import yaml

        data = {
            "clock_display_seconds": 5,
            "plugins": [
                {"name": "test", "frequency": 150, "settings": {}},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = Path(f.name)

        try:
            config = PluginConfig(config_path=tmp_path)
            config.load()

            assert config.plugin_entries[0]["frequency"] == 100
        finally:
            tmp_path.unlink()

    def test_get_plugin_config(self):
        """get_plugin_config returns the correct settings dict."""
        pytest.importorskip("yaml")
        import yaml

        data = {
            "clock_display_seconds": 5,
            "plugins": [
                {
                    "name": "weather",
                    "frequency": 30,
                    "settings": {
                        "latitude": 48.85,
                        "longitude": 2.35,
                        "city_name": "Paris",
                    },
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            tmp_path = Path(f.name)

        try:
            config = PluginConfig(config_path=tmp_path)
            config.load()

            settings = config.get_plugin_config("weather")
            assert settings["latitude"] == 48.85
            assert settings["city_name"] == "Paris"

            # Unknown plugin inherits global language
            assert config.get_plugin_config("unknown") == {"language": "en"}
        finally:
            tmp_path.unlink()
