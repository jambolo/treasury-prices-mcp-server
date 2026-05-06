"""Unbounded price cache keyed by date."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Awaitable, Callable

Fetcher = Callable[[date], Awaitable[list[dict]]]


class PriceCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._rows_by_date: dict[date, list[dict]] = {}
        self._cusip_by_date: dict[date, dict[str, dict]] = {}

    async def get_or_fetch(self, d: date, fetcher: Fetcher) -> list[dict]:
        async with self._lock:
            if d not in self._rows_by_date:
                rows = await fetcher(d)
                self._rows_by_date[d] = rows
                self._cusip_by_date[d] = {r["cusip"]: r for r in rows if r.get("cusip")}
            return list(self._rows_by_date[d])

    async def lookup(self, d: date, cusip: str) -> dict | None:
        async with self._lock:
            return self._cusip_by_date.get(d, {}).get(cusip)

    async def cached_dates(self) -> list[str]:
        async with self._lock:
            return sorted(d.isoformat() for d in self._rows_by_date)
