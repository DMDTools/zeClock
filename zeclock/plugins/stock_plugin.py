"""StockPlugin - Displays stock prices and daily change on the DMD.

Fetches stock quotes from Yahoo Finance (no API key required) and
displays current price and daily change for configured symbols.
Shows up to 2 symbols per page, adding more pages if more symbols
are configured. Data is cached for 10 minutes.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import aiohttp
from PIL import Image

from .base import ClockPlugin

logger = logging.getLogger(__name__)

# Default cache duration in seconds (10 minutes)
DEFAULT_CACHE_DURATION_SECONDS = 10 * 60

# Yahoo Finance quote API (no key required)
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass
class StockQuote:
    """Cached quote data for a single stock symbol."""

    symbol: str
    price: float
    change: float
    change_percent: float
    currency: str


@dataclass
class StockData:
    """Cached stock data for all configured symbols."""

    quotes: List[StockQuote]
    fetched_at: float = 0.0


class StockPlugin(ClockPlugin):
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

    @property
    def frame_delay_ms(self) -> int:
        return self._frame_delay_ms

    # Class-level cache shared across activations
    _shared_cache: Optional["StockData"] = None

    @property
    def _cache(self) -> Optional["StockData"]:
        return StockPlugin._shared_cache

    @_cache.setter
    def _cache(self, value: Optional["StockData"]) -> None:
        StockPlugin._shared_cache = value

    def __init__(self):
        """Initialize StockPlugin with default state."""
        self._frame_delay_ms: int = 100  # 10 FPS
        self._symbols: List[str] = []
        self._page_duration_seconds: int = 5
        self._cache_duration_seconds: int = DEFAULT_CACHE_DURATION_SECONDS
        self._current_page: int = 0
        self._frame_count: int = 0
        self._frames_per_page: int = 0
        self._total_pages: int = 0
        self._helpers = None
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
        self._page_duration_seconds = max(2, min(30, int(page_duration)))

        # Cache/refresh interval (default 10 minutes, minimum 5 minutes)
        refresh_minutes = config.get("refresh_minutes", 10)
        self._cache_duration_seconds = max(5 * 60, int(refresh_minutes) * 60)

        # Calculate frames per page
        self._frames_per_page = (
            self._page_duration_seconds * 1000 + self._frame_delay_ms - 1
        ) // self._frame_delay_ms

        # Calculate total pages (1 symbol per page)
        self._total_pages = len(self._symbols)

        self._current_page = 0
        self._frame_count = 0
        self._initialized = True

        # Fetch stock data
        await self._refresh_cache_if_needed()

    async def render_frame(self, width: int, height: int) -> Optional[Image.Image]:
        """Render the next stock frame.

        Shows up to 2 symbols per page with price and change.
        Returns None after all pages are displayed.

        Args:
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            PIL Image in RGB mode, or None to signal completion.
        """
        if not self._initialized:
            return None

        if self._cache is None or not self._cache.quotes:
            logger.warning("[stock] No stock data available - signaling completion")
            return None

        # All pages displayed? Signal completion.
        if self._current_page >= self._total_pages:
            return None

        if self._current_page == 0 and self._frame_count == 0:
            logger.info("[stock] Start rendering")

        # Render current page
        frame = self._render_page(self._current_page, width, height)

        # Add staleness indicator if cache is stale
        if self._is_cache_stale():
            self._draw_staleness_indicator(frame, width, height)

        # Advance frame counter
        self._frame_count += 1
        if self._frame_count >= self._frames_per_page:
            self._frame_count = 0
            self._current_page += 1

        return frame

    async def cleanup(self) -> None:
        """Release resources."""
        self._current_page = 0
        self._frame_count = 0

    def _is_cache_stale(self) -> bool:
        """Check if the cached stock data is older than the configured interval."""
        if self._cache is None:
            return True
        elapsed = time.time() - self._cache.fetched_at
        return elapsed >= self._cache_duration_seconds

    async def _refresh_cache_if_needed(self) -> None:
        """Fetch new stock data if cache is stale."""
        if not self._is_cache_stale():
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
            "interval": "1d",
            "range": "2d",
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }

        try:
            async with session.get(
                url, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    logger.warning(
                        "[stock] Yahoo Finance returned %d for %s",
                        response.status, symbol,
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

    def _parse_chart_response(
        self, data: dict, symbol: str
    ) -> Optional[StockQuote]:
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
            previous_close = meta.get("chartPreviousClose", meta.get("previousClose", current_price))
            currency = meta.get("currency", "USD")

            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else 0.0

            return StockQuote(
                symbol=symbol,
                price=current_price,
                change=change,
                change_percent=change_percent,
                currency=currency,
            )

        except (KeyError, IndexError, TypeError, ZeroDivisionError) as e:
            logger.warning("[stock] Failed to parse response for %s: %s", symbol, e)
            return None

    def _render_page(self, page: int, width: int, height: int) -> Image.Image:
        """Render a page showing a single stock symbol.

        Layout (full 32px height):
        - Line 1 (y=0): Ticker symbol (MENU font, yellow)
        - Line 2 (y=12): Price (MENU font, orange)
        - Line 3 (y=25): Change + percent (SYSTEM font, green/red)

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
        if page >= len(self._cache.quotes):
            return frame

        quote = self._cache.quotes[page]

        # Determine change color
        if quote.change >= 0:
            change_color: Tuple[int, int, int] = (0, 255, 80)
            sign = "+"
        else:
            change_color = (255, 50, 50)
            sign = ""

        # Line 1: Ticker (MENU, yellow, left) + Price (MENU, orange, right)
        ticker = quote.symbol[:8]
        ticker_frame = self._helpers.render_text(
            ticker, x=1, y=0, color=(255, 200, 0), font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, ticker_frame)

        price_str = self._format_price(quote.price)
        price_width = self._helpers.get_text_width(price_str, font_name="MENU")
        price_x = width - price_width - 1
        price_frame = self._helpers.render_text(
            price_str, x=price_x, y=0, color=(255, 128, 0), font_name="MENU"
        )
        frame = self._helpers.composite_frames(frame, price_frame)

        # Line 2: Currency (SYSTEM, dim white, left)
        currency = quote.currency[:3].upper()
        currency_frame = self._helpers.render_text(
            currency, x=1, y=13, color=(150, 150, 150), font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, currency_frame)

        # Line 3: Change + percent (SYSTEM font, green/red)
        change_str = f"{sign}{quote.change:+.2f}"
        change_str = change_str.replace("++", "+").replace("+-", "-")
        pct_str = f"{sign}{quote.change_percent:+.1f}%"
        pct_str = pct_str.replace("++", "+").replace("+-", "-")
        change_line = f"{change_str} ({pct_str})"

        if self._helpers.get_text_width(change_line, font_name="SYSTEM") > width - 2:
            change_line = pct_str

        change_frame = self._helpers.render_text(
            change_line, x=1, y=25, color=change_color, font_name="SYSTEM"
        )
        frame = self._helpers.composite_frames(frame, change_frame)

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

    def _draw_staleness_indicator(
        self, frame: Image.Image, width: int, height: int
    ) -> None:
        """Draw a blinking dot in the top-right corner when data is stale.

        Args:
            frame: The frame to draw onto (modified in place).
            width: Display width in pixels.
            height: Display height in pixels.
        """
        blink_interval_frames = max(1, 500 // self._frame_delay_ms)
        total_frames = self._current_page * self._frames_per_page + self._frame_count
        blink_cycle = total_frames // blink_interval_frames
        dot_visible = (blink_cycle % 2) == 0

        if not dot_visible:
            return

        dot_color = (255, 0, 0)
        dot_x = width - 5
        dot_y = 2
        pixels = frame.load()

        for dy in range(3):
            for dx in range(3):
                px = dot_x + dx
                py = dot_y + dy
                if 0 <= px < width and 0 <= py < height:
                    pixels[px, py] = dot_color
