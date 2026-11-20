"""Step 2.2 tests: the recovered cost index and escalation (D-039, D-040)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bidlens.ingest.parse_sv08 import parse_adjusted
from bidlens.pricing import setup
from bidlens.pricing.escalate import CostIndex, implied_index, smooth

FIXTURE = Path("tests/fixtures/caltrans/results_item_district_year.html")


def test_parse_adjusted_reads_index_and_prices():
    page = parse_adjusted(FIXTURE.read_text())
    assert page.index_name == "CHCCI (2020 Base)"
    assert page.current_index == pytest.approx(146.53)
    contract, opened, price, adjusted = page.rows[0]
    assert (contract, opened, price, adjusted) == ("05-1R2904", date(2025, 2, 19), 575.0, 399.84)


def test_implied_index_recovers_the_quarter_value():
    q = implied_index([FIXTURE.read_text()])
    row = q[(q["year"] == 2025) & (q["quarter"] == 1)].iloc[0]
    assert row["value"] == pytest.approx(210.72, abs=0.01)
    assert row["spread"] < 0.001


def test_unadjusted_quarter_counts_as_unpublished():
    # Set every adjusted price equal to the original price before it.
    cell = r"<td style='text-align: right;'>"
    html = re.sub(
        rf"({cell}\$([\d.,]+)</td>\s*){cell}\$[\d.,]+</td>",
        rf"\1{cell}$\2</td>",
        FIXTURE.read_text(),
    )
    page = parse_adjusted(html)
    assert all(price == adjusted for _, _, price, adjusted in page.rows)
    q = implied_index([html])
    assert q["value"].isna().all()


def test_inconsistent_quarter_is_rejected():
    page = parse_adjusted(FIXTURE.read_text())
    _, _, price, adjusted = next(r for r in page.rows if r[2] >= 100)
    html = FIXTURE.read_text().replace(f"${adjusted:.2f}</td>", f"${adjusted * 0.9:.2f}</td>", 1)
    with pytest.raises(ValueError, match="inconsistent"):
        implied_index([html])


def _quarterly():
    return pd.DataFrame(
        {
            "year": [2023, 2023, 2023, 2023, 2024, 2024],
            "quarter": [1, 2, 3, 4, 1, 2],
            "value": [100.0, 110.0, 120.0, 130.0, 140.0, np.nan],
        }
    )


def test_smooth_uses_only_earlier_quarters_and_carries_forward():
    s = smooth(_quarterly(), through=date(2024, 11, 1)).set_index(["year", "quarter"])
    assert s.loc[(2023, 1), "value"] == 100.0  # first quarter: its own value
    assert s.loc[(2023, 2), "value"] == 100.0  # known before Q2: Q1 only
    assert s.loc[(2023, 3), "value"] == 105.0
    assert s.loc[(2024, 1), "value"] == pytest.approx(115.0)  # 2023 Q1..Q4
    assert s.loc[(2024, 2), "value"] == pytest.approx(125.0)  # 2023 Q2..2024 Q1
    assert s.loc[(2024, 4), "value"] == pytest.approx(125.0)  # unpublished: carried forward
    assert not s.loc[(2024, 2), "published"]


def test_cost_index_escalates_between_quarters():
    idx = CostIndex(smooth(_quarterly()))
    out = idx.escalate([100.0, 100.0], ["2023-02-10", "2023-08-01"], "2024-01-15")
    np.testing.assert_allclose(out, [115.0, 100 * 115 / 105])
    # Dates outside the series use its first or last value.
    assert idx.value(["2010-01-01", "2030-01-01"]).tolist() == [100.0, 125.0]


def test_escalate_refuses_to_run_without_an_index():
    setup.use_cost_index(setup._UNSET)
    with pytest.raises(RuntimeError, match="no cost index"):
        setup.escalate([1.0], ["2024-01-01"], "2024-01-01")
    setup.use_cost_index(None)
    assert setup.escalate([1.0], ["2024-01-01"], "2025-01-01").tolist() == [1.0]
