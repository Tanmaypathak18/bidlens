"""Step 2.1 tests: split, metrics and benchmarks, on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bidlens.pricing.benchmarks import (
    MIN_TRAILING,
    History,
    LinePricer,
    contract_totals,
    headline,
    item_history,
    norm_description,
    prepare_lines,
    trailing_median,
)
from bidlens.pricing.setup import (
    MIN_FAMILY_TEST,
    OTHER,
    add_split,
    ape,
    report_family,
    score,
    select_test,
    use_cost_index,
)


@pytest.fixture(autouse=True)
def _no_escalation():
    """These tests check the benchmarks on fixed prices, without a cost index."""
    use_cost_index(None)
    yield
    use_cost_index(None)


def _low(rows):
    df = pd.DataFrame(
        rows, columns=["contract_id", "bid_open_date", "item_code", "unit", "unit_price"]
    )
    df["bid_open_date"] = pd.to_datetime(df["bid_open_date"])
    df["item_family"] = "Asphalt Surfacing"
    df["is_outlier"] = False
    df["low_bidder_disagrees"] = False
    return add_split(df)


def test_split_is_by_date():
    df = _low(
        [
            ("a", "2023-12-31", "390132", "TON", 100.0),
            ("b", "2024-01-01", "390132", "TON", 100.0),
            ("c", "2026-11-03", "390132", "TON", 100.0),
            ("d", "2026-11-04", "390132", "TON", 100.0),
        ]
    )
    assert list(df["split"]) == ["train", "test", "test", "after"]


def test_test_rows_drop_flagged_contracts_and_zero_prices():
    df = _low(
        [
            ("a", "2024-02-01", "390132", "TON", 100.0),
            ("b", "2024-02-01", "390132", "TON", 0.0),
            ("c", "2024-02-01", "390132", "TON", 90.0),
        ]
    )
    df.loc[df["contract_id"] == "c", "low_bidder_disagrees"] = True
    assert list(select_test(df)["contract_id"]) == ["a"]


def test_metrics():
    df = pd.DataFrame(
        {"unit_price": [100.0, 100.0, 100.0, 100.0], "pred": [110.0, 80.0, 150.0, np.nan]}
    )
    np.testing.assert_allclose(ape([110.0], [100.0]), [0.1])
    s = score(df).iloc[0]
    assert s["n"] == 4
    assert s["coverage"] == pytest.approx(0.75)
    assert s["mdape"] == pytest.approx(0.2)
    assert s["within_15"] == pytest.approx(1 / 3)


def test_small_families_become_other():
    fam = pd.Series(["A"] * MIN_FAMILY_TEST + ["B"] * (MIN_FAMILY_TEST - 1) + [None])
    out = report_family(fam)
    assert set(out[:MIN_FAMILY_TEST]) == {"A"}
    assert set(out[MIN_FAMILY_TEST:]) == {OTHER}


def test_history_uses_only_earlier_dates_and_trailing_window():
    dates = ["2022-01-01", "2023-06-01", "2023-07-01", "2023-08-01", "2024-01-01"]
    h = History(["k"] * 5, dates, [1000.0, 10.0, 20.0, 30.0, 999.0])
    # Same-day and later prices are never used; the 12-month window drops 2022.
    assert h.median("k", "2024-01-01", 365) == (20.0, 3)
    # Without a window, all earlier prices count.
    assert h.median("k", "2024-01-01") == (25.0, 4)
    # Fewer than MIN_TRAILING in the window: fall back to all earlier prices.
    m, n = h.median("k", "2023-07-15", 30)
    assert (m, n) == (20.0, MIN_TRAILING)
    assert h.median("k", "2021-01-01", 365) == (pytest.approx(np.nan, nan_ok=True), 0)
    assert h.median("missing", "2024-01-01")[1] == 0


def test_trailing_median_never_sees_its_own_contract():
    low = _low(
        [
            ("a", "2023-01-10", "390132", "TON", 100.0),
            ("b", "2023-02-10", "390132", "TON", 120.0),
            ("c", "2024-03-01", "390132", "TON", 5000.0),
        ]
    )
    pred = trailing_median(select_test(low), item_history(low))
    assert pred["pred"].iloc[0] == pytest.approx(110.0)


def _lines():
    rows = [
        # contract, date, item_no, code, description, unit, qty, unit_price, amount
        ("X1", "2023-01-01", "1", "390132", "HMA (TYPE A)", "TON", 100.0, 100.0, 10000.0),
        ("X1", "2023-01-01", "2", "150000", "REMOVE THING", "EA", 2.0, 500.0, 1000.0),
        ("X1", "2023-01-01", "3", "012345", "Special Widget!", "EA", 1.0, 7000.0, 7000.0),
        ("X1", "2023-01-01", "4", "999990", "MOBILIZATION", "LS", None, 50000.0, 50000.0),
        ("T1", "2024-05-01", "1", "390132", "HMA (TYPE A)", "TON", 10.0, 90.0, 900.0),
        ("T1", "2024-05-01", "2", "150000", "REMOVE THING", "EA", 1.0, 600.0, 600.0),
        ("T1", "2024-05-01", "3", "019999", "SPECIAL WIDGET", "EA", 1.0, 8000.0, 8000.0),
        ("T1", "2024-05-01", "4", "014444", "NEVER SEEN", "LS", None, 3000.0, 3000.0),
        ("T1", "2024-05-01", "5", "999990", "MOBILIZATION", "LS", None, 40000.0, 40000.0),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "contract_number",
            "bid_open_date",
            "item_no",
            "item_code",
            "description",
            "unit",
            "quantity",
            "unit_price",
            "amount",
        ],
    )


def test_line_pricing_tiers_and_contract_total():
    master = pd.DataFrame(
        {
            "item_code": ["390132", "150000", "999990"],
            "unit": ["TON", "EA", "LS"],
            "item_family": ["Asphalt Surfacing", "Earthwork and Clearing", "General and Overhead"],
        }
    )
    lines = prepare_lines(_lines(), master)
    low = _low([("X1", "2023-01-01", "390132", "TON", 100.0)])
    pricer = LinePricer(low, lines, scope={("390132", "TON")})
    test = lines[lines["contract_number"] == "T1"]
    priced = pricer.price_lines(test).set_index("item_no")
    assert priced.loc["1", ["tier", "pred_unit_price"]].tolist() == [1, 100.0]
    assert priced.loc["2", ["tier", "pred_unit_price"]].tolist() == [2, 500.0]
    # Special item matched by description, ignoring case and punctuation.
    assert priced.loc["3", ["tier", "pred_unit_price"]].tolist() == [3, 7000.0]
    # Never seen, no family: median of earlier LS lines (the X1 mobilization).
    assert priced.loc["4", ["tier", "pred_unit_price"]].tolist() == [4, 50000.0]
    assert priced.loc["5", ["tier", "pred_unit_price"]].tolist() == [2, 50000.0]

    contracts = pd.DataFrame(
        {
            "contract_number": ["T1"],
            "bid_open_date": ["2024-05-01"],
            "engineers_estimate": [60000.0],
            "low_bid_cost": [52500.0],
        }
    )
    totals = contract_totals(pricer.price_lines(test), contracts)
    row = totals.iloc[0]
    assert row["bidlens_total"] == pytest.approx(10 * 100 + 500 + 7000 + 50000 + 50000)
    assert row["share_lines_item_level"] == pytest.approx(0.8)
    assert not row["in_headline"]
    assert row["bidlens_closer"] == (abs(row["bidlens_total"] - 52500) < abs(60000 - 52500))
    h = headline(totals)
    assert h["all_test_contracts"]["contracts"] == 1


def test_norm_description():
    assert norm_description("Special  Widget!") == norm_description("SPECIAL WIDGET")
