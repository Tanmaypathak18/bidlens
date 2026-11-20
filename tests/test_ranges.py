"""Step 2.6 tests: conformal range calibration and comparable bids."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bidlens.pricing.comparables import ComparableFinder
from bidlens.pricing.ranges import calibrate, conformity, cqr_adjustment
from bidlens.pricing.setup import use_cost_index


@pytest.fixture(autouse=True)
def _no_escalation():
    use_cost_index(None)
    yield
    use_cost_index(None)


def test_conformity_is_negative_inside_and_positive_outside():
    s = conformity(
        np.array([10.0, 10.0, 10.0]), np.array([20.0, 20.0, 20.0]), np.array([15.0, 5.0, 40.0])
    )
    assert s[0] < 0
    assert s[1] == pytest.approx(np.log(2))
    assert s[2] == pytest.approx(np.log(2))


def test_cqr_adjustment_reaches_coverage():
    rng = np.random.default_rng(0)
    scores = rng.normal(size=999)
    adj = cqr_adjustment(scores, 0.8)
    assert (scores <= adj).mean() >= 0.8
    assert cqr_adjustment([], 0.8) == 0.0


def test_calibration_widens_a_too_narrow_range_using_only_the_past():
    rng = np.random.default_rng(1)
    n = 4000
    dates = pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 365 * 3, n), "D")
    actual = np.exp(rng.normal(0, 1, n))
    df = pd.DataFrame(
        {
            "kind": np.where(dates < pd.Timestamp("2024-01-01"), "validation", "test"),
            "bid_open_date": dates,
            "unit_price": actual,
            "q10": np.exp(-0.5) * np.ones(n),
            "q90": np.exp(0.5) * np.ones(n),  # too narrow
            "lump_sum": False,
        }
    )
    out = calibrate(df)
    t = out[out["kind"] == "test"]
    inside = (t["unit_price"] >= t["low"]) & (t["unit_price"] <= t["high"])
    assert 0.76 <= inside.mean() <= 0.84
    assert (t["adjustment"] > 0).all()


def _history():
    return pd.DataFrame(
        {
            "item_code": ["390132"] * 4 + ["120100"],
            "unit": ["TON"] * 4 + ["LS"],
            "bid_open_date": pd.to_datetime(
                ["2023-01-01", "2023-06-01", "2023-06-01", "2024-06-01", "2023-01-01"]
            ),
            "quantity": [100.0, 1000.0, 110.0, 100.0, 1.0],
            "unit_price": [120.0, 80.0, 115.0, 999.0, 5e4],
            "district": ["04", "04", "05", "04", "04"],
            "engineers_estimate": [1e6, 1e6, np.nan, 1e6, 1e6],
            "contract_number": ["A", "B", "C", "D", "E"],
            "source_row_id": [1, 2, 3, 4, 5],
        }
    )


def test_comparables_same_item_earlier_and_ranked_by_closeness():
    f = ComparableFinder(_history())
    c = f.find("390132", "TON", "2024-01-01", 105.0, "04", 1e6)
    # A: 0.05 quantity + 0.50 age = 0.55; C: 0.05 + 0.29 + 0.50 other district = 0.84.
    assert list(c["contract_number"]) == ["A", "C", "B"]  # D (later) never appears
    assert c["source"].iloc[1].endswith("Num=3")
    assert f.find("390132", "TON", "2022-01-01", 100.0, "04", 1e6).empty
    assert f.find("999999", "EA", "2024-01-01", 1.0, "04", 1e6).empty
