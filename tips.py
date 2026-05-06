"""TIPS security details, index ratio fetch, and valuation math."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import httpx

_SECURITIES_URL = "https://www.treasurydirect.gov/TA_WS/securities/search"
_SECINDEX_URL = "https://www.treasurydirect.gov/TA_WS/secindex/search"

# Cache security metadata by CUSIP — immutable after issuance.
_security_cache: dict[str, dict] = {}
_security_lock = asyncio.Lock()

# Cache full index table by CUSIP: date string -> (dailyIndex, refCpi).
_index_cache: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
_index_lock = asyncio.Lock()


async def _fetch_security(cusip: str) -> dict:
    async with _security_lock:
        if cusip in _security_cache:
            return _security_cache[cusip]

    params = {"cusip": cusip, "format": "json"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        r = await c.get(_SECURITIES_URL, params=params)
        r.raise_for_status()
        data = r.json()

    if not data:
        raise ValueError(f"No security found for CUSIP {cusip}")

    rec = data[0] if isinstance(data, list) else data
    async with _security_lock:
        _security_cache[cusip] = rec
    return rec


async def _fetch_index_table(cusip: str) -> dict[str, tuple[Decimal, Decimal]]:
    """Fetch and cache the full index table for a CUSIP. Returns date->( dailyIndex, refCpi)."""
    async with _index_lock:
        if cusip in _index_cache:
            return _index_cache[cusip]

    params = {
        "cusip": cusip,
        "format": "json",
        "sortdatafield": "indexDate",
        "sortorder": "desc",
        "pagenum": "0",
        "pagesize": "1000",
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
        r = await c.get(_SECINDEX_URL, params=params)
        r.raise_for_status()
        data = r.json()

    records = data if isinstance(data, list) else data.get("records", [])
    table: dict[str, tuple[Decimal, Decimal]] = {}
    for rec in records:
        key = rec.get("indexDate", "")[:10]
        if key:
            table[key] = (Decimal(str(rec["dailyIndex"])), Decimal(str(rec["refCpi"])))

    async with _index_lock:
        _index_cache[cusip] = table
    return table


async def _get_index_ratio(cusip: str, index_date: date) -> tuple[Decimal, Decimal]:
    """Return (dailyIndex, refCpi) for a CUSIP on a specific date."""
    table = await _fetch_index_table(cusip)
    key = index_date.strftime("%Y-%m-%d")
    if key not in table:
        raise ValueError(f"No index ratio for CUSIP {cusip} on {key}")
    return table[key]


def _coupon_dates(dated_date: date, maturity: date, settlement: date) -> tuple[date, date]:
    """Return (last_coupon_date, next_coupon_date) bracketing settlement."""
    # Coupon months align with maturity month and 6 months prior.
    m1, m2 = maturity.month, (maturity.month - 6) % 12 or 12
    coupon_months = {m1, m2}

    # Walk backwards from settlement to find last coupon on or before settlement.
    d = settlement
    while True:
        if d.month in coupon_months and d.day == 15 and d >= dated_date:
            last = d
            break
        d -= timedelta(days=1)

    # Next coupon = 6 months after last.
    m = last.month + 6
    y = last.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    nxt = last.replace(year=y, month=m)
    return last, nxt


async def get_security_metadata(cusip: str) -> dict:
    """Return raw security metadata for a CUSIP from TreasuryDirect."""
    return await _fetch_security(cusip)


async def get_index_ratio(cusip: str, index_date: date) -> dict:
    """Return dailyIndex and refCpi for a CUSIP on a specific date."""
    daily_index, ref_cpi = await _get_index_ratio(cusip, index_date)
    return {
        "cusip": cusip,
        "index_date": index_date.isoformat(),
        "daily_index": float(daily_index),
        "ref_cpi": float(ref_cpi),
    }


async def compute_tips_value(
    cusip: str,
    price_date: date,
    quoted_price: Decimal,
    face_value: Decimal,
) -> dict:
    """Return full TIPS valuation breakdown for given quoted clean price.

    Args:
        cusip: 9-char Treasury CUSIP.
        price_date: Settlement / price date.
        quoted_price: Clean price per 100 face (from FedInvest).
        face_value: Par amount in dollars.
    """
    sec, (daily_index, ref_cpi) = await asyncio.gather(
        _fetch_security(cusip),
        _get_index_ratio(cusip, price_date),
    )

    coupon_rate = Decimal(str(sec.get("interestRate", "0"))) / 100
    dated_str = sec.get("datedDate") or sec.get("issueDate", "")
    dated_date = date.fromisoformat(dated_str[:10])
    maturity = date.fromisoformat(sec["maturityDate"][:10])

    last_coupon, next_coupon = _coupon_dates(dated_date, maturity, price_date)
    days_since = Decimal((price_date - last_coupon).days)
    days_period = Decimal((next_coupon - last_coupon).days)

    adj_principal = (face_value * daily_index).quantize(Decimal("0.000001"))
    infl_adj_price_per_100 = (quoted_price * daily_index).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    infl_adj_price = (face_value * infl_adj_price_per_100 / 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    accrued = (
        (coupon_rate / 2) * adj_principal * (days_since / days_period)
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    full_price = (infl_adj_price + accrued).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "cusip": cusip,
        "price_date": price_date.isoformat(),
        "face_value": float(face_value),
        "quoted_price_per_100": float(quoted_price),
        "daily_index": float(daily_index),
        "ref_cpi": float(ref_cpi),
        "inflation_adjusted_principal": float(adj_principal),
        "inflation_adjusted_price_per_100": float(infl_adj_price_per_100),
        "inflation_adjusted_price": float(infl_adj_price),
        "coupon_rate": float(coupon_rate),
        "last_coupon_date": last_coupon.isoformat(),
        "next_coupon_date": next_coupon.isoformat(),
        "days_since_last_coupon": int(days_since),
        "days_in_coupon_period": int(days_period),
        "accrued_interest": float(accrued),
        "full_price": float(full_price),
        "security_type": sec.get("securityType", ""),
        "maturity_date": maturity.isoformat(),
        "series": sec.get("series", ""),
    }
