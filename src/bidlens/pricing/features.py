"""Model features for item unit prices (step 2.3).

Every feature is known before bids open. History features use only strictly earlier bids.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

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


# ----------------------------------------------------------------- shared data setup
# Kept here, free of XGBoost, LightGBM and PyTorch imports: their OpenMP runtimes must
# never load into one process (they crash on macOS), so each model runs in its own process.

LINE_PREDICTIONS = Path("data") / "interim" / "line_predictions_{model}.parquet"
LINE_KEY = ["contract_number", "bid_open_date", "item_no"]


def prepare(con: duckdb.DuckDBPyConnection):
    """Rows, features, target, training mask, test rows and training categories."""
    from bidlens.pricing.setup import select_test

    rows = load_model_rows(con)
    X_all = build(rows, rows)
    y_all = np.log(to_ref(rows["unit_price"].clip(lower=1e-9), rows["bid_open_date"]))
    train_mask = (
        (rows["split"] == "train")
        & ~rows["low_bidder_disagrees"]
        & ~rows["is_outlier"]
        & (rows["unit_price"] > 0)
    )
    test = select_test(rows)
    cats = {c: sorted(X_all.loc[train_mask, c].dropna().unique()) for c in CATEGORICAL}
    X_all = as_categories(X_all, cats)
    return rows, X_all, y_all, train_mask, test, cats


def contract_lines(con: duckdb.DuckDBPyConnection, rows: pd.DataFrame, cats: dict):
    """Bid-list lines of the test contracts, priced by the history tiers (`base`), plus the
    model features of the top-100 lines (`X_lines`, indexed like `base`)."""
    from bidlens.pricing.benchmarks import LinePricer, prepare_lines
    from bidlens.pricing.compare import ITEMS, load_contracts, load_scope

    contracts = load_contracts(con)
    master = con.execute("SELECT item_code, unit, item_family FROM item_master ORDER BY 1").df()
    raw = con.execute(
        f"SELECT * FROM read_parquet('{ITEMS}') ORDER BY contract_number, bid_open_date, item_no"
    ).df()
    lines = prepare_lines(raw, master)
    scope = load_scope()
    keys = contracts[["contract_number", "bid_open_date"]].assign(
        bid_open_date=lambda d: pd.to_datetime(d["bid_open_date"])
    )
    targets = lines.merge(keys, on=["contract_number", "bid_open_date"], how="inner")
    base = LinePricer(rows, lines, scope).price_lines(targets)
    in_scope = np.array(
        [(c, u) in scope for c, u in zip(base["item_code"], base["unit"], strict=True)]
    )
    info = con.execute(
        """SELECT contract_number, bid_open_date, district, county, type_of_work, n_items,
                  working_days, CAST(engineers_estimate AS DOUBLE) AS engineers_estimate
           FROM contract"""
    ).df()
    info["bid_open_date"] = pd.to_datetime(info["bid_open_date"])
    sel = base[in_scope].merge(info, on=["contract_number", "bid_open_date"], how="left")
    sel.index = base.index[in_scope]
    X_lines = as_categories(build(sel, rows), cats)
    return contracts, base, sel, X_lines


def save_line_predictions(model: str, sel: pd.DataFrame, log_ref_pred) -> Path:
    """Store a model's unit prices (bid-date dollars) for the top-100 contract lines."""
    out = sel[LINE_KEY].copy()
    out["pred_unit_price"] = from_ref(np.exp(log_ref_pred), sel["bid_open_date"])
    path = Path(str(LINE_PREDICTIONS).format(model=model))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return path
