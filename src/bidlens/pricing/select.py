"""Step 2.5: model comparison and selection.

Usage:
    uv run python -m bidlens.pricing.select    # writes outputs/13_model_comparison

Reads the predictions saved by `refresh` (one file per model), compares every method on
the test set (frozen at the cutoff and refreshed each quarter), chooses the production
model on 2023 validation bids, and saves the choice to data/models/production.json.
No model library is imported here.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.pricing import features as F
from bidlens.pricing.benchmarks import contract_totals, headline, item_history, trailing_median
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.refresh import OUT as REFRESH
from bidlens.pricing.setup import WITHIN, ape, report_family, use_cost_index

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "13_model_comparison"
PRODUCTION = ROOT / "data" / "models" / "production.json"
MODELS = ["xgboost", "lightgbm", "kumo"]
METHODS = ["trailing_median", *MODELS]
LABELS = {
    "trailing_median": "Historical median",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "kumo": "Kumo Tabular",
    "production": "BidLens (chosen)",
}
OVERRIDE_POINTS = 0.05
OVERRIDE_MIN_PRICES = 50
LICENCES = {
    "trailing_median": "None needed (simple statistic)",
    "xgboost": "Apache-2.0",
    "lightgbm": "MIT",
    "kumo": "Code Apache-2.0; weights OpenMDW-1.1",
}


def _mdape(pred, actual) -> float:
    e = ape(pred, actual)
    e = e[~np.isnan(e)]
    return float(np.median(e)) if len(e) else np.nan


def load_refresh(model: str) -> pd.DataFrame:
    return pd.read_parquet(Path(str(REFRESH).format(model=model)))


def choose(val: pd.DataFrame) -> tuple[str, dict, pd.DataFrame]:
    """Selection rule: default = best overall validation MdAPE; family overrides by a margin."""
    overall = {m: _mdape(val[m], val["unit_price"]) for m in METHODS}
    default = min(overall, key=overall.get)
    rows, overrides = [], {}
    for fam, g in val.groupby("item_family"):
        s = {m: _mdape(g[m], g["unit_price"]) for m in METHODS}
        best = min(s, key=s.get)
        switch = (
            best != default
            and len(g) >= OVERRIDE_MIN_PRICES
            and s[default] - s[best] >= OVERRIDE_POINTS
        )
        if switch:
            overrides[fam] = best
        rows.append(
            {
                "item_family": fam,
                "validation_prices": len(g),
                **s,
                "chosen": best if switch else default,
            }
        )
    table = pd.DataFrame(rows).sort_values("validation_prices", ascending=False)
    return default, overrides, table.assign(**{"overall_" + m: overall[m] for m in METHODS})


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    con = duckdb.connect(str(DB), read_only=True)
    use_cost_index(CostIndex.from_db(con))
    rows, X, y, train_mask, test, cats = F.prepare(con)
    contracts, base, sel, _ = F.contract_lines(con, rows, cats)
    con.close()
    ref = {m: load_refresh(m) for m in MODELS}

    # --- validation (2023 bids, everything before 2023) and the choice
    d = rows["bid_open_date"]
    val = rows[train_mask & (d >= pd.Timestamp("2023-01-01"))].copy()
    val["trailing_median"] = trailing_median(val, item_history(rows))["pred"].to_numpy()
    for m in MODELS:
        v = ref[m][ref[m]["kind"] == "validation"].set_index("key")["pred_unit_price"]
        val[m] = val["bid_item_id"].map(v).to_numpy()
    val["item_family"] = val["item_family"].fillna("Other")
    default, overrides, choice_table = choose(val)

    # --- test: frozen (stages 10, 11) and refreshed
    frozen = pd.read_csv(
        ROOT / "outputs" / "10_baselines" / "predictions.csv", dtype={"bid_item_id": str}
    ).merge(
        pd.read_csv(
            ROOT / "outputs" / "11_kumo_tabular" / "predictions.csv", dtype={"bid_item_id": str}
        )[["bid_item_id", "kumo"]],
        on="bid_item_id",
    )
    t = test.copy()
    t["family"] = report_family(t["item_family"])
    t["fam_raw"] = t["item_family"].fillna("Other")
    t["trailing_median"] = t["bid_item_id"].map(frozen.set_index("bid_item_id")["trailing_median"])
    for m in MODELS:
        t[f"{m}_frozen"] = t["bid_item_id"].map(frozen.set_index("bid_item_id")[m])
        r = ref[m][ref[m]["kind"] == "test"].set_index("key")["pred_unit_price"]
        t[m] = t["bid_item_id"].map(r)
    method_of = t["fam_raw"].map(lambda f: overrides.get(f, default))
    t["production"] = [t.at[i, m] for i, m in zip(t.index, method_of, strict=True)]

    def _score(df, col):
        e = ape(df[col], df["unit_price"])
        lr = np.log(df[col] / df["unit_price"])
        return {
            "prices": len(df),
            "mdape": float(np.median(e)),
            "within_15": float((e <= WITHIN).mean()),
            "median_signed": float(np.expm1(np.median(lr))),
        }

    cols = ["trailing_median", *[f"{m}_frozen" for m in MODELS], *MODELS, "production"]
    overall = {c: _score(t, c) for c in cols}
    clean = {c: _score(t[~t["is_outlier"]], c)["mdape"] for c in cols}
    by_family = []
    for fam, g in t.groupby("family"):
        by_family.append(
            {
                "family": fam,
                "prices": len(g),
                **{c: _score(g, c)["mdape"] for c in [*METHODS, "production"]},
            }
        )
    by_family = pd.DataFrame(by_family).sort_values("prices", ascending=False)
    by_year = []
    for yr, g in t.groupby(t["bid_open_date"].dt.year):
        by_year.append(
            {
                "year": int(yr),
                **{c: _score(g, c)["mdape"] for c in [*METHODS, "production"]},
                **{f"{c}_signed": _score(g, c)["median_signed"] for c in [*METHODS, "production"]},
            }
        )
    by_year = pd.DataFrame(by_year)

    # --- contract level, refreshed
    lines = {}
    for m in MODELS:
        r = ref[m][ref[m]["kind"] == "line"].set_index("key")["pred_unit_price"]
        key = (
            sel["contract_number"]
            + "|"
            + sel["bid_open_date"].dt.strftime("%Y-%m-%d")
            + "|"
            + sel["item_no"].astype(str)
        )
        lines[m] = key.map(r)
        if lines[m].isna().any():
            raise RuntimeError(f"refresh_{m} misses contract lines; rerun refresh --model {m}")
    lines["production"] = pd.Series(
        [
            lines[m].at[i]
            for i, m in zip(
                sel.index,
                sel["item_family"].fillna("Other").map(lambda f: overrides.get(f, default)),
                strict=True,
            )
        ],
        index=sel.index,
    )
    totals = {"trailing_median": contract_totals(base, contracts)}
    head_set = totals["trailing_median"]["in_headline"].to_numpy()
    for m, p in lines.items():
        priced = base.copy()
        priced.loc[sel.index, "pred_unit_price"] = p.to_numpy()
        priced.loc[sel.index, "tier"] = 1
        priced["pred_amount"] = priced["pred_unit_price"] * priced["quantity"]
        tt = contract_totals(priced, contracts)
        tt["in_headline"] = head_set
        totals[m] = tt
    contract = {m: headline(tt) for m, tt in totals.items()}

    speed = {
        m: json.loads(Path(str(REFRESH).format(model=m)).with_suffix(".json").read_text())
        for m in MODELS
    }

    write(
        OUT,
        default,
        overrides,
        choice_table,
        overall,
        clean,
        by_family,
        by_year,
        contract,
        speed,
        totals,
        t,
    )
    PRODUCTION.parent.mkdir(parents=True, exist_ok=True)
    PRODUCTION.write_text(
        json.dumps(
            {
                "default": default,
                "family_overrides": overrides,
                "refresh": "quarterly, every cleaned bid before the quarter",
                "kumo": {
                    "package": "structured-data-models==0.2.1",
                    "size": "small",
                    "weights": "nvidia/Kumo-Tabular@v1.0.1",
                },
                "gbm_settings": "outputs/10_baselines/results.json",
                "chosen_on": "2023 validation bids",
                "generated": date.today().isoformat(),
            },
            indent=2,
        )
        + "\n"
    )

    from bidlens.outputs import write_index

    write_index()
    print(
        json.dumps(
            {
                "default": default,
                "overrides": overrides,
                "test_mdape": {k: round(v["mdape"], 4) for k, v in overall.items()},
                "contract_closer": {
                    k: round(v["headline"]["bidlens_closer_share"], 3) for k, v in contract.items()
                },
            },
            indent=2,
        )
    )
    return 0


def _pct(x: float) -> str:
    return "" if pd.isna(x) else f"{100 * x:.1f}%"


def write(
    out,
    default,
    overrides,
    choice_table,
    overall,
    clean,
    by_family,
    by_year,
    contract,
    speed,
    totals,
    t,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    choice_table.to_csv(out / "validation_choice.csv", index=False, float_format="%.4f")
    by_family.to_csv(out / "test_by_family.csv", index=False, float_format="%.4f")
    by_year.to_csv(out / "test_by_year.csv", index=False, float_format="%.4f")
    t[
        [
            "bid_item_id",
            "contract_number",
            "bid_open_date",
            "item_code",
            "unit",
            "family",
            "unit_price",
            "trailing_median",
            *MODELS,
            "production",
        ]
    ].rename(columns={"unit_price": "low_bid_unit_price"}).to_csv(
        out / "test_predictions_refreshed.csv",
        index=False,
        float_format="%.4f",
        date_format="%Y-%m-%d",
    )
    wide = totals["trailing_median"][
        [
            "contract_number",
            "bid_open_date",
            "low_bid_cost",
            "engineers_estimate",
            "in_headline",
            "ee_error",
        ]
    ].copy()
    for m, tt in totals.items():
        wide[f"{m}_total"] = tt["bidlens_total"].to_numpy()
        wide[f"{m}_error"] = tt["bidlens_error"].to_numpy()
    wide.to_csv(
        out / "contract_totals_refreshed.csv",
        index=False,
        float_format="%.4f",
        date_format="%Y-%m-%d",
    )

    vo = choice_table.iloc[0]
    vlines = ["| Method | Validation median miss (2023 bids) |", "| --- | ---: |"]
    for m in METHODS:
        vlines.append(f"| {LABELS[m]} | {_pct(vo['overall_' + m])} |")
    over_txt = (
        "; ".join(f"{f}: {LABELS[m]}" for f, m in overrides.items())
        if overrides
        else "none (no family cleared the bar)"
    )

    olines = [
        "| Method | How it runs | Median miss | Within 15% | Median over (+) / under (-) "
        "| Without outliers |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    rowspec = [
        ("trailing_median", "Latest bids, always"),
        *[(f"{m}_frozen", "Frozen at the end of 2023") for m in MODELS],
        *[(m, "Refreshed each quarter") for m in MODELS],
        ("production", "Refreshed each quarter"),
    ]
    for c, how in rowspec:
        name = LABELS[c.replace("_frozen", "")]
        o = overall[c]
        olines.append(
            f"| {name} | {how} | {_pct(o['mdape'])} | {_pct(o['within_15'])} | "
            f"{100 * o['median_signed']:+.1f}% | {_pct(clean[c])} |"
        )

    cols = [*METHODS, "production"]
    flines = [
        "| Item family | Prices | " + " | ".join(LABELS[c] for c in cols) + " | Best |",
        "| --- | ---: |" + " ---: |" * len(cols) + " --- |",
    ]
    losses = {m: [] for m in cols}
    for r in by_family.itertuples(index=False):
        vals = {c: getattr(r, c) for c in cols}
        best = min(METHODS, key=lambda c: vals[c])
        for c in METHODS:
            if c != best:
                losses[c].append(r.family)
        flines.append(
            f"| {r.family} | {r.prices:,} | "
            + " | ".join(_pct(vals[c]) for c in cols)
            + f" | {LABELS[best]} |"
        )
    ylines = [
        "| Bid year | " + " | ".join(LABELS[c] for c in cols) + " |",
        "| --- |" + " ---: |" * len(cols),
    ]
    for r in by_year.itertuples(index=False):
        ylines.append(
            f"| {r.year} | "
            + " | ".join(
                f"{_pct(getattr(r, c))} ({100 * getattr(r, c + '_signed'):+.0f}%)" for c in cols
            )
            + " |"
        )

    h = {m: contract[m]["headline"] for m in contract}
    ee = h["production"]
    clines = [
        "| Total built with | Closer than the EE | Typical miss "
        "| Median over (+) / under (-) | Within 15% |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for m in ["trailing_median", *MODELS, "production"]:
        r = h[m]
        clines.append(
            f"| {LABELS[m]} | {_pct(r['bidlens_closer_share'])} | "
            f"{_pct(r['bidlens_median_abs_error'])} | {100 * r['bidlens_median_error']:+.1f}% | "
            f"{_pct(r['bidlens_within_15'])} |"
        )
    clines.append(
        f"| Engineer's estimate | | {_pct(ee['ee_median_abs_error'])} | "
        f"{100 * ee['ee_median_error']:+.1f}% | {_pct(ee['ee_within_15'])} |"
    )
    a = contract["production"]["all_test_contracts"]

    slines = [
        "| Method | Time per quarter's refresh and pricing | Training | Licence |",
        "| --- | ---: | --- | --- |",
        f"| {LABELS['trailing_median']} | under 1 s | none | {LICENCES['trailing_median']} |",
    ]
    for m in MODELS:
        how = "none: reads a table of known prices" if m == "kumo" else "refit, three seeds"
        slines.append(
            f"| {LABELS[m]} | {speed[m]['seconds_per_quarter']:.1f} s | {how} | {LICENCES[m]} |"
        )

    loss_lines = []
    for m in METHODS:
        if losses[m]:
            loss_lines.append(
                f"- **{LABELS[m]}** is beaten in {len(losses[m])} of "
                f"{len(by_family)} families: {', '.join(losses[m])}."
            )

    body = f"""
Which pricing method BidLens uses, and how it compares with Caltrans' engineer's estimate
(step 2.5).

## The question

Four ways of pricing a bid item have been built: the historical median of recent low bids
(stage 08), XGBoost and LightGBM (stage 10), and NVIDIA Kumo Tabular (stage 11). Which one
should BidLens use, and is a BidLens total closer to the winning bid than the engineer's
estimate?

## Two ways of running the models

Stages 10 and 11 froze the models at the end of 2023 and tested them on almost three
years of later bids. The sanity check (stage 12) showed they drift high as time passes.
In real use BidLens always has the latest bids, so each model is also run **refreshed
each quarter**: before pricing a quarter's bids it sees every bid opened before that
quarter. It still never sees the bids it is pricing.

## The choice

The choice was made on 2023 bids (everything before 2023 as history), not on the test
years, so the test results below are an honest check of it:

{chr(10).join(vlines)}

**Default: {LABELS[default]}.** Family exceptions (a method must beat the default by 5
points on at least 50 validation prices): {over_txt}.

## Results on the test years (2024 to 2026)

### Single items

{chr(10).join(olines)}

By item family (refreshed; median miss):

{chr(10).join(flines)}

Where each method loses (another method has a lower median miss on the test years):

{chr(10).join(loss_lines)}

By bid year (median miss, and median over or under in brackets):

{chr(10).join(ylines)}

### Whole contracts: the headline

Every line of each test contract's bid list is priced (top-100 items by the method; other
lines by earlier prices for the same item, as in stage 08), and added up.

{chr(10).join(clines)}

On the {h["production"]["contracts"]} headline contracts (at least 90% of lines have price
history), **the BidLens total landed closer to the low bid than Caltrans' engineer's
estimate on {_pct(h["production"]["bidlens_closer_share"])} of contracts.** Over all
{a["contracts"]} test contracts: {_pct(a["bidlens_closer_share"])}.

The engineer's estimate sits above the low bid on most contracts (median
{100 * ee["ee_median_error"]:+.1f}%): the low bid is the most aggressive of several bids,
and in 2024 to 2026 low bids in Districts 4 and 5 came in well under Caltrans' estimates.
The BidLens total is centred much closer to the low bid (median
{100 * h["production"]["bidlens_median_error"]:+.1f}%), because it is built from earlier
low bids rather than from an engineer's cost build-up.

## Speed and licence

{chr(10).join(slines)}

## What is saved

`data/models/production.json` records the choice (default method, family exceptions,
refresh rule and model versions). The app (step 4.1) prices with it. Not committed; rebuild
with the commands below.

## Files

- `validation_choice.csv`: 2023 validation median miss per family and method, and the choice.
- `test_by_family.csv`, `test_by_year.csv`: the tables above.
- `test_predictions_refreshed.csv`: every test price with each method's refreshed prediction.
- `contract_totals_refreshed.csv`: every test contract's totals by method, with errors.

## How it was produced

`uv run python -m bidlens.pricing.refresh --model xgboost` (then `lightgbm`, then `kumo`;
one process each), then `uv run python -m bidlens.pricing.select`. Code in
`src/bidlens/pricing/`. Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text(
        "# 13 Model comparison and selection\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    (out / "results.json").write_text(
        json.dumps(
            {
                "default": default,
                "overrides": overrides,
                "test": overall,
                "test_without_outliers": clean,
                "contract_level": contract,
                "speed": speed,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
