"""Treasury Prices MCP server.

Exposes MCP tools (primary) and resources (bonus) for two data sources:

1. Historical prices (FedInvest CSV) — buy/sell/end_of_day clean prices per
   100 face value for all Treasury market-based securities on a given date.
   One date is held in memory at a time; requesting a new date replaces the cache.

2. TIPS valuation (TreasuryDirect TA_WS API) — given a CUSIP and date, fetches
   the daily CPI index ratio and security metadata, then computes the
   inflation-adjusted principal, accrued interest, and full invoice price.

Transport: Streamable HTTP. Auth: bearer token via Starlette middleware (MCP_AUTH_TOKEN env var).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal

import uvicorn
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from cache import PriceCache
from fetcher import fetch_prices
from tips import compute_tips_value, get_index_ratio, get_security_metadata

mcp = FastMCP("treasury-prices")
cache = PriceCache()


class _BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        auth = request.headers.get("Authorization", "")
        if not (auth.startswith("Bearer ") and auth[7:] == self._token):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"Invalid date '{s}'. Expected YYYY-MM-DD.") from e


# --- Core helpers: single source of truth for tools and resources. ---

async def _load_rows(price_date: str) -> list[dict]:
    d = _parse_date(price_date)
    return await cache.get_or_fetch(d, fetch_prices)




async def _load_row(price_date: str, cusip: str) -> dict:
    d = _parse_date(price_date)
    await cache.get_or_fetch(d, fetch_prices)
    row = await cache.lookup(d, cusip.strip().upper())
    if not row:
        raise ValueError(f"CUSIP {cusip} not found for {price_date}")
    return row


def _filter_by_type(rows: list[dict], security_type: str | None) -> list[dict]:
    if not security_type:
        return rows
    st = security_type.lower()
    return [r for r in rows if st in r.get("security_type", "").lower()]


# --- Tools (primary interface; model-callable). ---

@mcp.tool
async def get_price(cusip: str, price_date: str) -> dict:
    """Return the price row for a CUSIP on the given date.

    The row contains buy, sell, and end_of_day prices. end_of_day is the
    most accurate for historical dates but is often zero for the current day
    (not yet published); in that case use the sell price instead.

    All three prices (buy, sell, end_of_day) are clean prices per 100 face value.

    Args:
        cusip: 9-character Treasury CUSIP.
        price_date: Date in YYYY-MM-DD format.
    """
    return await _load_row(price_date, cusip)


@mcp.tool
async def list_prices(price_date: str, security_type: str | None = None) -> list[dict]:
    """List all price rows for a date, optionally filtered by security type substring.

    Args:
        price_date: Date in YYYY-MM-DD format.
        security_type: Optional case-insensitive substring (e.g. "TIPS", "BILL", "NOTE").
    """
    rows = await _load_rows(price_date)
    return _filter_by_type(rows, security_type)


@mcp.tool
async def get_cached_dates() -> list[str]:
    """Return all dates currently held in the price cache (YYYY-MM-DD), sorted ascending."""
    return await cache.cached_dates()


@mcp.tool
async def get_tips_value(
    cusip: str,
    price_date: str,
    face_value: float = 1000.0,
    price_type: str = "end_of_day",
) -> dict:
    """Compute full invoice value of a TIPS on a given date.

    Fetches the quoted clean price from the price cache, the daily CPI index
    ratio from TreasuryDirect, and returns the inflation-adjusted principal,
    accrued interest, and full (dirty) price.

    NOTE on price_type: "end_of_day" is the most accurate price for settled
    dates but is often zero for the current day (not yet published). If this
    tool raises an error because end_of_day is zero, retry with price_type
    "sell" instead.

    Args:
        cusip: 9-character Treasury CUSIP for a TIPS security.
        price_date: Date in YYYY-MM-DD format.
        face_value: Par amount in dollars (default 1000).
        price_type: Which FedInvest price to use — "buy", "sell", or
            "end_of_day" (default "end_of_day"). end_of_day is preferred
            for historical dates; use "sell" for today's date.

    Returns a dict with:
        daily_index: CPI inflation index ratio for the date (multiplier, not a price).
        inflation_adjusted_principal: face_value × daily_index (par adjusted for inflation, in dollars).
        inflation_adjusted_price_per_100: clean inflation-adjusted price per 100 face value
            (quoted_price × daily_index — same convention as the historical prices page).
        inflation_adjusted_price: inflation_adjusted_price_per_100 scaled to face_value dollars.
        full_price: dirty price in dollars = inflation_adjusted_price + accrued_interest.
    """
    valid_types = {"buy", "sell", "end_of_day"}
    if price_type not in valid_types:
        raise ValueError(f"price_type must be one of {sorted(valid_types)}")

    row = await _load_row(price_date, cusip)
    raw_price = row.get(price_type, "")

    if not raw_price or Decimal(raw_price) == 0:
        raise ValueError(
            f"Price type '{price_type}' is zero or missing for {cusip} on {price_date}. "
            "Try a different price_type."
        )

    d = _parse_date(price_date)
    return await compute_tips_value(
        cusip=cusip.strip().upper(),
        price_date=d,
        quoted_price=Decimal(raw_price),
        face_value=Decimal(str(face_value)),
    )


# --- Resources (bonus; user-attachable in Claude Desktop, model-readable in
#     clients that support resource templates). ---

@mcp.resource(
    "prices://{price_date}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
async def resource_prices_for_date(price_date: str) -> list[dict]:
    """All Treasury price rows for a given date (YYYY-MM-DD)."""
    return await _load_rows(price_date)


@mcp.resource(
    "prices://{price_date}/{cusip}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
async def resource_price_for_cusip(price_date: str, cusip: str) -> dict:
    """Single Treasury price row for a CUSIP on a given date (YYYY-MM-DD)."""
    return await _load_row(price_date, cusip)


@mcp.resource(
    "tips://{cusip}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
async def resource_tips_security(cusip: str) -> dict:
    """TIPS security metadata for a CUSIP — coupon rate, dated date, maturity,
    reference CPI at issue, series, and auction details."""
    return await get_security_metadata(cusip.strip().upper())


@mcp.resource(
    "tips://{cusip}/{price_date}",
    mime_type="application/json",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
async def resource_tips_index(cusip: str, price_date: str) -> dict:
    """CPI daily index ratio and reference CPI for a CUSIP on a given date (YYYY-MM-DD)."""
    d = _parse_date(price_date)
    return await get_index_ratio(cusip.strip().upper(), d)


# --- App assembly. ---

app = mcp.http_app()

_auth_token = os.environ.get("MCP_AUTH_TOKEN")
if _auth_token:
    app.add_middleware(_BearerAuthMiddleware, token=_auth_token)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
