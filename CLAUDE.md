# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev deps
pip install -r requirements-dev.txt

# Run server locally (port 8080, no auth)
python server.py

# Run server with bearer auth
MCP_AUTH_TOKEN=secret python server.py

# Unit tests only (default — integration tests deselected)
pytest -m "not integration"

# Single test file / test
pytest tests/test_tips_unit.py
pytest tests/test_tips_unit.py::test_name

# Integration tests (real network to TreasuryDirect / FedInvest)
pytest -m integration

# All tests
pytest

# Docker
docker build -t treasury-prices-mcp .
docker run -p 8080:8080 -e MCP_AUTH_TOKEN=secret treasury-prices-mcp
```

`pytest.ini` sets `asyncio_mode = auto` — async tests do not need `@pytest.mark.asyncio`. The `integration` marker gates network-dependent tests.

## Architecture

Single FastMCP server (`server.py`) exposing both **tools** (model-callable, primary) and **resources** (user-attachable, bonus). Both surfaces share `_load_rows` / `_load_row` helpers — keep that single source of truth when adding endpoints. Tools and resources are intentionally parallel; changes to one usually need the other.

Two independent upstream data sources, each with its own caching strategy:

1. **FedInvest historical prices** (`fetcher.py`) — POSTs date params to a CSV endpoint at `treasurydirect.gov/GA-FI/FedInvest/securityPriceDetail`. CSV is **headerless and positional**; column order is hardcoded in `_COLUMNS`. Cached per-date in `cache.PriceCache` (in-memory, unbounded, async-locked, two indexes: rows-by-date and cusip-lookup-by-date). Weekends/holidays return empty CSV → empty list, not error.

2. **TreasuryDirect TA_WS** (`tips.py`) — two endpoints: `/securities/search` for security metadata (immutable post-issuance, cached by CUSIP forever) and `/secindex/search` for the daily CPI index ratio table (fetched once per CUSIP as a full table of up to 1000 rows, then keyed by date string). Both caches are module-level dicts with asyncio locks.

TIPS valuation (`compute_tips_value`) combines both sources: clean price from FedInvest cache × `dailyIndex` from TA_WS cache, plus accrued-interest math from coupon dates. Coupon dates are derived from maturity month ± 6 months on the 15th — see `_coupon_dates`. All money math uses `Decimal` with `ROUND_HALF_UP`; only the final return dict converts to `float` for JSON.

### Price-type semantics (important caveat)

FedInvest publishes three clean prices per security: `buy`, `sell`, `end_of_day`. **`end_of_day` is zero/missing for the current trading day** because it is not published until after close. `get_tips_value` raises `ValueError` in that case and the docstring tells the model to retry with `price_type="sell"`. Preserve this behavior — the error message is a contract with the model.

### Auth

Bearer token middleware (`_BearerAuthMiddleware` in `server.py`) is **only added when `MCP_AUTH_TOKEN` is set**. No token → no auth. The middleware wraps the FastMCP HTTP app before it is handed to uvicorn.

### Transport

Streamable HTTP via `mcp.http_app()`. Do not switch to stdio without checking the deployment target (Docker, port 8080).

## Conventions

- Dates in API surface are strings `YYYY-MM-DD`; internally always `datetime.date`. `_parse_date` is the only conversion point.
- CUSIPs are normalized via `.strip().upper()` at the cache-lookup boundary, not in the cache itself.
- All upstream HTTP uses `httpx.AsyncClient` with `timeout=30.0, follow_redirects=True`.
- `Decimal(str(x))` when constructing from floats — never `Decimal(float)`.
