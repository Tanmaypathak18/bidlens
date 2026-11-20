"""Step 2.7 tests: market context features and the simple methods (no PyTorch here)."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from bidlens.market.context import _recent, cqr_add, linear


def test_module_does_not_load_pytorch_on_import():
    # The suite also loads XGBoost; PyTorch in the same process crashes on macOS.
    assert "torch" not in sys.modules or "xgboost" not in sys.modules


def test_recent_uses_only_the_previous_12_months():
    df = pd.DataFrame(
        {
            "bid_open_date": pd.to_datetime(
                ["2022-01-01", "2023-03-01", "2023-06-01", "2023-06-01"]
            ),
            "district": ["04", "04", "05", "04"],
            "spread": [-0.5, -0.1, 0.2, 9.0],
        }
    )
    all_d = _recent(df, "spread", False)
    same_d = _recent(df, "spread", True)
    assert np.isnan(all_d[0])
    assert np.isnan(all_d[1])  # 2022-01-01 is more than 12 months before 2023-03-01
    # 2023-06-01 rows see only 2023-03-01 (2022 is more than 12 months back; same day excluded).
    assert all_d[2] == pytest.approx(-0.1) and all_d[3] == pytest.approx(-0.1)
    assert np.isnan(same_d[2]) and same_d[3] == pytest.approx(-0.1)


def test_linear_recovers_a_linear_relation():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(
        {
            "a": rng.normal(size=300),
            "b": rng.normal(size=300),
            "district": rng.choice(["04", "05"], 300),
        }
    )
    y = 2 * X["a"] - X["b"] + 0.5 * (X["district"] == "05")
    p = linear(X[:250], y[:250], X[250:], ["a", "b"])
    assert np.abs(p - y[250:]).mean() < 0.05


def test_cqr_add_coverage():
    s = np.arange(100, dtype=float)
    assert cqr_add(s, 0.8) == 80.0
    assert cqr_add([], 0.8) == 0.0
