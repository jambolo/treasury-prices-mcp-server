"""Integration tests — require real network. Run with: pytest -m integration"""
from __future__ import annotations

from datetime import date

import pytest

from fetcher import fetch_prices
from tips import get_index_ratio, get_security_metadata

KNOWN_DATE = date(2026, 5, 5)      # Tuesday — should have prices
WEEKEND_DATE = date(2026, 5, 2)    # Saturday — should be empty
KNOWN_CUSIP = "91282CGW5"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_prices_returns_rows():
    rows = await fetch_prices(KNOWN_DATE)
    assert len(rows) > 100


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_prices_row_structure():
    rows = await fetch_prices(KNOWN_DATE)
    row = rows[0]
    assert set(row.keys()) == {"cusip", "security_type", "rate", "maturity_date", "call_date", "buy", "sell", "end_of_day"}
    assert len(row["cusip"]) == 9


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_prices_known_cusip_present():
    rows = await fetch_prices(KNOWN_DATE)
    cusips = {r["cusip"] for r in rows}
    assert KNOWN_CUSIP in cusips


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_prices_weekend_empty():
    rows = await fetch_prices(WEEKEND_DATE)
    assert rows == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_security_metadata_fields():
    meta = await get_security_metadata(KNOWN_CUSIP)
    assert meta["cusip"] == KNOWN_CUSIP
    assert float(meta["interestRate"]) == pytest.approx(1.25)
    assert meta["maturityDate"].startswith("2028-04-15")
    assert meta["datedDate"].startswith("2023-04-15")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_security_metadata_cached():
    """Second call should hit cache — just verify it doesn't raise."""
    await get_security_metadata(KNOWN_CUSIP)
    meta = await get_security_metadata(KNOWN_CUSIP)
    assert meta["cusip"] == KNOWN_CUSIP


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_security_metadata_unknown_cusip():
    with pytest.raises(Exception):
        await get_security_metadata("000000000")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_index_ratio_returns_values():
    result = await get_index_ratio(KNOWN_CUSIP, KNOWN_DATE)
    assert result["cusip"] == KNOWN_CUSIP
    assert result["index_date"] == "2026-05-05"
    assert result["daily_index"] > 1.0
    assert result["ref_cpi"] > 300.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_index_ratio_date_before_issuance():
    with pytest.raises(ValueError, match="No index ratio"):
        await get_index_ratio(KNOWN_CUSIP, date(2020, 1, 1))
