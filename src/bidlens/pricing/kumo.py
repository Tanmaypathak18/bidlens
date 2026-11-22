"""Step 2.4: NVIDIA Kumo Tabular on the step 2.1 split.

Usage:
    uv run python -m bidlens.pricing.kumo     # writes outputs/11_kumo_tabular

Kumo Tabular is a pretrained tabular foundation model: it is not trained on our data.
It reads a "context" table of known prices (here, every cleaned training bid) and predicts
the prices of new rows from it in one pass. Same features and target as the baselines.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import sdm
import torch

from bidlens.pricing import features as F
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import CUTOFF, report_family, score, use_cost_index

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "11_kumo_tabular"
SIZE = "small"
SEED = 0
REVISION = "v1.0.1"


class KumoPricer:
    """Kumo Tabular regression with a fixed context of known (features, log price) rows."""

    def __init__(self, size: str = SIZE, device: str = "cpu") -> None:
        self.sdm = sdm
        self.device = device
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = sdm.models.KumoTabular(task="regression", size=size, device=device)

    @staticmethod
    def _frame(X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        for c in F.CATEGORICAL:
            out[c] = out[c].astype(object).where(out[c].notna(), "<missing>").astype(str)
        return out

    def predict(
        self, X_ctx: pd.DataFrame, y_ctx, X_query: pd.DataFrame, with_range: bool = False
    ) -> np.ndarray:
        """Median predicted log price for each query row. With `with_range`, an array of
        three columns: the median, 10th and 90th percentile."""
        df = pd.concat(
            [
                self._frame(X_ctx).assign(target=np.asarray(y_ctx, dtype=float)),
                self._frame(X_query).assign(target=0.0),
            ],
            ignore_index=True,
        )
        stypes = self.sdm.infer_stypes(
            df, overrides={c: self.sdm.Stype.categorical for c in F.CATEGORICAL}
        )
        tab = self.sdm.TableTensor.from_pandas(df, stypes=stypes, device=self.device)
        n = len(X_ctx)
        with warnings.catch_warnings(), torch.no_grad():
            warnings.simplefilter("ignore")
            out = self.model(
                x_context=tab[:n].drop_columns("target"),
                y_context=tab[:n]["target"],
                x_query=tab[n:].drop_columns("target"),
                generator=torch.Generator(device=self.device).manual_seed(SEED),
            )
        cols = ["q500", "q100", "q900"] if with_range else ["q500"]
        res = np.column_stack([out[q].numerical.squeeze(-1).cpu().numpy() for q in cols])
        return res if with_range else res[:, 0]


def run(con) -> dict:
    # Never import XGBoost or LightGBM here: see features.py.
    rows, X, y, train_mask, test, cats = F.prepare(con)
    _, _, sel, X_lines = F.contract_lines(con, rows, cats)
    pricer = KumoPricer()
    t0 = time.perf_counter()
    p_log = pricer.predict(X[train_mask], y[train_mask], X.loc[test.index])
    infer_s = time.perf_counter() - t0
    F.save_line_predictions("kumo", sel, pricer.predict(X[train_mask], y[train_mask], X_lines))
    pred = test.copy()
    pred["family"] = report_family(pred["item_family"])
    pred["year"] = pred["bid_open_date"].dt.year
    pred["kumo"] = F.from_ref(np.exp(p_log), test["bid_open_date"])
    return {"pred": pred, "infer_seconds": infer_s, "context_rows": int(train_mask.sum())}


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write_outputs(out: Path, res: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pred = res["pred"]
    base = pd.read_csv(
        ROOT / "outputs" / "10_baselines" / "predictions.csv", dtype={"bid_item_id": str}
    )
    pred = pred.merge(
        base[["bid_item_id", "trailing_median", "xgboost", "lightgbm"]],
        on="bid_item_id",
        how="left",
    )
    models = ["trailing_median", "xgboost", "lightgbm", "kumo"]
    labels = {
        "trailing_median": "Median",
        "xgboost": "XGBoost",
        "lightgbm": "LightGBM",
        "kumo": "Kumo",
    }
    tables = []
    for label, df in (("all prices", pred), ("without outliers", pred[~pred["is_outlier"]])):
        for by in ("family", "year"):
            for col in models:
                t = score(df, by, pred=col)
                t.insert(0, "model", col)
                t.insert(0, "by", by)
                t.insert(0, "test_set", label)
                tables.append(t)
    scores = pd.concat(tables, ignore_index=True)
    scores.to_csv(out / "scores.csv", index=False, float_format="%.4f")
    pred[
        [
            "bid_item_id",
            "contract_number",
            "bid_open_date",
            "item_code",
            "unit",
            "family",
            "quantity",
            "unit_price",
            "kumo",
            "is_outlier",
        ]
    ].rename(columns={"unit_price": "low_bid_unit_price"}).to_csv(
        out / "predictions.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d"
    )

    fam = scores[(scores["test_set"] == "all prices") & (scores["by"] == "family")]
    md = fam.pivot_table(index="group", columns="model", values="mdape", sort=False)
    wi = fam.pivot_table(index="group", columns="model", values="within_15", sort=False)
    n = fam[fam["model"] == "kumo"].set_index("group")["n"]
    head = "| Item family | Prices | " + " | ".join(labels[m] for m in models) + " | Best |"
    lines = [head, "| --- | ---: |" + " ---: |" * len(models) + " --- |"]
    kumo_wins = []
    for g in n.index:
        best = min(models, key=lambda m: md.loc[g, m])
        if best == "kumo" and g != "All":
            kumo_wins.append(g)
        lines.append(
            f"| {g} | {int(n[g]):,} | "
            + " | ".join(_pct(md.loc[g, m]) for m in models)
            + f" | {labels[best]} |"
        )
    clean = scores[
        (scores["test_set"] == "without outliers")
        & (scores["by"] == "family")
        & (scores["group"] == "All")
    ].set_index("model")["mdape"]
    year = scores[(scores["test_set"] == "all prices") & (scores["by"] == "year")]
    ywide = year.pivot_table(index="group", columns="model", values="mdape", sort=False)
    ylines = [
        "| Bid year | " + " | ".join(labels[m] for m in models) + " |",
        "| --- |" + " ---: |" * len(models),
    ]
    for g, r in ywide.iterrows():
        ylines.append(f"| {g} | " + " | ".join(_pct(r[m]) for m in models) + " |")

    body = f"""
NVIDIA Kumo Tabular, a pretrained model for tables, scored on the same test as the
baselines (step 2.4).

## What we did

Kumo Tabular is not trained on our data. It is given a table of known prices (every
cleaned training bid before {CUTOFF:%d %B %Y}: {res["context_rows"]:,} rows, with the same
22 facts per bid as the baselines) and predicts each test price from it in one pass. It
runs on this Mac's processor with NVIDIA's small model, downloaded once
from Hugging Face (`nvidia/Kumo-Tabular`, version {REVISION}).

Settings were chosen on 2023 bids before looking at the test: one shared table of known
prices beat separate tables per item family (36.8% vs 38.4% median miss), and the small
model beat the medium one (36.8% vs 37.2%) at a third of the time.

## Results

All {len(pred):,} test prices: Kumo misses the low-bid unit price by a median of
**{_pct(md.loc["All", "kumo"])}** and is within 15% on {_pct(wi.loc["All", "kumo"])} of them,
against {_pct(md.loc["All", "lightgbm"])} and {_pct(wi.loc["All", "lightgbm"])} for LightGBM,
{_pct(md.loc["All", "xgboost"])} and {_pct(wi.loc["All", "xgboost"])} for XGBoost, and
{_pct(md.loc["All", "trailing_median"])} and {_pct(wi.loc["All", "trailing_median"])} for the
trailing median. Without flagged outliers, Kumo: {_pct(clean["kumo"])}.

Median miss by item family ("Best" is the lowest):

{chr(10).join(lines)}

Kumo is best in: {", ".join(kumo_wins) if kumo_wins else "none"}.

By bid year (median miss):

{chr(10).join(ylines)}

## Speed and licence

Pricing all {len(pred):,} test items took {res["infer_seconds"]:.1f} s on CPU, including
reading the {res["context_rows"]:,} context rows; there is no training step. The model code is
Apache-2.0 and the weights are OpenMDW-1.1 (both allow commercial use).

## Files

- `scores.csv`: median miss, within-15% and coverage for all four methods, by family and
  year, with and without outliers.
- `predictions.csv`: every test price with Kumo's prediction.

## How it was produced

`uv run python -m bidlens.pricing.kumo` (code in `src/bidlens/pricing/kumo.py`), after
`bidlens.pricing.baseline`. Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text("# 11 Kumo Tabular\n\n" + body.strip() + "\n", encoding="utf-8")
    summary = {
        "mdape": {m: float(md.loc["All", m]) for m in models},
        "within_15": {m: float(wi.loc["All", m]) for m in models},
        "kumo_without_outliers": float(clean["kumo"]),
        "families_where_kumo_best": kumo_wins,
        "infer_seconds": round(res["infer_seconds"], 1),
        "context_rows": res["context_rows"],
    }
    (out / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    res = run(con)
    con.close()
    summary = write_outputs(OUT, res)

    from bidlens.outputs import write_index

    write_index()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
