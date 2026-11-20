"""Step 2.1 benchmarks (decisions D-034, D-037, D-038).

1. Item level: the median escalated low-bid unit price for the same item and unit over the
   12 months before the bid date (all earlier history when fewer than 3 prices).
2. Contract level: a BidLens contract total that prices every line of the low bidder's item
   list, built only from contracts opened before the one being priced. Until the step 2.5
   model exists, the top-100 items are priced by benchmark 1.

Everything here takes plain DataFrames so tests can run without the database.
"""

from __future__ import annotations

import re
from collections.abc import Hashable

import numpy as np
import pandas as pd

from bidlens.pricing.setup import escalate

TRAILING_DAYS = 365
MIN_TRAILING = 3
SPECIAL_PREFIXES = ("01", "02", "03", "04")

TIERS = {
    1: "Top-100 item: trailing 12-month median",
    2: "Other standard item: median of earlier bids",
    3: "Special item: median of earlier bids with the same description",
    4: "Fallback: median for the same item family or unit",
    5: "Unpriced: no earlier bid with the same unit",
}
ITEM_LEVEL_TIERS = (1, 2, 3)


class History:
    """Earlier prices grouped by a key, sorted by bid date, for "before this date" medians."""

    def __init__(self, keys: list[Hashable], dates, prices) -> None:
        df = pd.DataFrame({"k": keys, "d": pd.to_datetime(pd.Series(dates)).values, "p": prices})
        df = df[df["p"].notna() & (df["p"] > 0)]
        self._groups: dict[Hashable, tuple[np.ndarray, np.ndarray]] = {}
        for k, g in df.groupby("k", sort=False):
            g = g.sort_values("d", kind="stable")
            self._groups[k] = (g["d"].values.astype("datetime64[D]"), g["p"].values)

    def median(self, key: Hashable, on, window_days: int | None = None) -> tuple[float, int]:
        """Median of prices strictly before `on`, escalated to `on`.

        With `window_days`, use only that many days before `on`, unless that leaves fewer
        than MIN_TRAILING prices; then use all earlier prices. Returns (median, count).
        """
        grp = self._groups.get(key)
        if grp is None:
            return np.nan, 0
        dates, prices = grp
        on = np.datetime64(pd.Timestamp(on).date(), "D")
        hi = int(np.searchsorted(dates, on, side="left"))
        if hi == 0:
            return np.nan, 0
        lo = 0
        if window_days is not None:
            w = int(np.searchsorted(dates, on - np.timedelta64(window_days, "D"), side="left"))
            if hi - w >= MIN_TRAILING:
                lo = w
        p = escalate(prices[lo:hi], dates[lo:hi], on)
        return float(np.median(p)), hi - lo


# ----------------------------------------------------------------- item level


def item_history(low: pd.DataFrame) -> History:
    """All low-bid (rank 1) prices from the cost database, keyed by (code, unit)."""
    keys = list(zip(low["item_code"], low["unit"], strict=True))
    return History(keys, low["bid_open_date"], low["unit_price"].to_numpy(dtype=float))


def trailing_median(targets: pd.DataFrame, hist: History) -> pd.DataFrame:
    """Benchmark 1 for each target row (needs item_code, unit, bid_open_date)."""
    out = [
        hist.median((c, u), d, TRAILING_DAYS)
        for c, u, d in zip(
            targets["item_code"], targets["unit"], targets["bid_open_date"], strict=True
        )
    ]
    res = targets.copy()
    res["pred"] = [m for m, _ in out]
    res["n_history"] = [n for _, n in out]
    return res


# ------------------------------------------------------------- contract level


def norm_description(text: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (text or "").upper()).strip()


def is_special(code: str) -> bool:
    return str(code)[:2] in SPECIAL_PREFIXES


def prepare_lines(lines: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Low-bidder item lines from the bid summaries, ready for pricing.

    `lines` has contract_number, bid_open_date, item_no, item_code, description, unit,
    quantity, unit_price, amount. `master` has item_code, unit, item_family.
    """
    m = master[["item_code", "unit", "item_family"]].rename(columns={"unit": "master_unit"})
    df = lines.merge(m, on="item_code", how="left")
    df["unit"] = df["unit"].fillna(df["master_unit"])
    lump = df["quantity"].isna()
    df["quantity"] = df["quantity"].fillna(1.0)
    # Lump sum: one unit priced at the line amount.
    df["unit_price"] = np.where(lump, df["amount"], df["unit_price"])
    df["special"] = df["item_code"].map(is_special)
    df["desc_key"] = df["description"].map(norm_description)
    df["bid_open_date"] = pd.to_datetime(df["bid_open_date"])
    return df.drop(columns=["master_unit"])


class LinePricer:
    """Prices bid summary lines by the D-038 tiers, using only earlier contracts."""

    def __init__(self, low: pd.DataFrame, lines: pd.DataFrame, scope: set[tuple[str, str]]) -> None:
        self.scope = scope
        self.tier1 = item_history(low)
        d, p = lines["bid_open_date"], lines["unit_price"].to_numpy(dtype=float)
        unit = lines["unit"]
        self.tier2 = History(list(zip(lines["item_code"], unit, strict=True)), d, p)
        self.tier3 = History(list(zip(lines["desc_key"], unit, strict=True)), d, p)
        self.family = History(list(zip(lines["item_family"], unit, strict=True)), d, p)
        self.unit = History(list(unit), d, p)

    def price(self, row) -> tuple[float, int, int]:
        """Returns (unit price, tier, number of earlier prices used)."""
        on, code, unit = row.bid_open_date, row.item_code, row.unit
        if (code, unit) in self.scope:
            m, n = self.tier1.median((code, unit), on, TRAILING_DAYS)
            if n:
                return m, 1, n
        if not row.special:
            m, n = self.tier2.median((code, unit), on)
            if n:
                return m, 2, n
        else:
            m, n = self.tier3.median((row.desc_key, unit), on)
            if n:
                return m, 3, n
        if isinstance(row.item_family, str):
            m, n = self.family.median((row.item_family, unit), on)
            if n:
                return m, 4, n
        m, n = self.unit.median(unit, on)
        if n:
            return m, 4, n
        return 0.0, 5, 0

    def price_lines(self, lines: pd.DataFrame) -> pd.DataFrame:
        out = [self.price(r) for r in lines.itertuples(index=False)]
        res = lines.copy()
        res["pred_unit_price"] = [o[0] for o in out]
        res["tier"] = [o[1] for o in out]
        res["n_history"] = [o[2] for o in out]
        res["pred_amount"] = res["pred_unit_price"] * res["quantity"]
        return res


def contract_totals(
    priced: pd.DataFrame, contracts: pd.DataFrame, min_item_level: float = 0.9
) -> pd.DataFrame:
    """One row per contract: BidLens total, engineer's estimate and low bid, with errors.

    `contracts` has contract_number, bid_open_date, engineers_estimate, low_bid_cost.
    `in_headline` marks contracts where at least `min_item_level` of lines have item-level
    history (D-037); that is known before bid, so it is not a peek at the result.
    """
    g = priced.assign(
        item_level=priced["tier"].isin(ITEM_LEVEL_TIERS),
        **{f"tier{t}_amount": priced["pred_amount"].where(priced["tier"] == t, 0.0) for t in TIERS},
    ).groupby(["contract_number", "bid_open_date"], as_index=False)
    agg = g.agg(
        n_lines=("tier", "size"),
        share_lines_item_level=("item_level", "mean"),
        bidlens_total=("pred_amount", "sum"),
        **{f"tier{t}_amount": (f"tier{t}_amount", "sum") for t in TIERS},
    )
    for t in TIERS:
        agg[f"tier{t}_share"] = agg[f"tier{t}_amount"] / agg["bidlens_total"]
        agg = agg.drop(columns=f"tier{t}_amount")
    c = contracts.copy()
    c["bid_open_date"] = pd.to_datetime(c["bid_open_date"])
    df = c.merge(agg, on=["contract_number", "bid_open_date"], how="inner")
    low = df["low_bid_cost"].astype(float)
    ee = df["engineers_estimate"].astype(float)
    df["bidlens_error"] = (df["bidlens_total"] - low) / low
    df["ee_error"] = (ee - low) / low
    df["bidlens_closer"] = df["bidlens_error"].abs() < df["ee_error"].abs()
    df["in_headline"] = df["share_lines_item_level"] >= min_item_level
    return df


def headline(totals: pd.DataFrame) -> dict:
    """How often BidLens lands closer to the low bid than the engineer's estimate."""

    def _one(df: pd.DataFrame) -> dict:
        return {
            "contracts": int(len(df)),
            "bidlens_closer_share": float(df["bidlens_closer"].mean()),
            "bidlens_median_abs_error": float(df["bidlens_error"].abs().median()),
            "ee_median_abs_error": float(df["ee_error"].abs().median()),
            "bidlens_median_error": float(df["bidlens_error"].median()),
            "ee_median_error": float(df["ee_error"].median()),
            "bidlens_within_15": float((df["bidlens_error"].abs() <= 0.15).mean()),
            "ee_within_15": float((df["ee_error"].abs() <= 0.15).mean()),
        }

    return {
        "headline": _one(totals[totals["in_headline"]]),
        "all_test_contracts": _one(totals),
    }
