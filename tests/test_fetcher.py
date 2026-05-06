"""Unit tests for fetcher CSV parsing using mocked HTTP."""
from __future__ import annotations

from datetime import date

import pytest
import respx
from httpx import Response

from fetcher import URL, fetch_prices

SAMPLE_CSV = """\
912797SP3,MARKET BASED BILL,0.0,05/07/2026,,0.000000,99.980278,0.000000
91282CGW5,MARKET BASED TIPS,1.25,04/15/2028,,97.500000,97.480000,97.490000
912810TM0,MARKET BASED BOND,4.375,05/15/2041,,100.125000,100.100000,100.110000
"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_parses_csv():
    respx.post(URL).mock(return_value=Response(200, text=SAMPLE_CSV))
    rows = await fetch_prices(date(2026, 5, 5))
    assert len(rows) == 3
    assert rows[0]["cusip"] == "912797SP3"
    assert rows[0]["security_type"] == "MARKET BASED BILL"
    assert rows[0]["sell"] == "99.980278"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_all_fields_present():
    respx.post(URL).mock(return_value=Response(200, text=SAMPLE_CSV))
    rows = await fetch_prices(date(2026, 5, 5))
    row = rows[1]
    assert set(row.keys()) == {"cusip", "security_type", "rate", "maturity_date", "call_date", "buy", "sell", "end_of_day"}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_empty_response():
    respx.post(URL).mock(return_value=Response(200, text=""))
    rows = await fetch_prices(date(2026, 5, 5))
    assert rows == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_skips_blank_lines():
    csv_with_blanks = SAMPLE_CSV + "\n\n\n"
    respx.post(URL).mock(return_value=Response(200, text=csv_with_blanks))
    rows = await fetch_prices(date(2026, 5, 5))
    assert len(rows) == 3


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_strips_whitespace():
    csv_padded = " 912797SP3 , MARKET BASED BILL ,0.0,05/07/2026,,0.000000,99.980278,0.000000\n"
    respx.post(URL).mock(return_value=Response(200, text=csv_padded))
    rows = await fetch_prices(date(2026, 5, 5))
    assert rows[0]["cusip"] == "912797SP3"
    assert rows[0]["security_type"] == "MARKET BASED BILL"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prices_posts_correct_date():
    captured = {}

    def capture(request):
        captured["body"] = request.content.decode()
        return Response(200, text=SAMPLE_CSV)

    respx.post(URL).mock(side_effect=capture)
    await fetch_prices(date(2026, 3, 7))
    assert "priceDateDay=7" in captured["body"]
    assert "priceDateMonth=3" in captured["body"]
    assert "priceDateYear=2026" in captured["body"]
