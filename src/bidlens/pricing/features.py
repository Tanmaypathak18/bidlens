"""Model features for item unit prices (step 2.3, decision D-041).

Every feature is known before bids open. History features use only strictly earlier bids.
"""

from __future__ import annotations

import re
from datetime import date

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing.benchmarks import TRAILING_DAYS, History, item_history
from bidlens.pricing.setup import escalate

REF_DATE = date(2023, 12, 31)  # target dollars: 2023 Q4 (the last training quarter)
START = pd.Timestamp("2018-01-01")

WORK_TYPES = {
    "wt_paving": r"RHMA|\bHMA\b|OVERLAY|ASPHALT|PAVING|PAVEMENT|COLD PLANE|\bMILL|\bAC\b|SEAL",
    "wt_bridge": r"BRIDGE|\bDECK|STRUCTURE|OVERCROSSING|VIADUCT",
    "wt_electrical": r"SIGNAL|LIGHTING|ELECTRICAL|\bTMS\b|\bITS\b|CCTV|RAMP METER|DETECTION",
    "wt_drainage": r"CULVERT|DRAIN",
    "wt_safety": r"GUARDRAIL|BARRIER|SAFETY|\bMBGR\b|\bMGS\b|RUMBLE|CRASH CUSHION",
    "wt_landscape": r"LANDSCAP|PLANT|IRRIGAT|EROSION|HIGHWAY PLANTING",
    "wt_concrete_pavement": r"SLAB|CONCRETE PAVEMENT|\bJPCP\b|\bPCC\b|\bRSC\b",
    "wt_signs": r"\bSIGN",
    "wt_slope_storm": r"SLIDE|SLOPE|STORM|EMERGENCY|SLIP|WALL|EMBANKMENT|SINK",
    "wt_pedestrian": r"CURB RAMP|\bADA\b|SIDEWALK|PEDESTRIAN|BIKE|BICYCLE",
}

CATEGORICAL = ["item_code", "item_family", "unit", "district", "county"]
NUMERIC = [
    "log_quantity",
    "log_quantity_vs_history",
    "bid_quarter",
    "months_since_2018",
    "log_engineers_estimate",
    "log_working_days",
    "n_items",
    *WORK_TYPES,
    "log_trailing_median",
    "n_history",
]
FEATURES = CATEGORICAL + NUMERIC


def load_model_rows(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Every low-bid price with the contract fields the features need."""
    from bidlens.pricing.setup import load_low_bids

    low = load_low_bids(con)
    contracts = con.execute(
        """
        SELECT contract_id, county, type_of_work, n_items, working_days,
               CAST(engineers_estimate AS DOUBLE) AS engineers_estimate
        FROM contract
        ORDER BY contract_id
        """
    ).df()
    return low.merge(contracts, on="contract_id", how="left")


def work_type_flags(descriptions: pd.Series) -> pd.DataFrame:
    text = descriptions.fillna("").str.upper()
    return pd.DataFrame(
        {k: text.str.contains(re.compile(v)).astype(float) for k, v in WORK_TYPES.items()},
        index=descriptions.index,
    )


def history_features(rows: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """Trailing median price (in REF_DATE dollars), its count, and the earlier median
    quantity, from strictly earlier low bids in `low`."""
    prices = item_history(low)
    keys = list(zip(low["item_code"], low["unit"], strict=True))
    quantities = History(keys, low["bid_open_date"], low["quantity"].to_numpy(dtype=float))
    tm, n, q = [], [], []
    for code, unit, on in zip(rows["item_code"], rows["unit"], rows["bid_open_date"], strict=True):
        m, k = prices.median((code, unit), on, TRAILING_DAYS)
        tm.append(m)
        n.append(k)
        q.append(quantities.median((code, unit), on, escalated=False)[0])
    tm_ref = to_ref(np.array(tm), rows["bid_open_date"])
    return pd.DataFrame(
        {"trailing_median_ref": tm_ref, "n_history": n, "history_quantity": q}, index=rows.index
    )


def to_ref(prices, dates) -> np.ndarray:
    """Prices at their own dates -> REF_DATE dollars."""
    return escalate(prices, dates, REF_DATE)


def from_ref(prices, dates) -> np.ndarray:
    """REF_DATE dollars -> each row's own date."""
    prices = np.asarray(prices, dtype=float)
    dates = pd.to_datetime(pd.Series(dates))
    one = np.ones(len(prices))
    return prices / escalate(one, dates, REF_DATE)


def build(rows: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """Feature frame for `rows` (with contract fields), using history from `low`."""
    h = history_features(rows, low)
    d = pd.to_datetime(rows["bid_open_date"])
    f = pd.DataFrame(index=rows.index)
    for c in CATEGORICAL:
        f[c] = rows[c].astype("string")
    f["log_quantity"] = np.log(rows["quantity"].astype(float))
    f["log_quantity_vs_history"] = f["log_quantity"] - np.log(h["history_quantity"])
    f["bid_quarter"] = d.dt.quarter.astype(float)
    f["months_since_2018"] = (d.dt.year - START.year) * 12 + d.dt.month - START.month
    f["log_engineers_estimate"] = np.log(rows["engineers_estimate"].astype(float))
    f["log_working_days"] = np.log(rows["working_days"].astype(float))
    f["n_items"] = rows["n_items"].astype(float)
    f = f.join(work_type_flags(rows["type_of_work"]))
    f["log_trailing_median"] = np.log(h["trailing_median_ref"])
    f["n_history"] = h["n_history"].astype(float)
    return f[FEATURES]


def as_categories(f: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Categorical columns with the training categories (unseen values become missing)."""
    f = f.copy()
    for c in CATEGORICAL:
        f[c] = pd.Categorical(f[c], categories=categories[c])
    return f
