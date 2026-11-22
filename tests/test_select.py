"""Step 2.5 test: the model selection rule."""

from __future__ import annotations

import pandas as pd

from bidlens.pricing.select import choose


def _val(n, fam, errors):
    """n validation prices of 100 in one family; each method misses by its error."""
    return pd.DataFrame(
        {
            "item_family": fam,
            "unit_price": [100.0] * n,
            **{m: [100.0 * (1 + e)] * n for m, e in errors.items()},
        }
    )


def test_default_is_best_overall_and_overrides_need_a_clear_margin():
    base = {"trailing_median": 0.5, "xgboost": 0.4, "lightgbm": 0.4, "kumo": 0.3}
    val = pd.concat(
        [
            _val(300, "A", base),
            _val(60, "B", {**base, "lightgbm": 0.2}),  # beats kumo by 10 points, 60 prices
            _val(60, "C", {**base, "xgboost": 0.27}),  # only 3 points better: no override
            _val(20, "D", {**base, "lightgbm": 0.1}),  # too few prices: no override
        ],
        ignore_index=True,
    )
    default, overrides, table = choose(val)
    assert default == "kumo"
    assert overrides == {"B": "lightgbm"}
    assert set(table["chosen"]) == {"kumo", "lightgbm"}
