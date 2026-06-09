"""Tests for StockPlugin configuration schema and PluginNotConfiguredError.

Validates Requirement 5: Stock Plugin Configuration Guidance.
Tests cover:
- config_schema declares "symbols" field correctly
- PluginNotConfiguredError raised when symbols is missing
- PluginNotConfiguredError raised when symbols is None
- PluginNotConfiguredError raised when symbols is an empty list
- PluginNotConfiguredError raised when symbols contains only whitespace strings
- Valid symbols proceed without error
"""

import pytest
from unittest.mock import AsyncMock, patch

from zeclock.plugins.stock_plugin import StockPlugin
from zeclock.plugins.base import ConfigField, PluginNotConfiguredError


@pytest.fixture
def stock_plugin():
    """Create a fresh StockPlugin instance."""
    return StockPlugin()


class TestConfigSchema:
    """Tests for the config_schema property."""

    def test_config_schema_returns_list(self, stock_plugin):
        """config_schema should return a list."""
        schema = stock_plugin.config_schema
        assert isinstance(schema, list)

    def test_config_schema_has_symbols_field(self, stock_plugin):
        """config_schema should declare a 'symbols' field."""
        schema = stock_plugin.config_schema
        assert len(schema) == 1
        field = schema[0]
        assert isinstance(field, ConfigField)
        assert field.name == "symbols"

    def test_symbols_field_properties(self, stock_plugin):
        """The symbols field should have correct type and required flag."""
        field = stock_plugin.config_schema[0]
        assert field.field_type == "text"
        assert field.required is True
        assert field.label == "Stock Symbols"
        assert len(field.description) > 0


class TestPluginNotConfiguredError:
    """Tests for PluginNotConfiguredError in initialize()."""

    @pytest.mark.asyncio
    async def test_raises_when_symbols_missing(self, stock_plugin):
        """Should raise PluginNotConfiguredError when symbols key is absent."""
        config = {}
        with pytest.raises(PluginNotConfiguredError):
            await stock_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_symbols_is_none(self, stock_plugin):
        """Should raise PluginNotConfiguredError when symbols is None."""
        config = {"symbols": None}
        with pytest.raises(PluginNotConfiguredError):
            await stock_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_symbols_is_empty_list(self, stock_plugin):
        """Should raise PluginNotConfiguredError when symbols is []."""
        config = {"symbols": []}
        with pytest.raises(PluginNotConfiguredError):
            await stock_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_symbols_all_whitespace(self, stock_plugin):
        """Should raise PluginNotConfiguredError when all symbols are whitespace."""
        config = {"symbols": ["   ", "\t", ""]}
        with pytest.raises(PluginNotConfiguredError):
            await stock_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_raises_when_symbols_all_empty_strings(self, stock_plugin):
        """Should raise PluginNotConfiguredError when all symbols are empty strings."""
        config = {"symbols": ["", "", ""]}
        with pytest.raises(PluginNotConfiguredError):
            await stock_plugin.initialize(config)

    @pytest.mark.asyncio
    async def test_valid_symbols_does_not_raise(self, stock_plugin):
        """Should not raise when valid symbols are provided."""
        config = {"symbols": ["AAPL", "MSFT"]}
        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)
        # Should reach here without error
        assert stock_plugin._initialized is True

    @pytest.mark.asyncio
    async def test_mixed_valid_and_whitespace_does_not_raise(self, stock_plugin):
        """Should not raise when at least one valid symbol exists among whitespace."""
        config = {"symbols": ["  ", "AAPL", ""]}
        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)
        assert stock_plugin._initialized is True
        assert stock_plugin._symbols == ["AAPL"]
