"""StockPlugin - Displays stock prices and daily change on the DMD.

Fetches stock quotes from Yahoo Finance (no API key required) and
displays current price and daily change for configured symbols.
Shows up to 2 symbols per page, adding more pages if more symbols
are configured. Data is cached for 10 minutes.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import aiohttp
from PIL import Image

from .base import PagedPlugin
from .helpers import draw_staleness_indicator

logger = logging.getLogger(__name__)

# Default cache duration in seconds (10 minutes)
DEFAULT_CACHE_DURATION_SECONDS = 10 * 60

# Yahoo Finance quote API (no key required)
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass
class StockQuote:
    """Cached quote data for a single stock symbol."""

    symbol: str
    price: float  # regular market close price
    change: float  # day change (vs previous close)
    change_percent: float
    currency: str
    market_state: str = "CLOSED"  # OPEN, PRE, POST, CLOSED
    extended_price: float = 0.0  # pre/post market price (0 if not available)
    extended_change: float = 0.0  # change vs regular close
    extended_change_percent: float = 0.0
    intraday_prices: List[float] = field(default_factory=list)  # 1-min close prices
    trading_minutes: int = 390  # total regular session minutes (default US market)


@dataclass
class StockData:
    """Cached stock data for all configured symbols."""

    quotes: List[StockQuote]
    fetched_at: float = 0.0


class StockPlugin(PagedPlugin):
    """Displays stock prices and daily change on the DMD.

    Fetches data from Yahoo Finance (no API key or account required).
    Shows up to 2 symbols per page, with additional pages for more symbols.
    """

    @property
    def name(self) -> str:
        return "stock"

    @property
    def description(self) -> str:
        return "Stock prices and daily change display"

    # Class-level cache shared across activations
    _shared_cache: Optional["StockData"] = None

    @property
    def _cache(self) -> Optional["StockData"]:
        return StockPlugin._shared_cache

    @_cache.setter
    def _cache(self, value: Optional["StockData"]) -> None:
        StockPlugin._shared_cache = value

    def __init__(self) -> None:
        """Initialize StockPlugin with default state."""
        super().__init__()
        self._symbols: List[str] = []
        self._cache_duration_seconds: int = DEFAULT_CACHE_DURATION_SECONDS
        self._initialized: bool = False

    async def initialize(self, config: dict) -> None:
        """Initialize the plugin with configuration.

        Config keys:
            symbols (list): Stock ticker symbols, e.g. ["AAPL", "MSFT", "^FCHI"]
            page_duration_seconds (int): Duration per page 2-30s (default: 5)

        Args:
            config: Plugin-specific settings from plugins.yaml.
        """
        self._helpers = config.get("_helpers")

        # Read symbols configuration
        symbols = config.get("symbols", [])
        if not symbols:
            logger.warning("[stock] No symbols configured")
            self._initialized = False
            return

        # Normalize symbols to uppercase
        self._symbols = [s.upper().strip() for s in symbols if s.strip()]
        if not self._symbols:
            logger.warning("[stock] No valid symbols after filtering")
            self._initialized = False
            return

        # Read optional configuration
        page_duration = config.get("page_duration_seconds", 5)

        # Cache/refresh interval (default 10 minutes, minimum 5 minutes)
        refresh_minutes = config.get("refresh_minutes", 10)
        self._cache_duration_seconds = max(5 * 60, int(refresh_minutes) * 60)

        # Initialize paging (2 pages per symbol: info + graph)
        self._init_paging(
            total_pages=len(self._symbols) * 2,
            page_duration_seconds=page_duration,
            frame_delay_ms=100,
        )

        self._initialized = True

        # Fetch stock data
        await self._refresh_cache_if_needed()

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next stock frame with staleness indicator."""
        if not self._initialized or self._cache is None or not self._cache.quotes:
            return None

        # Get total frame index before PagedPlugin advances it
        total_idx = self._total_frame_index()

        frame = await super().render_frame(width, height)
        if frame is None:
            return None

        if self._is_cache_stale():
            draw_staleness_indicator(frame, total_idx, self._frame_delay_ms)

        return frame

    def render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a page showing stock info or intraday graph.

        Pages alternate: even pages show info, odd pages show the graph.
        """
        symbol_index = page // 2
        is_graph_page = (page % 2) == 1

        if is_graph_page:
            return self._render_graph_page(symbol_index, width, height)
        else:
            return self._render_page(symbol_index, width, height)

    async def cleanup(self) -> None:
        """Release resources."""
        await super().cleanup()

    def _is_cache_stale(self) -> bool:
        """Check if the cached stock data is older than the configured interval."""
        if self._cache is None:
            return True
        elapsed = time.time() - self._cache.fetched_at
        return elapsed >= self._cache_duration_seconds

    async def _refresh_cache_if_needed(self) -> None:
        """Fetch new stock data if cache is stale."""
        if not self._is_cache_stale():
            assert self._cache is not None
            age = int(time.time() - self._cache.fetched_at)
            logger.info("[stock] Using cached data (%ds old)", age)
            return

        logger.info("[stock] Cache stale or empty, fetching from Yahoo Finance")
        try:
            data = await self._fetch_stock_data()
            if data is not None:
                self._cache = data
                logger.info("[stock] Fetched %d quotes from API", len(data.quotes))
        except Exception as e:
            logger.warning("[stock] Failed to fetch stock data: %s", e)

    async def _fetch_stock_data(self) -> Optional[StockData]:
        """Fetch quotes for all configured symbols from Yahoo Finance.

        Fetches all symbols concurrently to minimize total latency.

        Returns:
            StockData instance with quotes, or None on complete failure.
        """
        quotes: List[StockQuote] = []

        try:
            async with aiohttp.ClientSession() as session:
                tasks = [
                    self._fetch_single_quote(session, symbol)
                    for symbol in self._symbols
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, StockQuote):
                        quotes.append(result)
                    elif isinstance(result, Exception):
                        logger.warning("[stock] Fetch error: %s", result)
        except Exception as e:
            logger.warning("[stock] Error during stock data fetch: %s", e)

        if not quotes:
            return None

        return StockData(quotes=quotes, fetched_at=time.time())

    async def _fetch_single_quote(
        self, session: aiohttp.ClientSession, symbol: str
    ) -> Optional[StockQuote]:
        """Fetch a single stock quote from Yahoo Finance chart API.

        Args:
            session: aiohttp session to reuse.
            symbol: Ticker symbol (e.g. "AAPL", "^FCHI", "BTC-USD").

        Returns:
            StockQuote or None on failure.
        """
        url = YAHOO_QUOTE_URL.format(symbol=symbol)
        params = {
            "interval": "1m",
            "range": "1d",
            "includePrePost": "true",
        }
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "[stock] Yahoo Finance returned %d for %s",
                        response.status,
                        symbol,
                    )
                    return None

                data = await response.json()
                return self._parse_chart_response(data, symbol)

        except aiohttp.ClientError as e:
            logger.warning("[stock] Request failed for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.warning("[stock] Unexpected error for %s: %s", symbol, e)
            return None

    def _parse_chart_response(self, data: dict, symbol: str) -> Optional[StockQuote]:
        """Parse Yahoo Finance chart API response.

        Args:
            data: Parsed JSON response.
            symbol: The requested symbol.

        Returns:
            StockQuote or None if response is malformed.
        """
        try:
            result = data["chart"]["result"][0]
            meta = result["meta"]

            current_price = meta["regularMarketPrice"]
            previous_close = meta.get(
                "chartPreviousClose", meta.get("previousClose", current_price)
            )
            currency = meta.get("currency", "USD")

            change = current_price - previous_close
            change_percent = (
                (change / previous_close * 100) if previous_close != 0 else 0.0
            )

            # Determine market state from currentTradingPeriod
            market_state = self._determine_market_state(meta)

            # Calculate total regular trading session minutes
            trading_minutes = self._get_trading_minutes(meta)

            # Get extended hours price (last data point if in pre/post market)
            extended_price = 0.0
            extended_change = 0.0
            extended_change_percent = 0.0

            if market_state in ("PRE", "POST"):
                closes = (
                    result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                )
                if closes:
                    # Find last non-None close
                    last_price = None
                    for c in reversed(closes):
                        if c is not None:
                            last_price = c
                            break
                    if last_price is not None and last_price != current_price:
                        extended_price = last_price
                        extended_change = last_price - current_price
                        extended_change_percent = (
                            (extended_change / current_price * 100)
                            if current_price != 0
                            else 0.0
                        )

            return StockQuote(
                symbol=symbol,
                price=current_price,
                change=change,
                change_percent=change_percent,
                currency=currency,
                market_state=market_state,
                extended_price=extended_price,
                extended_change=extended_change,
                extended_change_percent=extended_change_percent,
                intraday_prices=self._extract_intraday_prices(result),
                trading_minutes=trading_minutes,
            )

        except (KeyError, IndexError, TypeError, ZeroDivisionError) as e:
            logger.warning("[stock] Failed to parse response for %s: %s", symbol, e)
            return None

    def _determine_market_state(self, meta: dict) -> str:
        """Determine market state from currentTradingPeriod timestamps.

        Returns:
            One of: "OPEN", "PRE", "POST", "CLOSED"
        """
        ctp = meta.get("currentTradingPeriod")
        if not ctp:
            return "CLOSED"

        now = int(time.time())
        pre = ctp.get("pre", {})
        regular = ctp.get("regular", {})
        post = ctp.get("post", {})

        if regular.get("start", 0) <= now <= regular.get("end", 0):
            return "OPEN"
        elif pre.get("start", 0) <= now <= pre.get("end", 0):
            return "PRE"
        elif post.get("start", 0) <= now <= post.get("end", 0):
            return "POST"
        else:
            return "CLOSED"

    def _get_trading_minutes(self, meta: dict) -> int:
        """Get the total regular trading session duration in minutes.

        Falls back to 390 (US market 6.5h) if not available.

        Args:
            meta: The chart meta dict from Yahoo Finance.

        Returns:
            Total trading session minutes.
        """
        ctp = meta.get("currentTradingPeriod")
        if not ctp:
            return 390

        regular = ctp.get("regular", {})
        start = regular.get("start", 0)
        end = regular.get("end", 0)

        if start and end and end > start:
            return max(1, (end - start) // 60)

        return 390

    def _extract_intraday_prices(self, result: dict) -> List[float]:
        """Extract regular-session intraday close prices from chart API result.

        Only includes data points within the regular trading session
        (excludes pre-market and after-hours data). Uses timestamps from
        the API response to filter.

        Args:
            result: The chart result dict from Yahoo Finance.

        Returns:
            List of close prices for the regular session only (may be empty).
        """
        try:
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            timestamps = result.get("timestamp", [])

            # Get regular session boundaries
            meta = result.get("meta", {})
            ctp = meta.get("currentTradingPeriod", {})
            regular = ctp.get("regular", {})
            reg_start = regular.get("start", 0)
            reg_end = regular.get("end", 0)

            if not timestamps or not reg_start or not reg_end:
                # No timestamps or no session info — return all non-None closes
                return [float(c) for c in closes if c is not None]

            # Filter: only include prices within regular session
            prices: List[float] = []
            for i, ts in enumerate(timestamps):
                if i < len(closes) and closes[i] is not None:
                    if reg_start <= ts <= reg_end:
                        prices.append(float(closes[i]))

            return prices
        except (KeyError, IndexError, TypeError, ValueError):
            return []

    def _render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a page showing a single stock symbol.

        Layout scales proportionally for SD (128x32) and HD (256x64):
        - Line 1 (y=0): Ticker (MENU, yellow, left) + Price (MENU, orange, right)
        - Line 2 (y≈40%): Change + percent (SYSTEM font, green/red)
        - Line 3 (y≈75%): Extended hours if available (SYSTEM font)

        Args:
            page: Page index.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        frame = self._helpers.create_frame()

        # Get the quote for this page
        assert self._cache is not None
        if page >= len(self._cache.quotes):
            return frame

        quote = self._cache.quotes[page]

        # Scale factor
        sy = height / 32

        # Determine change color
        if quote.change >= 0:
            change_color: Tuple[int, int, int] = (0, 255, 80)
            sign = "+"
        else:
            change_color = (255, 50, 50)
            sign = "-"

        # Line 1: Ticker (MENU, yellow, left) + Price (MENU, orange, right)
        ticker = quote.symbol[:8]
        ticker_frame = self._helpers.render_text(
            ticker, x=1, y=0, color=(255, 200, 0), font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, ticker_frame)

        price_str = self._format_price(quote.price)
        price_frame = self._helpers.render_text_right_aligned(
            price_str, y=0, color=(255, 128, 0), font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, price_frame)

        # Format change strings
        change_val_str = f"{sign}{abs(quote.change):.2f}"
        change_pct_str = f"{sign}{abs(quote.change_percent):.1f}%"

        # Format extended hours strings
        has_ext = quote.extended_price > 0
        if has_ext:
            ext_sign = "+" if quote.extended_change >= 0 else "-"
            ext_color = (0, 200, 150) if quote.extended_change >= 0 else (200, 80, 80)
            ext_label = "AH " if quote.market_state == "POST" else "PM "
            ext_val_str = f"{ext_label}{quote.extended_price:.2f}"
            ext_pct_str = f"{ext_sign}{abs(quote.extended_change_percent):.1f}%"
        else:
            ext_val_str = ""
            ext_pct_str = ""
            ext_color = (0, 0, 0)

        # Align decimal points
        max_val_len = max(len(change_val_str), len(ext_val_str) if has_ext else 0)
        change_val_padded = change_val_str.rjust(max_val_len)
        max_pct_len = max(len(change_pct_str), len(ext_pct_str) if has_ext else 0)
        change_pct_padded = change_pct_str.rjust(max_pct_len)

        # Line 2: change (scaled y position)
        line2 = f"{change_val_padded} {change_pct_padded}"
        change_frame = self._helpers.render_text_right_aligned(
            line2, y=int(16 * sy), color=change_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, change_frame)

        # Line 3: extended hours (scaled y position)
        if has_ext:
            ext_val_padded = ext_val_str.rjust(max_val_len)
            ext_pct_padded = ext_pct_str.rjust(max_pct_len)
            line3 = f"{ext_val_padded} {ext_pct_padded}"
            ext_frame = self._helpers.render_text_right_aligned(
                line3, y=int(24 * sy), color=ext_color, font_name="SYSTEM"
            )
            frame = self._helpers.composite_frames(frame, ext_frame)

        return frame

    def _format_price(self, price: float) -> str:
        """Format a price for display on the DMD.

        Uses MENU font which only has: 0-9 A-Z & + - . / : < > (space)

        Args:
            price: The stock price.

        Returns:
            Formatted price string.
        """
        if price >= 10000:
            return f"{price:.0f}"
        elif price >= 1000:
            return f"{price:.1f}"
        elif price >= 100:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.2f}"
        else:
            # Sub-dollar (crypto, penny stocks)
            return f"{price:.4f}"

    def _render_graph_page(
        self, symbol_index: int, width: int, height: int
    ) -> Image.Image:
        """Render an intraday price graph for a stock symbol.

        Layout scales proportionally for SD and HD:
        - Top line: Ticker + price (SYSTEM font)
        - Graph area: Sparkline of intraday prices with previous close reference

        Args:
            symbol_index: Index into the quotes list.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode.
        """
        if self._helpers is None:
            return Image.new("RGB", (width, height), (0, 0, 0))

        frame = self._helpers.create_frame()

        assert self._cache is not None
        if symbol_index >= len(self._cache.quotes):
            return frame

        quote = self._cache.quotes[symbol_index]

        # Scale factor
        sy = height / 32

        # Determine color based on change direction
        if quote.change >= 0:
            graph_color: Tuple[int, int, int] = (0, 255, 80)
        else:
            graph_color = (255, 50, 50)

        # Top line: ticker + price (SYSTEM font)
        ticker = quote.symbol[:6]
        price_str = self._format_price(quote.price)
        header = f"{ticker} {price_str}"
        header_frame = self._helpers.render_text(
            header, x=1, y=0, color=(255, 200, 0), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, header_frame)

        # Graph area dimensions (scaled)
        graph_top = int(9 * sy)
        graph_bottom = height - 1
        graph_height = graph_bottom - graph_top
        graph_width = width - 2  # 1px margin each side
        graph_x_offset = 1

        # Draw the graph
        prices = quote.intraday_prices
        if len(prices) < 2:
            no_data_frame = self._helpers.render_text(
                "NO DATA",
                x=1,
                y=int(14 * sy),
                color=(128, 128, 128),
                font_name="SYSTEM",
            )
            frame = self._helpers.composite_frames(frame, no_data_frame)
            return frame

        # Scale X axis to full trading session
        total_minutes = max(1, quote.trading_minutes)
        elapsed_minutes = len(prices)

        if elapsed_minutes >= total_minutes:
            data_pixels = graph_width
        else:
            data_pixels = max(1, int(graph_width * elapsed_minutes / total_minutes))

        sampled = self._downsample_prices(prices, data_pixels)

        # Calculate Y range
        prev_close = quote.price - quote.change
        min_price = min(min(sampled), prev_close)
        max_price = max(max(sampled), prev_close)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = 1.0

        # Draw previous close reference line (dashed)
        ref_y = graph_bottom - int(
            (prev_close - min_price) / price_range * graph_height
        )
        pixels = frame.load()
        assert pixels is not None
        for x in range(graph_x_offset, graph_x_offset + graph_width):
            if x % 4 < 2:
                if 0 <= ref_y < height:
                    pixels[x, ref_y] = (80, 80, 80)

        # Draw the sparkline
        pixels = frame.load()
        assert pixels is not None

        for i in range(len(sampled)):
            y = graph_bottom - int(
                (sampled[i] - min_price) / price_range * graph_height
            )
            x = graph_x_offset + i
            y = max(graph_top, min(graph_bottom, y))

            if 0 <= x < width and 0 <= y < height:
                pixels[x, y] = graph_color

            if i > 0:
                prev_y = graph_bottom - int(
                    (sampled[i - 1] - min_price) / price_range * graph_height
                )
                prev_y = max(graph_top, min(graph_bottom, prev_y))
                prev_x = graph_x_offset + i - 1

                if abs(y - prev_y) > 1:
                    y_start = min(y, prev_y)
                    y_end = max(y, prev_y)
                    fill_x = x if x == prev_x + 1 else prev_x
                    for fy in range(y_start, y_end + 1):
                        if 0 <= fill_x < width and 0 <= fy < height:
                            pixels[fill_x, fy] = graph_color

        return frame

    @staticmethod
    def _downsample_prices(prices: List[float], target_width: int) -> List[float]:
        """Downsample a list of prices to fit a target pixel width.

        Uses simple averaging of bins. If prices are fewer than target_width,
        returns them as-is (graph will be narrower).

        Args:
            prices: Raw intraday price list.
            target_width: Number of horizontal pixels available.

        Returns:
            List of prices with at most target_width elements.
        """
        n = len(prices)
        if n <= target_width:
            return list(prices)

        # Bin prices into target_width buckets
        result: List[float] = []
        for i in range(target_width):
            start = int(i * n / target_width)
            end = int((i + 1) * n / target_width)
            if end <= start:
                end = start + 1
            bucket = prices[start:end]
            result.append(sum(bucket) / len(bucket))

        return result
