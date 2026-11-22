"""Step 2.1: target, time split and metrics.

- Target: log of the escalated low-bid (rank 1) unit price (escalation: step 2.2).
  Models predict the log; the metrics below are computed on prices.
- Split: train on bids opened before CUTOFF, test on CUTOFF to TEST_END.
- The test set drops contracts flagged `low_bidder_disagrees` and prices that are zero or
  negative (a percentage error is undefined). Flagged price outliers stay in; results are
  reported with and without them.
- Metrics: median absolute percentage error (MdAPE) and the share within 15% of the
  low-bid unit price, per item family. Families with fewer than MIN_FAMILY_TEST test prices
  are reported together as "Other".
"""

from __future__ import annotations

from datetime import date

import duckdb
import numpy as np
import pandas as pd

CUTOFF = date(2024, 1, 1)
TEST_END = date(2026, 11, 3)
WITHIN = 0.15
MIN_FAMILY_TEST = 20
OTHER = "Other"


_UNSET = object()
_cost_index = _UNSET


def use_cost_index(index) -> None:
    """Set the cost index used by `escalate` (a `CostIndex`), or None for no escalation.

    Scripts call `use_cost_index(CostIndex.from_db(con))`; tests may pass None.
    """
    global _cost_index
    _cost_index = index


def escalate(prices, from_dates, to_date) -> np.ndarray:
    """Bring prices from their bid dates to `to_date` dollars.

    Every price that crosses dates goes through here. Raises if no index was set, so
    unescalated prices can't slip through by accident.
    """
    if _cost_index is _UNSET:
        raise RuntimeError("no cost index set: call use_cost_index() first")
    if _cost_index is None:
        return np.asarray(prices, dtype=float)
    return _cost_index.escalate(prices, from_dates, to_date)


def target(unit_price) -> np.ndarray:
    """Model target: log of the (escalated) unit price."""
    return np.log(np.asarray(unit_price, dtype=float))


def load_low_bids(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Every low-bid (rank 1) price, with its split label and flags."""
    df = con.execute(
        """
        SELECT n.bid_item_id, n.contract_id, c.contract_number, c.bid_open_date,
               c.district, n.item_code, n.unit, n.item_family,
               CAST(n.quantity AS DOUBLE) AS quantity,
               CAST(n.unit_price AS DOUBLE) AS unit_price,
               EXISTS (SELECT 1 FROM bid_flag f WHERE f.bid_item_id = n.bid_item_id
                       AND f.bid_rank = n.bid_rank AND f.flag = 'price_outlier') AS is_outlier,
               EXISTS (SELECT 1 FROM contract_flag cf WHERE cf.contract_id = n.contract_id
                       AND cf.flag = 'low_bidder_disagrees') AS low_bidder_disagrees
        FROM bid_normalized n JOIN contract c USING (contract_id)
        WHERE n.bid_rank = 1
        ORDER BY n.bid_item_id  -- fixed row order: models depend on it
        """
    ).df()
    df["bid_open_date"] = pd.to_datetime(df["bid_open_date"])
    return add_split(df)


def add_split(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["bid_open_date"])
    df = df.copy()
    df["split"] = np.where(
        d < pd.Timestamp(CUTOFF),
        "train",
        np.where(d <= pd.Timestamp(TEST_END), "test", "after"),
    )
    return df


def select_test(low: pd.DataFrame) -> pd.DataFrame:
    keep = (low["split"] == "test") & ~low["low_bidder_disagrees"] & (low["unit_price"] > 0)
    return low[keep].copy()


def report_family(families: pd.Series) -> pd.Series:
    """Item family for reporting: families with too few test prices become "Other"."""
    fam = families.fillna(OTHER)
    counts = fam.value_counts()
    small = counts[counts < MIN_FAMILY_TEST].index
    return fam.where(~fam.isin(small), OTHER)


def ape(pred, actual) -> np.ndarray:
    pred = np.asarray(pred, dtype=float)
    actual = np.asarray(actual, dtype=float)
    return np.abs(pred - actual) / actual


def score(df: pd.DataFrame, by: str | None = None, pred: str = "pred") -> pd.DataFrame:
    """MdAPE and share within 15%, over rows that have a prediction.

    `n` counts every row; `coverage` is the share with a prediction.
    """

    def _one(g: pd.DataFrame) -> pd.Series:
        has = g[pred].notna()
        e = ape(g.loc[has, pred], g.loc[has, "unit_price"])
        return pd.Series(
            {
                "n": len(g),
                "coverage": has.mean() if len(g) else np.nan,
                "mdape": float(np.median(e)) if len(e) else np.nan,
                "within_15": float((e <= WITHIN).mean()) if len(e) else np.nan,
            }
        )

    if by is None:
        return (
            _one(df)
            .to_frame()
            .T.assign(group="All")[["group", "n", "coverage", "mdape", "within_15"]]
        )
    out = df.groupby(by, sort=True).apply(_one, include_groups=False).reset_index()
    out = out.rename(columns={by: "group"})
    out = out.sort_values("n", ascending=False, kind="stable")
    total = _one(df).to_frame().T.assign(group="All")
    return pd.concat([out, total], ignore_index=True)[
        ["group", "n", "coverage", "mdape", "within_15"]
    ]
