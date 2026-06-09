"""Tests for zeclock.geocoder module."""

import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from zeclock.geocoder import (
    GeoResult,
    geocode,
    search_cities,
    _cache,
    _extract_country,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the geocoder cache before each test."""
    _cache.clear()
    yield
    _cache.clear()


# --- GeoResult dataclass ---


def test_georesult_creation():
    result = GeoResult(
        latitude=48.8566,
        longitude=2.3522,
        display_name="Paris, Île-de-France, France",
        country="France",
    )
    assert result.latitude == 48.8566
    assert result.longitude == 2.3522
    assert result.display_name == "Paris, Île-de-France, France"
    assert result.country == "France"


# --- geocode() input validation ---


def test_geocode_empty_string_returns_none():
    assert geocode("") is None


def test_geocode_whitespace_only_returns_none():
    assert geocode("   ") is None


def test_geocode_tabs_and_newlines_returns_none():
    assert geocode("\t\n  ") is None


# --- geocode() success ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {
                "lat": "48.8566",
                "lon": "2.3522",
                "display_name": "Paris, Île-de-France, France",
            }
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    result = geocode("Paris")
    assert result is not None
    assert result.latitude == 48.8566
    assert result.longitude == 2.3522
    assert "Paris" in result.display_name
    assert result.country == "France"


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_trims_input(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {
                "lat": "51.5074",
                "lon": "-0.1278",
                "display_name": "London, England, United Kingdom",
            }
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    result = geocode("  London  ")
    assert result is not None
    assert result.latitude == 51.5074


# --- geocode() errors ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_empty_results_returns_none(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps([]).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    assert geocode("Nonexistentcity12345") is None


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_network_error_returns_none(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Network error")
    assert geocode("Paris") is None


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_timeout_returns_none(mock_urlopen):
    mock_urlopen.side_effect = OSError("timed out")
    assert geocode("Paris") is None


# --- geocode() caching ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_caches_result(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {
                "lat": "48.8566",
                "lon": "2.3522",
                "display_name": "Paris, Île-de-France, France",
            }
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    result1 = geocode("Paris")
    result2 = geocode("Paris")

    assert result1 == result2
    # urlopen should only be called once due to caching
    assert mock_urlopen.call_count == 1


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_geocode_cache_case_insensitive(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {
                "lat": "48.8566",
                "lon": "2.3522",
                "display_name": "Paris, France",
            }
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    geocode("paris")
    geocode("PARIS")

    assert mock_urlopen.call_count == 1


# --- search_cities() input validation ---


def test_search_cities_empty_string_returns_empty():
    assert search_cities("") == []


def test_search_cities_whitespace_only_returns_empty():
    assert search_cities("   ") == []


def test_search_cities_less_than_3_chars_returns_empty():
    assert search_cities("Pa") == []


def test_search_cities_exactly_3_chars_after_trim():
    # "Par" is 3 chars — should attempt the request (will fail without mock)
    with patch("zeclock.geocoder.urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            [
                {
                    "lat": "48.8566",
                    "lon": "2.3522",
                    "display_name": "Paris, France",
                }
            ]
        ).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        results = search_cities("Par")
        assert len(results) == 1


# --- search_cities() success ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_search_cities_returns_up_to_5(mock_urlopen):
    items = [
        {"lat": str(i), "lon": str(i), "display_name": f"City {i}, Country {i}"}
        for i in range(7)
    ]
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(items).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    results = search_cities("City")
    assert len(results) <= 5


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_search_cities_success(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"},
            {"lat": "48.8530", "lon": "2.3499", "display_name": "Paris 5e, France"},
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    results = search_cities("Paris")
    assert len(results) == 2
    assert results[0].latitude == 48.8566
    assert results[1].display_name == "Paris 5e, France"


# --- search_cities() errors ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_search_cities_network_error_returns_empty(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Network error")
    assert search_cities("Paris") == []


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_search_cities_empty_results_returns_empty(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps([]).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    assert search_cities("Nonexistentcity") == []


# --- search_cities() caching ---


@patch("zeclock.geocoder.urllib.request.urlopen")
def test_search_cities_caches_results(mock_urlopen):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(
        [
            {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"},
        ]
    ).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = mock_response

    search_cities("Paris")
    search_cities("Paris")

    assert mock_urlopen.call_count == 1


# --- _extract_country helper ---


def test_extract_country_from_display_name():
    assert _extract_country("Paris, Île-de-France, France") == "France"


def test_extract_country_empty_string():
    assert _extract_country("") == ""


def test_extract_country_single_part():
    assert _extract_country("France") == "France"
