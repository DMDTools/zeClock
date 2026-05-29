"""Tests for stock plugin intraday graph feature.

Tests cover:
- Graph page rendering with valid intraday data
- Graph page rendering with insufficient data (< 2 points)
- Downsampling of price data to fit display width
- Page alternation (info page, graph page, info page, graph page...)
- Graph color matches change direction (green up, red down)
- Previous close reference line positioning
- Edge cases: flat prices, single data point, many data points
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from zeclock.plugins.stock_plugin import StockPlugin, StockQuote, StockData


@pytest.fixture
def stock_plugin():
    """Create a fresh StockPlugin instance."""
    return StockPlugin()


def make_quote(
    symbol: str = "AAPL",
    price: float = 150.0,
    change: float = 2.5,
    change_percent: float = 1.7,
    intraday_prices: list = None,
    trading_minutes: int = 390,
) -> StockQuote:
    """Create a StockQuote with optional intraday prices."""
    if intraday_prices is None:
        # Generate a simple upward trend
        intraday_prices = [147.0 + i * 0.01 for i in range(390)]
    return StockQuote(
        symbol=symbol,
        price=price,
        change=change,
        change_percent=change_percent,
        currency="USD",
        market_state="OPEN",
        intraday_prices=intraday_prices,
        trading_minutes=trading_minutes,
    )


def make_helpers_mock():
    """Create a mock PluginHelpers that returns real PIL images."""
    helpers = MagicMock()
    helpers.create_frame.return_value = Image.new("RGB", (128, 32), (0, 0, 0))

    def render_text_side_effect(
        text, x=0, y=0, color=(255, 128, 0), font_name="STANDARD"
    ):
        return Image.new("RGB", (128, 32), (0, 0, 0))

    def render_text_right_aligned_side_effect(
        text, y=0, margin=1, color=(255, 128, 0), font_name="STANDARD"
    ):
        return Image.new("RGB", (128, 32), (0, 0, 0))

    def composite_side_effect(bg, fg):
        # Simple composite: just return bg (tests check pixel-level for graph)
        return bg

    helpers.render_text.side_effect = render_text_side_effect
    helpers.render_text_right_aligned.side_effect = (
        render_text_right_aligned_side_effect
    )
    helpers.composite_frames.side_effect = composite_side_effect
    return helpers


class TestPageAlternation:
    """Test that pages alternate between info and graph."""

    @pytest.mark.asyncio
    async def test_two_pages_per_symbol(self, stock_plugin):
        """Each symbol should produce 2 pages: info + graph."""
        config = {
            "symbols": ["AAPL", "MSFT"],
            "page_duration_seconds": 2,
            "_helpers": make_helpers_mock(),
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # 2 symbols * 2 pages each = 4 total pages
        assert stock_plugin._total_pages == 4

    @pytest.mark.asyncio
    async def test_single_symbol_two_pages(self, stock_plugin):
        """A single symbol should produce 2 pages."""
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": make_helpers_mock(),
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        assert stock_plugin._total_pages == 2

    @pytest.mark.asyncio
    async def test_render_page_dispatches_correctly(self, stock_plugin):
        """Even pages render info, odd pages render graph."""
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": make_helpers_mock(),
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        stock_plugin._cache = StockData(quotes=[make_quote()], fetched_at=time.time())

        with (
            patch.object(stock_plugin, "_render_page") as mock_info,
            patch.object(stock_plugin, "_render_graph_page") as mock_graph,
        ):
            mock_info.return_value = Image.new("RGB", (128, 32))
            mock_graph.return_value = Image.new("RGB", (128, 32))

            # Page 0 → info (symbol_index=0)
            stock_plugin.render_page(0, 128, 32)
            mock_info.assert_called_once_with(0, 128, 32)
            mock_graph.assert_not_called()

            mock_info.reset_mock()

            # Page 1 → graph (symbol_index=0)
            stock_plugin.render_page(1, 128, 32)
            mock_graph.assert_called_once_with(0, 128, 32)
            mock_info.assert_not_called()


class TestGraphRendering:
    """Test the graph page rendering."""

    @pytest.mark.asyncio
    async def test_graph_returns_valid_image(self, stock_plugin):
        """Graph page should return a valid 128x32 RGB image."""
        helpers = make_helpers_mock()
        # Override composite to actually return the frame for pixel testing
        helpers.composite_frames.side_effect = lambda bg, fg: bg

        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        stock_plugin._cache = StockData(quotes=[make_quote()], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        assert isinstance(frame, Image.Image)
        assert frame.mode == "RGB"
        assert frame.size == (128, 32)

    @pytest.mark.asyncio
    async def test_graph_with_no_data_shows_message(self, stock_plugin):
        """Graph with < 2 data points should show NO DATA."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # Quote with only 1 price point
        quote = make_quote(intraday_prices=[150.0])
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        stock_plugin._render_graph_page(0, 128, 32)

        # Should have called render_text with "NO DATA"
        calls = helpers.render_text.call_args_list
        no_data_calls = [c for c in calls if "NO DATA" in str(c)]
        assert len(no_data_calls) > 0

    @pytest.mark.asyncio
    async def test_graph_with_empty_data(self, stock_plugin):
        """Graph with empty price list should show NO DATA."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        quote = make_quote(intraday_prices=[])
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        stock_plugin._render_graph_page(0, 128, 32)

        calls = helpers.render_text.call_args_list
        no_data_calls = [c for c in calls if "NO DATA" in str(c)]
        assert len(no_data_calls) > 0

    @pytest.mark.asyncio
    async def test_graph_draws_pixels_for_valid_data(self, stock_plugin):
        """Graph with valid data should draw non-black pixels in graph area."""
        # Use a real frame (not mocked composite) to check pixels
        helpers = make_helpers_mock()

        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # Create a quote with a clear upward trend
        prices = [100.0 + i * 0.5 for i in range(100)]
        quote = make_quote(price=149.5, change=49.5, intraday_prices=prices)
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Check that some pixels in the graph area (y=9 to y=31) are non-black
        non_black_count = 0
        for y in range(9, 32):
            for x in range(1, 127):
                if pixels[x, y] != (0, 0, 0):
                    non_black_count += 1

        assert non_black_count > 0, "Graph should draw visible pixels"

    @pytest.mark.asyncio
    async def test_graph_green_when_positive_change(self, stock_plugin):
        """Graph line should be green when stock is up."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        prices = [100.0 + i * 0.1 for i in range(50)]
        quote = make_quote(price=105.0, change=5.0, intraday_prices=prices)
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Find green pixels in graph area
        green_pixels = []
        for y in range(9, 32):
            for x in range(1, 127):
                r, g, b = pixels[x, y]
                if g > r and g > b and g > 100:
                    green_pixels.append((x, y))

        assert len(green_pixels) > 0, "Positive change should draw green graph"

    @pytest.mark.asyncio
    async def test_graph_red_when_negative_change(self, stock_plugin):
        """Graph line should be red when stock is down."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        prices = [105.0 - i * 0.1 for i in range(50)]
        quote = make_quote(price=100.0, change=-5.0, intraday_prices=prices)
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Find red pixels in graph area
        red_pixels = []
        for y in range(9, 32):
            for x in range(1, 127):
                r, g, b = pixels[x, y]
                if r > g and r > b and r > 100:
                    red_pixels.append((x, y))

        assert len(red_pixels) > 0, "Negative change should draw red graph"


class TestGraphReferenceLine:
    """Test the previous close reference line."""

    @pytest.mark.asyncio
    async def test_reference_line_always_drawn(self, stock_plugin):
        """Reference line should always appear, even with gap up/down."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # Gap down: prev_close (110) is above all intraday prices (100-109.75)
        prices = [100.0 + i * 0.025 for i in range(390)]
        quote = make_quote(
            price=109.75, change=-0.25, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Look for gray pixels (reference line color is (80, 80, 80))
        gray_pixels = []
        for y in range(9, 32):
            for x in range(1, 127):
                if pixels[x, y] == (80, 80, 80):
                    gray_pixels.append((x, y))

        assert len(gray_pixels) > 0, "Reference line should always be drawn"

    @pytest.mark.asyncio
    async def test_reference_line_is_dashed(self, stock_plugin):
        """Reference line should have a dashed pattern (not solid)."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # prev_close = 105 is in the middle of range [100, 109.75]
        prices = [100.0 + i * 0.025 for i in range(390)]
        quote = make_quote(
            price=110.0, change=5.0, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Find the Y coordinate of the reference line
        gray_ys = set()
        for y in range(9, 32):
            for x in range(1, 127):
                if pixels[x, y] == (80, 80, 80):
                    gray_ys.add(y)

        if gray_ys:
            ref_y = list(gray_ys)[0]
            # Check that not all x positions have the gray pixel (dashed)
            gray_xs = [x for x in range(1, 127) if pixels[x, ref_y] == (80, 80, 80)]
            # Dashed pattern: x % 4 < 2, so roughly half should be drawn
            assert len(gray_xs) < 100, "Line should be dashed, not solid"
            assert len(gray_xs) > 20, "Line should have enough dashes to be visible"


class TestDownsampling:
    """Test the price downsampling logic."""

    def test_fewer_prices_than_width_returns_as_is(self):
        """If prices fit in width, return them unchanged."""
        prices = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = StockPlugin._downsample_prices(prices, 126)
        assert result == prices

    def test_exact_width_returns_as_is(self):
        """If prices exactly match width, return them unchanged."""
        prices = [float(i) for i in range(126)]
        result = StockPlugin._downsample_prices(prices, 126)
        assert result == prices

    def test_more_prices_than_width_downsamples(self):
        """If prices exceed width, downsample to target width."""
        prices = [float(i) for i in range(390)]  # typical trading day
        result = StockPlugin._downsample_prices(prices, 126)
        assert len(result) == 126

    def test_downsampled_preserves_trend(self):
        """Downsampled data should preserve the overall trend direction."""
        # Upward trend
        prices = [100.0 + i * 0.1 for i in range(500)]
        result = StockPlugin._downsample_prices(prices, 50)
        assert len(result) == 50
        # First value should be less than last
        assert result[0] < result[-1]

    def test_downsampled_preserves_range(self):
        """Downsampled min/max should be close to original min/max."""
        prices = [100.0 + i * 0.5 for i in range(400)]
        result = StockPlugin._downsample_prices(prices, 100)
        # Averages won't hit exact min/max but should be close
        assert min(result) >= min(prices)
        assert max(result) <= max(prices)

    def test_empty_list(self):
        """Empty price list should return empty."""
        result = StockPlugin._downsample_prices([], 126)
        assert result == []

    def test_single_price(self):
        """Single price should return as-is."""
        result = StockPlugin._downsample_prices([42.0], 126)
        assert result == [42.0]


class TestIntradayPricesExtraction:
    """Test that intraday prices are correctly extracted from API response."""

    def test_extract_intraday_prices_valid(self, stock_plugin):
        """Should extract only regular-session close prices."""
        reg_start = 1700000000
        reg_end = reg_start + 390 * 60
        result = {
            "meta": {
                "currentTradingPeriod": {
                    "regular": {"start": reg_start, "end": reg_end}
                }
            },
            "timestamp": [
                reg_start - 60,  # pre-market (excluded)
                reg_start,  # regular
                reg_start + 60,  # regular
                reg_start + 120,  # regular (None close)
                reg_start + 180,  # regular
                reg_end + 60,  # post-market (excluded)
            ],
            "indicators": {
                "quote": [{"close": [99.0, 100.0, 101.0, None, 102.0, 103.0]}]
            },
        }
        prices = stock_plugin._extract_intraday_prices(result)
        # pre-market (99.0) excluded, None excluded, post-market (103.0) excluded
        assert prices == [100.0, 101.0, 102.0]

    def test_extract_intraday_prices_no_timestamps_fallback(self, stock_plugin):
        """Should return all non-None closes when no timestamps available."""
        result = {
            "meta": {},
            "indicators": {"quote": [{"close": [100.0, 101.0, None, 102.0]}]},
        }
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == [100.0, 101.0, 102.0]

    def test_extract_intraday_prices_empty_closes(self, stock_plugin):
        """Should return empty list when closes are empty."""
        result = {
            "meta": {"currentTradingPeriod": {"regular": {"start": 1000, "end": 2000}}},
            "timestamp": [],
            "indicators": {"quote": [{"close": []}]},
        }
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == []

    def test_extract_intraday_prices_missing_indicators(self, stock_plugin):
        """Should return empty list when indicators are missing."""
        result = {}
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == []

    def test_extract_intraday_prices_all_none(self, stock_plugin):
        """Should return empty list when all closes are None."""
        reg_start = 1700000000
        result = {
            "meta": {
                "currentTradingPeriod": {
                    "regular": {"start": reg_start, "end": reg_start + 390 * 60}
                }
            },
            "timestamp": [reg_start, reg_start + 60, reg_start + 120],
            "indicators": {"quote": [{"close": [None, None, None]}]},
        }
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == []

    def test_extract_excludes_premarket_data(self, stock_plugin):
        """Pre-market data points should be excluded."""
        reg_start = 1700000000
        reg_end = reg_start + 390 * 60
        result = {
            "meta": {
                "currentTradingPeriod": {
                    "regular": {"start": reg_start, "end": reg_end}
                }
            },
            "timestamp": [
                reg_start - 300,  # pre-market
                reg_start - 240,  # pre-market
                reg_start - 180,  # pre-market
                reg_start,  # regular
                reg_start + 60,  # regular
            ],
            "indicators": {"quote": [{"close": [95.0, 96.0, 97.0, 100.0, 101.0]}]},
        }
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == [100.0, 101.0]

    def test_extract_excludes_postmarket_data(self, stock_plugin):
        """Post-market data points should be excluded."""
        reg_start = 1700000000
        reg_end = reg_start + 390 * 60
        result = {
            "meta": {
                "currentTradingPeriod": {
                    "regular": {"start": reg_start, "end": reg_end}
                }
            },
            "timestamp": [
                reg_start,  # regular
                reg_start + 60,  # regular
                reg_end + 60,  # post-market
                reg_end + 120,  # post-market
            ],
            "indicators": {"quote": [{"close": [100.0, 101.0, 105.0, 106.0]}]},
        }
        prices = stock_plugin._extract_intraday_prices(result)
        assert prices == [100.0, 101.0]


class TestGraphEdgeCases:
    """Test edge cases in graph rendering."""

    @pytest.mark.asyncio
    async def test_flat_prices_renders_without_error(self, stock_plugin):
        """Flat prices (no range) should render without division by zero."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # All prices the same
        prices = [150.0] * 100
        quote = make_quote(price=150.0, change=0.0, intraday_prices=prices)
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        # Should not raise
        frame = stock_plugin._render_graph_page(0, 128, 32)
        assert isinstance(frame, Image.Image)

    @pytest.mark.asyncio
    async def test_two_data_points_renders(self, stock_plugin):
        """Minimum valid data (2 points) should render a graph."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        prices = [100.0, 105.0]
        quote = make_quote(price=105.0, change=5.0, intraday_prices=prices)
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        assert isinstance(frame, Image.Image)
        assert frame.size == (128, 32)

    @pytest.mark.asyncio
    async def test_invalid_symbol_index_returns_blank(self, stock_plugin):
        """Out-of-range symbol index should return blank frame."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        stock_plugin._cache = StockData(quotes=[make_quote()], fetched_at=time.time())

        # Index 5 is out of range (only 1 quote)
        frame = stock_plugin._render_graph_page(5, 128, 32)
        assert isinstance(frame, Image.Image)


class TestProportionalGraph:
    """Test that the graph X-axis is proportional to the full trading day."""

    @pytest.mark.asyncio
    async def test_half_day_data_uses_half_width(self, stock_plugin):
        """With half the trading day elapsed, graph should only fill ~half the width."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # 195 minutes of data out of 390 total = half day
        prices = [100.0 + i * 0.05 for i in range(195)]
        quote = make_quote(
            price=109.75, change=9.75, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Graph area: x from 1 to 126 (width=126 pixels)
        # Half day → data should occupy ~63 pixels (x=1 to x=63)
        # Right half (x=64 to x=126) should be mostly empty (only ref line)

        # Count non-black, non-gray pixels in left half vs right half
        left_colored = 0
        right_colored = 0
        midpoint = 1 + 63  # graph starts at x=1, half is at x=64

        for y in range(9, 32):
            for x in range(1, midpoint):
                r, g, b = pixels[x, y]
                if (r, g, b) != (0, 0, 0) and (r, g, b) != (80, 80, 80):
                    left_colored += 1
            for x in range(midpoint, 127):
                r, g, b = pixels[x, y]
                if (r, g, b) != (0, 0, 0) and (r, g, b) != (80, 80, 80):
                    right_colored += 1

        assert left_colored > 0, "Left half should have graph data"
        assert right_colored == 0, "Right half should be empty (market still open)"

    @pytest.mark.asyncio
    async def test_full_day_data_uses_full_width(self, stock_plugin):
        """With full trading day data, graph should fill the entire width."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # Full 390 minutes of data
        prices = [100.0 + i * 0.05 for i in range(390)]
        quote = make_quote(
            price=119.45, change=19.45, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # With full data, the rightmost area should also have graph pixels
        right_quarter_colored = 0
        for y in range(9, 32):
            for x in range(96, 127):  # last quarter
                r, g, b = pixels[x, y]
                if (r, g, b) != (0, 0, 0) and (r, g, b) != (80, 80, 80):
                    right_quarter_colored += 1

        assert right_quarter_colored > 0, "Full day data should fill right side too"

    @pytest.mark.asyncio
    async def test_quarter_day_data_leaves_three_quarters_empty(self, stock_plugin):
        """With 25% of trading day elapsed, right 75% should be empty."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # 97 minutes out of 390 ≈ 25%
        prices = [100.0 + i * 0.1 for i in range(97)]
        quote = make_quote(
            price=109.6, change=9.6, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # 25% of 126 pixels ≈ 31 pixels. Check that x > 35 has no graph data
        far_right_colored = 0
        for y in range(9, 32):
            for x in range(40, 127):
                r, g, b = pixels[x, y]
                if (r, g, b) != (0, 0, 0) and (r, g, b) != (80, 80, 80):
                    far_right_colored += 1

        assert far_right_colored == 0, "Right 75% should be empty with only 25% data"

    @pytest.mark.asyncio
    async def test_reference_line_spans_full_width(self, stock_plugin):
        """The previous close reference line should span the full graph width."""
        helpers = make_helpers_mock()
        config = {
            "symbols": ["AAPL"],
            "page_duration_seconds": 2,
            "_helpers": helpers,
        }

        with patch.object(
            stock_plugin, "_refresh_cache_if_needed", new_callable=AsyncMock
        ):
            await stock_plugin.initialize(config)

        # Half day data, prev_close=105 is in the middle of [100, 109.75]
        prices = [100.0 + i * 0.05 for i in range(195)]
        quote = make_quote(
            price=115.0, change=10.0, intraday_prices=prices, trading_minutes=390
        )
        stock_plugin._cache = StockData(quotes=[quote], fetched_at=time.time())

        frame = stock_plugin._render_graph_page(0, 128, 32)
        pixels = frame.load()

        # Find gray pixels (reference line) in the right half
        right_gray = 0
        for y in range(9, 32):
            for x in range(64, 127):
                if pixels[x, y] == (80, 80, 80):
                    right_gray += 1

        assert right_gray > 0, "Reference line should extend into the empty right half"


class TestTradingMinutes:
    """Test the _get_trading_minutes helper."""

    def test_us_market_default(self, stock_plugin):
        """Should return 390 when no currentTradingPeriod."""
        meta = {}
        assert stock_plugin._get_trading_minutes(meta) == 390

    def test_us_market_from_timestamps(self, stock_plugin):
        """Should calculate minutes from regular start/end."""
        # 9:30 to 16:00 = 6.5 hours = 390 minutes
        meta = {
            "currentTradingPeriod": {
                "regular": {
                    "start": 1700000000,
                    "end": 1700000000 + 390 * 60,
                }
            }
        }
        assert stock_plugin._get_trading_minutes(meta) == 390

    def test_european_market_8h(self, stock_plugin):
        """European markets often trade 8.5 hours = 510 minutes."""
        meta = {
            "currentTradingPeriod": {
                "regular": {
                    "start": 1700000000,
                    "end": 1700000000 + 510 * 60,
                }
            }
        }
        assert stock_plugin._get_trading_minutes(meta) == 510

    def test_crypto_24h(self, stock_plugin):
        """Crypto markets trade 24h = 1440 minutes."""
        meta = {
            "currentTradingPeriod": {
                "regular": {
                    "start": 1700000000,
                    "end": 1700000000 + 1440 * 60,
                }
            }
        }
        assert stock_plugin._get_trading_minutes(meta) == 1440

    def test_missing_regular_period(self, stock_plugin):
        """Should fall back to 390 if regular period is missing."""
        meta = {"currentTradingPeriod": {"pre": {}, "post": {}}}
        assert stock_plugin._get_trading_minutes(meta) == 390
