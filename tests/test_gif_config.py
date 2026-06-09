"""Tests for GifPlugin configuration schema and PluginNotConfiguredError.

Validates Requirement 6: Gif Plugin Configuration Guidance.
Tests cover:
- config_schema declares "gif_dir" field correctly
- PluginNotConfiguredError raised when gif_dir does not exist
- PluginNotConfiguredError raised when gif_dir contains zero .gif files
- Valid gif_dir with .gif files proceeds without error
"""

import pytest
from pathlib import Path

from zeclock.plugins.gif_plugin import GifPlugin
from zeclock.plugins.base import ConfigField, PluginNotConfiguredError


@pytest.fixture
def gif_plugin():
    """Create a fresh GifPlugin instance."""
    return GifPlugin()


class TestConfigSchema:
    """Tests for the config_schema property."""

    def test_config_schema_returns_list(self, gif_plugin):
        """config_schema should return a list."""
        schema = gif_plugin.config_schema
        assert isinstance(schema, list)

    def test_config_schema_has_gif_dir_field(self, gif_plugin):
        """config_schema should declare a 'gif_dir' field."""
        schema = gif_plugin.config_schema
        assert len(schema) == 1
        field = schema[0]
        assert isinstance(field, ConfigField)
        assert field.name == "gif_dir"

    def test_gif_dir_field_properties(self, gif_plugin):
        """The gif_dir field should have correct type and required flag."""
        field = gif_plugin.config_schema[0]
        assert field.field_type == "text"
        assert field.required is True
        assert field.label == "GIF Directory"
        assert len(field.description) > 0


class TestPluginNotConfiguredError:
    """Tests for PluginNotConfiguredError in initialize()."""

    @pytest.mark.asyncio
    async def test_raises_when_gif_dir_does_not_exist(self, gif_plugin, tmp_path):
        """Should raise PluginNotConfiguredError when gif_dir doesn't exist."""
        non_existent = str(tmp_path / "nonexistent_dir")
        config = {"gif_dir": non_existent}
        with pytest.raises(PluginNotConfiguredError):
            await gif_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_gif_dir_is_empty(self, gif_plugin, tmp_path):
        """Should raise PluginNotConfiguredError when gif_dir has no .gif files."""
        empty_dir = tmp_path / "empty_gifs"
        empty_dir.mkdir()
        config = {"gif_dir": str(empty_dir)}
        with pytest.raises(PluginNotConfiguredError):
            await gif_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_gif_dir_has_non_gif_files(self, gif_plugin, tmp_path):
        """Should raise PluginNotConfiguredError when dir has files but no .gif."""
        dir_with_files = tmp_path / "no_gifs"
        dir_with_files.mkdir()
        (dir_with_files / "image.png").write_bytes(b"fake png")
        (dir_with_files / "readme.txt").write_text("hello")
        config = {"gif_dir": str(dir_with_files)}
        with pytest.raises(PluginNotConfiguredError):
            await gif_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_default_dir_does_not_exist(
        self, gif_plugin, monkeypatch
    ):
        """Should raise PluginNotConfiguredError when no gif_dir and default doesn't exist."""
        # Monkeypatch DEFAULT_GIF_DIR to a non-existent path
        import zeclock.plugins.gif_plugin as gif_module

        monkeypatch.setattr(
            gif_module, "DEFAULT_GIF_DIR", Path("/tmp/nonexistent_zeclock_gif_test")
        )
        config = {}
        with pytest.raises(PluginNotConfiguredError):
            await gif_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_valid_gif_dir_does_not_raise(self, gif_plugin, tmp_path):
        """Should not raise when gif_dir exists and contains .gif files."""
        gif_dir = tmp_path / "gifs"
        gif_dir.mkdir()
        # Create a minimal valid GIF file (GIF89a header)
        gif_content = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
            b"\xff\xff\xff\x00\x00\x00"
            b"!\xf9\x04\x00\x00\x00\x00\x00"
            b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        )
        (gif_dir / "test.gif").write_bytes(gif_content)
        config = {"gif_dir": str(gif_dir)}
        # Should not raise - gif loading proceeds in background
        await gif_plugin.initialize(config)
