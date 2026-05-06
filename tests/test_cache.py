"""Unit tests for PriceCache."""
from __future__ import annotations

from datetime import date

import pytest

from cache import PriceCache
from tests.conftest import SAMPLE_ROWS


async def _fetcher(rows):
    """Return a fetcher that returns fixed rows regardless of date."""
    async def _fetch(d: date):
        return rows
    return _fetch


@pytest.mark.asyncio
async def test_cache_stores_date():
    cache = PriceCache()
    d = date(2026, 5, 5)
    fetcher = await _fetcher(SAMPLE_ROWS)
    await cache.get_or_fetch(d, fetcher)
    assert (await cache.cached_dates()) == ["2026-05-05"]


@pytest.mark.asyncio
async def test_cache_multiple_dates_coexist():
    cache = PriceCache()
    d1, d2 = date(2026, 5, 5), date(2026, 5, 6)
    rows1 = [{"cusip": "AAA", "security_type": "BILL", "rate": "", "maturity_date": "", "call_date": "", "buy": "99", "sell": "99", "end_of_day": "0"}]
    rows2 = [{"cusip": "BBB", "security_type": "NOTE", "rate": "", "maturity_date": "", "call_date": "", "buy": "100", "sell": "100", "end_of_day": "100"}]

    await cache.get_or_fetch(d1, await _fetcher(rows1))
    await cache.get_or_fetch(d2, await _fetcher(rows2))

    assert await cache.lookup(d1, "AAA") == rows1[0]
    assert await cache.lookup(d2, "BBB") == rows2[0]
    assert await cache.lookup(d1, "BBB") is None
    assert await cache.lookup(d2, "AAA") is None
    assert await cache.cached_dates() == ["2026-05-05", "2026-05-06"]


@pytest.mark.asyncio
async def test_cache_lookup_missing_cusip():
    cache = PriceCache()
    d = date(2026, 5, 5)
    await cache.get_or_fetch(d, await _fetcher(SAMPLE_ROWS))
    assert await cache.lookup(d, "XXXXXXXXX") is None


@pytest.mark.asyncio
async def test_cache_fetcher_called_once_per_date():
    cache = PriceCache()
    d = date(2026, 5, 5)
    call_count = 0

    async def counting_fetcher(date_):
        nonlocal call_count
        call_count += 1
        return SAMPLE_ROWS

    await cache.get_or_fetch(d, counting_fetcher)
    await cache.get_or_fetch(d, counting_fetcher)
    await cache.get_or_fetch(d, counting_fetcher)
    assert call_count == 1


@pytest.mark.asyncio
async def test_cache_empty_dates():
    cache = PriceCache()
    assert await cache.cached_dates() == []


@pytest.mark.asyncio
async def test_cache_lookup_before_fetch():
    cache = PriceCache()
    assert await cache.lookup(date(2026, 5, 5), "912797SP3") is None
