"""Geocoding service using OpenStreetMap Nominatim API.

Converts city names to geographic coordinates (latitude/longitude).
Uses stdlib urllib.request — no additional dependencies required.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from typing import List, Optional

# In-memory cache for geocoding results (keyed by query string)
_cache: dict = {}

_USER_AGENT = "zeClock/1.0"
_TIMEOUT = 10  # seconds
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass
class GeoResult:
    """A geocoding result with coordinates and location metadata."""

    latitude: float
    longitude: float
    display_name: str
    country: str


def geocode(city_name: str) -> Optional[GeoResult]:
    """Resolve a city name to geographic coordinates.

    Args:
        city_name: Non-empty string (min 1 char after trimming whitespace).

    Returns:
        GeoResult with latitude, longitude, display_name, and country,
        or None if the city was not found or an error occurred.
    """
    if not city_name or not city_name.strip():
        return None

    query = city_name.strip()

    # Check cache
    cache_key = f"geocode:{query.lower()}"
    if cache_key in _cache:
        return _cache[cache_key]

    # Build request
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": "1",
        }
    )
    url = f"{_NOMINATIM_URL}?{params}"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", _USER_AGENT)

        with urllib.request.urlopen(req, timeout=_TIMEOUT) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None

    if not data:
        return None

    result = _parse_result(data[0])
    if result:
        _cache[cache_key] = result
    return result


def search_cities(query: str) -> List[GeoResult]:
    """Search for cities matching a query string.

    Args:
        query: Search string, minimum 3 characters after trimming.

    Returns:
        List of up to 5 GeoResult items, or empty list on error.
    """
    if not query or not query.strip():
        return []

    trimmed = query.strip()
    if len(trimmed) < 3:
        return []

    # Check cache
    cache_key = f"search:{trimmed.lower()}"
    if cache_key in _cache:
        return _cache[cache_key]

    # Build request
    params = urllib.parse.urlencode(
        {
            "q": trimmed,
            "format": "json",
            "limit": "5",
        }
    )
    url = f"{_NOMINATIM_URL}?{params}"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", _USER_AGENT)

        with urllib.request.urlopen(req, timeout=_TIMEOUT) as response:
            if response.status != 200:
                return []
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return []

    if not data:
        return []

    results = []
    for item in data[:5]:
        result = _parse_result(item)
        if result:
            results.append(result)

    _cache[cache_key] = results
    return results


def _parse_result(item: dict) -> Optional[GeoResult]:
    """Parse a single Nominatim API result into a GeoResult."""
    try:
        return GeoResult(
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            display_name=item.get("display_name", ""),
            country=(
                item.get("address", {}).get("country", "")
                if "address" in item
                else _extract_country(item.get("display_name", ""))
            ),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _extract_country(display_name: str) -> str:
    """Extract country from display_name (last comma-separated segment)."""
    if not display_name:
        return ""
    parts = display_name.split(",")
    return parts[-1].strip() if parts else ""
