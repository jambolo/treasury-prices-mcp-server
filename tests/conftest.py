"""Shared fixtures."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


KNOWN_DATE = date(2026, 5, 5)
KNOWN_CUSIP_TIPS = "91282CGW5"
KNOWN_CUSIP_BILL = "912797SP3"

SAMPLE_ROWS = [
    {
        "cusip": KNOWN_CUSIP_BILL,
        "security_type": "MARKET BASED BILL",
        "rate": "0.0",
        "maturity_date": "05/07/2026",
        "call_date": "",
        "buy": "0.000000",
        "sell": "99.980278",
        "end_of_day": "0.000000",
    },
    {
        "cusip": KNOWN_CUSIP_TIPS,
        "security_type": "MARKET BASED TIPS",
        "rate": "1.25",
        "maturity_date": "04/15/2028",
        "call_date": "",
        "buy": "97.500000",
        "sell": "97.480000",
        "end_of_day": "97.490000",
    },
    {
        "cusip": "912810TM0",
        "security_type": "MARKET BASED BOND",
        "rate": "4.375",
        "maturity_date": "05/15/2041",
        "call_date": "",
        "buy": "100.125000",
        "sell": "100.100000",
        "end_of_day": "100.110000",
    },
]

SAMPLE_SECURITY = {
    "cusip": KNOWN_CUSIP_TIPS,
    "interestRate": "1.25",
    "datedDate": "2023-04-15",
    "issueDate": "2023-06-30",
    "maturityDate": "2028-04-15",
    "securityType": "Note",
    "series": "X-2028",
    "referenceCpiOnIssuedDate": "303.3121",
    "referenceCpiOnDatedDate": "299.94933",
    "indexRatioOnIssueDate": "1.011210",
}

SAMPLE_INDEX_TABLE = {
    "2026-05-05": (Decimal("1.0997900"), Decimal("329.8812600")),
    "2026-05-04": (Decimal("1.0994200"), Decimal("329.7706800")),
    "2026-04-15": (Decimal("1.0911000"), Decimal("327.2688000")),
}
