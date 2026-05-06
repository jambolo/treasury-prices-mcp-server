"""Unit tests for TIPS math and helpers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from tips import _coupon_dates, compute_tips_value
from tests.conftest import SAMPLE_INDEX_TABLE, SAMPLE_SECURITY


# --- _coupon_dates ---

@pytest.mark.parametrize("settlement,expected_last,expected_next", [
    # Between coupons
    (date(2026, 5, 5),  date(2026, 4, 15), date(2026, 10, 15)),
    # Day before coupon
    (date(2026, 4, 14), date(2025, 10, 15), date(2026, 4, 15)),
    # On coupon date
    (date(2026, 4, 15), date(2026, 4, 15), date(2026, 10, 15)),
    # Day after coupon
    (date(2026, 4, 16), date(2026, 4, 15), date(2026, 10, 15)),
    # Between Oct coupon and year-end
    (date(2026, 11, 1), date(2026, 10, 15), date(2027, 4, 15)),
])
def test_coupon_dates(settlement, expected_last, expected_next):
    # 91282CGW5: maturity Apr 15 2028, coupon months Apr and Oct
    dated = date(2023, 4, 15)
    maturity = date(2028, 4, 15)
    last, nxt = _coupon_dates(dated, maturity, settlement)
    assert last == expected_last
    assert nxt == expected_next


def test_coupon_dates_days_in_period():
    dated = date(2023, 4, 15)
    maturity = date(2028, 4, 15)
    last, nxt = _coupon_dates(dated, maturity, date(2026, 5, 5))
    assert (nxt - last).days == 183  # Apr 15 to Oct 15 2026


# --- compute_tips_value ---

@pytest.mark.asyncio
async def test_compute_tips_value_math():
    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):

        result = await compute_tips_value(
            cusip="91282CGW5",
            price_date=date(2026, 5, 5),
            quoted_price=Decimal("97.5"),
            face_value=Decimal("1000"),
        )

    daily_index = Decimal("1.0997900")

    assert result["daily_index"] == pytest.approx(float(daily_index))
    assert result["inflation_adjusted_principal"] == pytest.approx(float(Decimal("1000") * daily_index))
    assert result["inflation_adjusted_price_per_100"] == pytest.approx(float(Decimal("97.5") * daily_index))
    assert result["inflation_adjusted_price"] == pytest.approx(
        float(Decimal("1000") * Decimal("97.5") * daily_index / 100), rel=1e-4
    )
    assert result["last_coupon_date"] == "2026-04-15"
    assert result["next_coupon_date"] == "2026-10-15"
    assert result["days_since_last_coupon"] == 20
    assert result["days_in_coupon_period"] == 183
    assert result["coupon_rate"] == pytest.approx(0.0125)
    assert result["maturity_date"] == "2028-04-15"
    assert result["series"] == "X-2028"


@pytest.mark.asyncio
async def test_compute_tips_value_accrued_interest():
    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):

        result = await compute_tips_value(
            cusip="91282CGW5",
            price_date=date(2026, 5, 5),
            quoted_price=Decimal("97.5"),
            face_value=Decimal("1000"),
        )

    # accrued = (0.0125/2) * adj_principal * (20/183)
    daily_index = Decimal("1.0997900")
    adj_principal = Decimal("1000") * daily_index
    expected_accrued = (Decimal("0.0125") / 2) * adj_principal * Decimal("20") / Decimal("183")
    assert result["accrued_interest"] == pytest.approx(float(expected_accrued), rel=1e-4)


@pytest.mark.asyncio
async def test_compute_tips_value_full_price_equals_clean_plus_accrued():
    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):

        result = await compute_tips_value(
            cusip="91282CGW5",
            price_date=date(2026, 5, 5),
            quoted_price=Decimal("97.5"),
            face_value=Decimal("1000"),
        )

    assert result["full_price"] == pytest.approx(
        result["inflation_adjusted_price"] + result["accrued_interest"], rel=1e-4
    )


@pytest.mark.asyncio
async def test_compute_tips_value_missing_index_date():
    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):

        with pytest.raises(ValueError, match="No index ratio"):
            await compute_tips_value(
                cusip="91282CGW5",
                price_date=date(2020, 1, 1),  # not in SAMPLE_INDEX_TABLE
                quoted_price=Decimal("97.5"),
                face_value=Decimal("1000"),
            )


@pytest.mark.asyncio
async def test_compute_tips_value_face_value_scales():
    """Doubling face_value doubles all dollar amounts."""
    kwargs = dict(
        cusip="91282CGW5",
        price_date=date(2026, 5, 5),
        quoted_price=Decimal("97.5"),
    )
    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):
        r1 = await compute_tips_value(**kwargs, face_value=Decimal("1000"))

    with patch("tips._fetch_security", new=AsyncMock(return_value=SAMPLE_SECURITY)), \
         patch("tips._fetch_index_table", new=AsyncMock(return_value=SAMPLE_INDEX_TABLE)):
        r2 = await compute_tips_value(**kwargs, face_value=Decimal("2000"))

    for field in ("inflation_adjusted_principal", "inflation_adjusted_price", "accrued_interest", "full_price"):
        assert r2[field] == pytest.approx(r1[field] * 2, rel=1e-4)
