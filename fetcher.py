"""Fetch Treasury historical prices CSV from FedInvest."""
from __future__ import annotations

import csv
from datetime import date
from io import StringIO

import httpx

URL = "https://www.treasurydirect.gov/GA-FI/FedInvest/securityPriceDetail"

# CSV has no header row. Columns are positional.
_COLUMNS = ("cusip", "security_type", "rate", "maturity_date", "call_date", "buy", "sell", "end_of_day")


async def fetch_prices(d: date) -> list[dict]:
    """POST date to FedInvest CSV endpoint, return list of normalized rows."""
    data = {
        "priceDateDay": str(d.day),
        "priceDateMonth": str(d.month),
        "priceDateYear": str(d.year),
        "fileType": "csv",
        "csv": "CSV FORMAT",
    }
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.post(URL, data=data)
        r.raise_for_status()
        text = r.text

    if not text.strip():
        return []

    rows: list[dict] = []
    for raw in csv.reader(StringIO(text)):
        if not raw or all(not c.strip() for c in raw):
            continue
        row = {_COLUMNS[i]: raw[i].strip() if i < len(raw) else "" for i in range(len(_COLUMNS))}
        if row.get("cusip"):
            rows.append(row)
    return rows
