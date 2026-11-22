"""Step 2.6: comparable past bids for a priced item.

For an item to be priced, the 10 earlier low bids for the same item code and unit,
ranked by distance = |log quantity difference| + 0.5 x years apart + 0.5 if another
district + 0.25 x |log engineer's estimate difference| (0 when either is missing).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bidlens.pricing.setup import escalate

N_COMPARABLES = 10
W_YEARS = 0.5
W_DISTRICT = 0.5
W_SIZE = 0.25
SOURCE_URL = "https://sv08data.dot.ca.gov/details.php?Num={}"


class ComparableFinder:
    """Index of earlier low bids, grouped by (item code, unit)."""

    def __init__(self, history: pd.DataFrame) -> None:
        """`history`: cleaned low bids with item_code, unit, bid_open_date, quantity,
        unit_price, district, engineers_estimate, contract_number, source_row_id."""
        h = history.sort_values("bid_open_date", kind="stable")
        self._groups = {k: g.reset_index(drop=True) for k, g in h.groupby(["item_code", "unit"])}

    def find(
        self, item_code, unit, on, quantity, district, engineers_estimate, n: int = N_COMPARABLES
    ) -> pd.DataFrame:
        g = self._groups.get((item_code, unit))
        if g is None:
            return pd.DataFrame()
        on = pd.Timestamp(on)
        g = g[g["bid_open_date"] < on]
        if g.empty:
            return g
        dist = np.abs(np.log(g["quantity"].to_numpy()) - np.log(quantity))
        dist += W_YEARS * (on - g["bid_open_date"]).dt.days.to_numpy() / 365.25
        dist += W_DISTRICT * (g["district"].to_numpy() != district)
        ee = g["engineers_estimate"].to_numpy(dtype=float)
        size = np.abs(np.log(ee) - np.log(engineers_estimate)) if engineers_estimate else np.nan
        dist += W_SIZE * np.nan_to_num(size, nan=0.0)
        top = np.argsort(dist, kind="stable")[:n]
        out = g.iloc[top].copy()
        out["distance"] = dist[top]
        out["unit_price_in_query_dollars"] = escalate(
            out["unit_price"].to_numpy(), out["bid_open_date"], on
        )
        out["source"] = out["source_row_id"].map(SOURCE_URL.format)
        return out[
            [
                "contract_number",
                "bid_open_date",
                "district",
                "quantity",
                "unit_price",
                "unit_price_in_query_dollars",
                "distance",
                "source",
            ]
        ]
