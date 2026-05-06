"""Unit tests for server helpers and tools (mocked network)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from server import _filter_by_type, _parse_date, mcp
from tests.conftest import SAMPLE_INDEX_TABLE, SAMPLE_ROWS, SAMPLE_SECURITY


# --- _parse_date ---

def test_parse_date_valid():
    assert _parse_date("2026-05-05") == date(2026, 5, 5)


def test_parse_date_invalid_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _parse_date("05/05/2026")


def test_parse_date_invalid_date():
    with pytest.raises(ValueError):
        _parse_date("2026-13-01")


def test_parse_date_leap_year_valid():
    assert _parse_date("2024-02-29") == date(2024, 2, 29)


def test_parse_date_leap_year_invalid():
    with pytest.raises(ValueError):
        _parse_date("2026-02-29")


# --- _filter_by_type ---

def test_filter_by_type_none_returns_all():
    assert _filter_by_type(SAMPLE_ROWS, None) == SAMPLE_ROWS


def test_filter_by_type_tips():
    rows = _filter_by_type(SAMPLE_ROWS, "TIPS")
    assert len(rows) == 1
    assert rows[0]["cusip"] == "91282CGW5"


def test_filter_by_type_case_insensitive():
    rows = _filter_by_type(SAMPLE_ROWS, "tips")
    assert len(rows) == 1


def test_filter_by_type_no_match():
    assert _filter_by_type(SAMPLE_ROWS, "ZZZZ") == []


def test_filter_by_type_partial_match():
    rows = _filter_by_type(SAMPLE_ROWS, "MARKET")
    assert len(rows) == 3


# --- Tools via in-process MCP client ---

async def _patched_client(fetcher_rows=SAMPLE_ROWS, security=SAMPLE_SECURITY, index_table=SAMPLE_INDEX_TABLE):
    """Context manager that patches fetchers and returns an in-process MCP client."""
    # Return a tuple of patch objects and the client for use in tests.
    return fetcher_rows, security, index_table


@pytest.mark.asyncio
async def test_tool_get_price(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        result = await client.call_tool("get_price", {"cusip": "912797SP3", "price_date": "2026-05-05"})

    assert result.data["cusip"] == "912797SP3"
    assert result.data["security_type"] == "MARKET BASED BILL"


@pytest.mark.asyncio
async def test_tool_get_price_cusip_not_found(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        with pytest.raises(Exception, match="not found"):
            await client.call_tool("get_price", {"cusip": "XXXXXXXXX", "price_date": "2026-05-05"})


@pytest.mark.asyncio
async def test_tool_list_prices_no_filter(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        result = await client.call_tool("list_prices", {"price_date": "2026-05-05"})

    assert len(result.data) == 3


@pytest.mark.asyncio
async def test_tool_list_prices_tips_filter(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        result = await client.call_tool("list_prices", {"price_date": "2026-05-05", "security_type": "TIPS"})

    assert len(result.data) == 1
    assert result.data[0]["cusip"] == "91282CGW5"


@pytest.mark.asyncio
async def test_tool_get_cached_dates_empty():
    # Use a fresh mcp instance would be ideal; instead use a date unlikely to be cached.
    async with Client(mcp) as client:
        result = await client.call_tool("get_cached_dates", {})
    assert isinstance(result.data, list)


@pytest.mark.asyncio
async def test_tool_get_tips_value_zero_eod_raises(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS  # 912797SP3 has end_of_day=0.000000

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        with pytest.raises(Exception, match="zero or missing"):
            await client.call_tool("get_tips_value", {
                "cusip": "912797SP3",
                "price_date": "2026-05-05",
                "price_type": "end_of_day",
            })


@pytest.mark.asyncio
async def test_tool_get_tips_value_invalid_price_type(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)

    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.call_tool("get_tips_value", {
                "cusip": "91282CGW5",
                "price_date": "2026-05-05",
                "price_type": "mid",
            })


@pytest.mark.asyncio
async def test_tool_get_tips_value_math(monkeypatch):
    async def fake_fetch(d):
        return SAMPLE_ROWS

    monkeypatch.setattr("server.fetch_prices", fake_fetch)
    monkeypatch.setattr("tips._fetch_security", AsyncMock(return_value=SAMPLE_SECURITY))
    monkeypatch.setattr("tips._fetch_index_table", AsyncMock(return_value=SAMPLE_INDEX_TABLE))

    async with Client(mcp) as client:
        result = await client.call_tool("get_tips_value", {
            "cusip": "91282CGW5",
            "price_date": "2026-05-05",
            "face_value": 1000.0,
            "price_type": "sell",
        })

    data = result.data
    assert data["cusip"] == "91282CGW5"
    assert data["face_value"] == 1000.0
    assert data["full_price"] > data["inflation_adjusted_price"]
    assert data["inflation_adjusted_price"] > 0
    assert data["accrued_interest"] > 0
    assert data["last_coupon_date"] == "2026-04-15"
    assert data["next_coupon_date"] == "2026-10-15"
