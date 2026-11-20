"""Step 2.3 tests: features and the baseline training loop, on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bidlens.pricing import baseline as BL
from bidlens.pricing import features as F
from bidlens.pricing.setup import add_split, use_cost_index


@pytest.fixture(autouse=True)
def _no_escalation():
    use_cost_index(None)
    yield
    use_cost_index(None)


def _rows(n=400, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime("2019-01-01") + pd.to_timedelta(rng.integers(0, 365 * 6, n), "D")
    code = rng.choice(["390132", "120100", "840515"], n)
    qty = np.exp(rng.uniform(0, 8, n))
    base = pd.Series(code).map({"390132": 120.0, "120100": 50000.0, "840515": 2.0}).to_numpy()
    price = base * qty**-0.2 * np.exp(rng.normal(0, 0.1, n))
    df = pd.DataFrame(
        {
            "bid_item_id": [f"b{i}" for i in range(n)],
            "contract_id": [f"c{i // 4}" for i in range(n)],
            "bid_open_date": dates,
            "item_code": code,
            "unit": pd.Series(code).map({"390132": "TON", "120100": "LS", "840515": "LF"}),
            "item_family": "Asphalt Surfacing",
            "district": rng.choice(["04", "05"], n),
            "county": rng.choice(["SON", "SLO", None], n),
            "quantity": qty,
            "unit_price": price,
            "type_of_work": rng.choice(
                ["COLD PLANE AC PAVEMENT AND OVERLAY", "REPLACE BRIDGE", None], n
            ),
            "n_items": rng.integers(10, 200, n).astype(float),
            "working_days": rng.integers(20, 400, n).astype(float),
            "engineers_estimate": np.where(rng.random(n) < 0.2, np.nan, rng.uniform(1e5, 5e7, n)),
            "is_outlier": False,
            "low_bidder_disagrees": False,
        }
    )
    return add_split(df.sort_values("bid_item_id").reset_index(drop=True))


def test_work_type_flags():
    f = F.work_type_flags(
        pd.Series(
            ["COLD PLANE AC PAVEMENT AND OVERLAY WITH RHMA", "REPLACE CULVERTS WITH BRIDGE", None]
        )
    )
    assert f.loc[0, "wt_paving"] == 1 and f.loc[0, "wt_bridge"] == 0
    assert f.loc[1, "wt_bridge"] == 1 and f.loc[1, "wt_drainage"] == 1
    assert f.loc[2].sum() == 0


def test_features_use_only_earlier_bids():
    rows = _rows()
    X = F.build(rows, rows)
    assert list(X.columns) == F.FEATURES
    first = rows.sort_values("bid_open_date").groupby(["item_code", "unit"]).head(1).index
    # The first bid of each item has no history.
    assert X.loc[first, "n_history"].eq(0).all()
    assert X.loc[first, "log_trailing_median"].isna().all()
    # Changing a later price never changes an earlier row's features.
    late = rows["bid_open_date"].idxmax()
    rows2 = rows.copy()
    rows2.loc[late, "unit_price"] *= 1000
    X2 = F.build(rows2, rows2)
    pd.testing.assert_frame_equal(X.drop(index=late), X2.drop(index=late))


def test_ref_dollars_round_trip():
    p = np.array([10.0, 20.0])
    d = pd.Series(pd.to_datetime(["2020-01-01", "2025-06-01"]))
    np.testing.assert_allclose(F.from_ref(F.to_ref(p, d), d), p)


@pytest.mark.parametrize("kind", ["xgboost", "lightgbm"])
def test_baseline_learns_and_beats_a_constant(kind):
    rows = _rows(n=600)
    X = F.build(rows, rows)
    cats = {c: sorted(X[c].dropna().unique()) for c in F.CATEGORICAL}
    X = F.as_categories(X, cats)
    y = np.log(rows["unit_price"].to_numpy())
    tr = (rows["bid_open_date"] < "2023-01-01").to_numpy()
    params, trees, log = BL.tune(kind, X[tr], y[tr], X[~tr], y[~tr], trials=2)
    assert len(log) == 2 and trees >= 1
    m = BL.fit(kind, BL.make_model(kind, params, trees, BL.SEED, False), X[tr], y[tr])
    model_err = BL._mdape(m.predict(X[~tr]), y[~tr])
    const_err = BL._mdape(np.full((~tr).sum(), np.median(y[tr])), y[~tr])
    assert model_err < const_err / 2
