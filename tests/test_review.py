"""D-071: findings are checked against their own quotes before they are shown."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bidlens.documents.extract import TABLES
from bidlens.documents.review import faithful, tidy

ROOT = Path(__file__).resolve().parents[1]
CLOSURE_QUOTE = (
    "For each 10-minute interval or fraction thereof past the time specified to open the "
    "closure, the amount for liquidated damages per interval shown in the table below is "
    "deducted."
)


def row(statement, evidence, category="time_damages", source="model", value=""):
    return {"statement": statement, "evidence": evidence, "category": category,
            "source": source, "value": value}  # fmt: skip


def test_summary_that_mixes_two_damages_fails_the_check():
    mixed = (
        "Liquidated damages per day for late completion are $1,000 for the first half hour, "
        "increasing to higher amounts for subsequent intervals."
    )
    assert not faithful(mixed, CLOSURE_QUOTE)
    # A summary stating a number or a time unit its quote lacks also fails.
    assert not faithful("Submit within 7 days.", "Submit within 5 days.")
    assert not faithful("Submit within 5 hours.", "Submit within 5 days.")
    quote = "Liquidated damages are limited to 5 percent of the total bid per occurrence."
    assert faithful("Damages are limited to 5 percent of the total bid.", quote)


def test_failing_summary_is_replaced_by_its_quote():
    t = tidy(pd.DataFrame([row("Damages are $1,000 per day for late completion.", CLOSURE_QUOTE,
                               value="1000")]))  # fmt: skip
    r = t.iloc[0]
    assert r["as_quoted"] and r["statement"] == CLOSURE_QUOTE and r["value"] == ""
    assert r["model_summary"].startswith("Damages are $1,000")


def test_value_replaced_by_an_addendum_is_dropped_and_quotes_shown_once():
    meeting = "A mandatory prebid meeting is scheduled on September 10, 2026 at 10:00 a.m."
    items = pd.DataFrame([
        row("A mandatory prebid meeting is scheduled on September 2, 2026, at 10:00 a.m. "
            "(changed by addendum; was September 10, 2026 at 10:00 a.m.).",
            "A mandatory prebid meeting is scheduled on September 2, 2026, at 10:00 a.m.",
            "bid_requirements", "pattern"),
        row("You must attend a mandatory prebid meeting on September 10, 2026 at 10:00 a.m.",
            meeting, "scope"),
        row("A $6,000 withhold applies for each missing declaration.",
            "A $6,000 withhold applies for each missing declaration.", "time_damages"),
        row("A $6,000 withhold applies for each missing declaration.",
            "A $6,000 withhold applies for each missing declaration.", "payment", "pattern"),
    ])  # fmt: skip
    t = tidy(items)
    assert not t["statement"].str.contains("September 10, 2026 at 10:00 a.m.$").any()
    assert len(t[t["evidence"] == meeting]) == 0
    withhold = t[t["statement"].str.contains("6,000")]
    assert list(withhold["category"]) == ["payment"]


def test_sample_package_shows_no_unchecked_summary():
    run = json.loads((ROOT / "data/sample/app/04-0W0504/extraction_combined.json").read_text())
    items = pd.DataFrame(run["items"])
    t = tidy(items[~items["category"].isin(TABLES)])
    model = t[(t["source"].fillna("model") != "pattern") & ~t["as_quoted"]]
    assert all(faithful(s, e) for s, e in zip(model["statement"], model["evidence"], strict=True))
    assert not t["statement"].str.contains("half hour").any()
    assert not t["statement"].str.contains("September 10, 2026, at 10:00 a.m. via").any()


def test_returned_withhold_is_not_rated_a_risk():
    import sys

    sys.path.insert(0, str(ROOT / "app"))
    from design import severity

    assert severity("The Department returns the withhold within 30 days.") == "watch"
    assert severity("A $6,000 withhold applies for each missing declaration.") == "risk"
