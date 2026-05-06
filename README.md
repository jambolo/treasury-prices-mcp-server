# Treasury Prices MCP Server

[![CI](https://github.com/jambolo/treasury-prices-mcp-server/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/jambolo/treasury-prices-mcp-server/actions/workflows/ci.yml)

An [MCP](https://modelcontextprotocol.io) server exposing U.S. Treasury historical prices and TIPS valuation as tools and resources, served over Streamable HTTP.

## Data sources

1. **FedInvest historical prices** — buy, sell, and end-of-day clean prices per 100 face value for all market-based Treasury securities on a given date. Fetched from `treasurydirect.gov/GA-FI/FedInvest/securityPriceDetail`.
2. **TreasuryDirect TA_WS** — security metadata and daily CPI index ratios used to compute the inflation-adjusted full invoice price of TIPS.

## Tools

| Tool | Purpose |
|---|---|
| `get_price` | Single price row for a CUSIP on a date. |
| `list_prices` | All price rows for a date, optional filter by security type substring (`TIPS`, `BILL`, `NOTE`, ...). |
| `get_cached_dates` | Dates currently in the in-memory price cache. |
| `get_tips_value` | Full invoice value of a TIPS — inflation-adjusted principal, accrued interest, and dirty price. |

## Resources

| URI template | Returns |
|---|---|
| `prices://{date}` | All price rows for the date. |
| `prices://{date}/{cusip}` | Single price row. |
| `tips://{cusip}` | TIPS security metadata. |
| `tips://{cusip}/{date}` | CPI daily index ratio for the date. |

## Running

```bash
pip install -r requirements.txt
python server.py                          # port 8080, no auth
MCP_AUTH_TOKEN=secret python server.py    # bearer auth
```

### Docker

```bash
docker build -t treasury-prices-mcp .
docker run -p 8080:8080 -e MCP_AUTH_TOKEN=secret treasury-prices-mcp
```

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `PORT` | `8080` | uvicorn bind port. |
| `MCP_AUTH_TOKEN` | (unset) | If set, requires `Authorization: Bearer <token>` on every request. |

## Notes on price types

FedInvest publishes three clean prices: `buy`, `sell`, `end_of_day`. `end_of_day` is the most accurate for settled dates but is zero for the current trading day until the close-of-day file is published. If `get_tips_value` raises an error for `end_of_day`, retry with `price_type="sell"`.

Weekends and holidays return an empty result — FedInvest publishes nothing on non-trading days.

## Development

```bash
pip install -r requirements-dev.txt
pytest -m "not integration"   # unit tests
pytest -m integration         # hits live TreasuryDirect / FedInvest
pytest                        # all
```

## License

MIT — see [LICENSE](LICENSE).
