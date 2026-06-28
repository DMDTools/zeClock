"""Unit tests for automatic config schema validation in PluginManager."""

from typing import List, Optional

import pytest
from PIL import Image

from zeclock.plugin_manager import PluginManager
from zeclock.plugins.base import ClockPlugin, ConfigField


class RequiredFieldPlugin(ClockPlugin):
    """A plugin with a required config field (no default)."""

    @property
    def name(self) -> str:
        return "required-field"

    @property
    def description(self) -> str:
        return "Plugin requiring an api_key field"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    @property
    def config_schema(self) -> List[ConfigField]:
        return [
            ConfigField(
                name="api_key",
                label="API Key",
                field_type="text",
                required=True,
                description="Your API key",
                default=None,
            ),
        ]

    async def initialize(self, config: dict) -> None:
        self._api_key = config.get("api_key")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


class RequiredFieldWithDefaultPlugin(ClockPlugin):
    """A plugin with a required field that has a non-None default."""

    @property
    def name(self) -> str:
        return "required-with-default"

    @property
    def description(self) -> str:
        return "Plugin with required field that has default"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    @property
    def config_schema(self) -> List[ConfigField]:
        return [
            ConfigField(
                name="refresh_interval",
                label="Refresh Interval",
                field_type="number",
                required=True,
                description="Refresh interval in seconds",
                default=60,
            ),
        ]

    async def initialize(self, config: dict) -> None:
        self._interval = config.get("refresh_interval", 60)

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


class NoSchemaPlugin(ClockPlugin):
    """A plugin with no config_schema (empty list)."""

    @property
    def name(self) -> str:
        return "no-schema"

    @property
    def description(self) -> str:
        return "Plugin with no configuration schema"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    async def initialize(self, config: dict) -> None:
        pass

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


class MultipleFieldsPlugin(ClockPlugin):
    """A plugin with multiple config fields, some required some optional."""

    @property
    def name(self) -> str:
        return "multi-fields"

    @property
    def description(self) -> str:
        return "Plugin with multiple config fields"

    @property
    def frame_delay_ms(self) -> int:
        return 100

    @property
    def config_schema(self) -> List[ConfigField]:
        return [
            ConfigField(
                name="api_key",
                label="API Key",
                field_type="text",
                required=True,
                description="Required API key",
                default=None,
            ),
            ConfigField(
                name="city",
                label="City",
                field_type="city",
                required=False,
                description="Optional city name",
                default=None,
            ),
            ConfigField(
                name="units",
                label="Units",
                field_type="text",
                required=True,
                description="Temperature units",
                default="celsius",
            ),
        ]

    async def initialize(self, config: dict) -> None:
        self._api_key = config.get("api_key")

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        return Image.new("RGB", (width, height), (0, 0, 0))

    async def cleanup(self) -> None:
        pass


@pytest.fixture
def pm_no_settings(tmp_path):
    """PluginManager with no plugin settings configured."""
    config_path = tmp_path / "plugins.yaml"
    config_path.write_text(
        "plugins:\n"
        "  - name: required-field\n"
        "    frequency: 100\n"
        "    settings: {}\n"
    )
    pm = PluginManager(128, 32, config_path=config_path)
    pm.config.load()
    return pm


@pytest.fixture
def pm_with_api_key(tmp_path):
    """PluginManager with api_key setting present."""
    config_path = tmp_path / "plugins.yaml"
    config_path.write_text(
        "plugins:\n"
        "  - name: required-field\n"
        "    frequency: 100\n"
        "    settings:\n"
        "      api_key: my-secret-key\n"
    )
    pm = PluginManager(128, 32, config_path=config_path)
    pm.config.load()
    return pm


@pytest.fixture
def pm_empty(tmp_path):
    """PluginManager with empty config."""
    config_path = tmp_path / "plugins.yaml"
    config_path.write_text("plugins: []\n")
    pm = PluginManager(128, 32, config_path=config_path)
    pm.config.load()
    return pm


class TestAutoConfigValidation:
    """Tests for automatic config schema validation."""

    @pytest.mark.asyncio
    async def test_missing_required_field_marks_unconfigured(self, pm_no_settings):
        """Plugin with required field missing from settings is marked unconfigured."""
        plugin = RequiredFieldPlugin()
        pm_no_settings.registry.register(plugin, "builtin")

        result = await pm_no_settings.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is True
        assert pm_no_settings.active_plugin is plugin

    @pytest.mark.asyncio
    async def test_required_field_present_initializes_normally(self, pm_with_api_key):
        """Plugin with required field present initializes successfully."""
        plugin = RequiredFieldPlugin()
        pm_with_api_key.registry.register(plugin, "builtin")

        result = await pm_with_api_key.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is False

    @pytest.mark.asyncio
    async def test_required_field_with_default_passes_validation(self, pm_empty):
        """Plugin with required field that has a default passes even without settings."""
        plugin = RequiredFieldWithDefaultPlugin()
        pm_empty.registry.register(plugin, "builtin")

        result = await pm_empty.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is False

    @pytest.mark.asyncio
    async def test_no_schema_always_passes(self, pm_empty):
        """Plugin with empty config_schema always passes validation."""
        plugin = NoSchemaPlugin()
        pm_empty.registry.register(plugin, "builtin")

        result = await pm_empty.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is False

    @pytest.mark.asyncio
    async def test_multiple_fields_first_required_missing(self, pm_empty):
        """If first required field (no default) is missing, plugin is unconfigured."""
        plugin = MultipleFieldsPlugin()
        pm_empty.registry.register(plugin, "builtin")

        result = await pm_empty.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is True

    @pytest.mark.asyncio
    async def test_multiple_fields_all_required_present(self, tmp_path):
        """If all required fields without defaults are present, plugin initializes."""
        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            "plugins:\n"
            "  - name: multi-fields\n"
            "    frequency: 100\n"
            "    settings:\n"
            "      api_key: secret\n"
        )
        pm = PluginManager(128, 32, config_path=config_path)
        pm.config.load()

        plugin = MultipleFieldsPlugin()
        pm.registry.register(plugin, "builtin")

        result = await pm.activate_plugin(plugin)

        assert result is True
        assert plugin._unconfigured is False

    @pytest.mark.asyncio
    async def test_optional_field_missing_does_not_block(self, tmp_path):
        """Optional fields (required=False) missing do not block initialization."""
        config_path = tmp_path / "plugins.yaml"
        config_path.write_text(
            "plugins:\n"
            "  - name: multi-fields\n"
            "    frequency: 100\n"
            "    settings:\n"
            "      api_key: secret\n"
        )
        pm = PluginManager(128, 32, config_path=config_path)
        pm.config.load()

        plugin = MultipleFieldsPlugin()
        pm.registry.register(plugin, "builtin")

        result = await pm.activate_plugin(plugin)

        # city is optional and missing, but should not block
        assert result is True
        assert plugin._unconfigured is False

    @pytest.mark.asyncio
    async def test_validation_does_not_prevent_init_timeout_handling(self, tmp_path):
        """Plugins that pass validation but timeout in initialize are still handled."""
        import asyncio

        class SlowPlugin(ClockPlugin):
            @property
            def name(self) -> str:
                return "slow-plugin"

            @property
            def description(self) -> str:
                return "A plugin that takes forever to initialize"

            @property
            def frame_delay_ms(self) -> int:
                return 100

            @property
            def config_schema(self) -> List[ConfigField]:
                return []

            async def initialize(self, config: dict) -> None:
                await asyncio.sleep(100)

            async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
                return Image.new("RGB", (width, height), (0, 0, 0))

            async def cleanup(self) -> None:
                pass

        config_path = tmp_path / "plugins.yaml"
        config_path.write_text("plugins: []\n")
        pm = PluginManager(128, 32, config_path=config_path)
        pm.config.load()
        pm.init_timeout = 0.1  # Very short timeout for testing

        plugin = SlowPlugin()
        pm.registry.register(plugin, "builtin")

        result = await pm.activate_plugin(plugin)

        assert result is False
