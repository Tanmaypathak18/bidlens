"""Step 2.3: XGBoost and LightGBM baselines (decision D-041).

Usage:
    uv run python -m bidlens.pricing.baseline    # writes outputs/10_baselines, data/models/

Both models predict the log of the low-bid unit price in 2023 Q4 dollars; predictions are
escalated back to each bid's date. Tuning uses a time-ordered inner split of the training
years (fit before 2023, choose on 2023), never the test years.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb

from bidlens.pricing import features as F
from bidlens.pricing.escalate import CostIndex
from bidlens.pricing.setup import (
    CUTOFF,
    WITHIN,
    ape,
    report_family,
    score,
    use_cost_index,
)

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
OUT = ROOT / "outputs" / "10_baselines"
MODELS = ROOT / "data" / "models"
INNER_CUTOFF = pd.Timestamp("2023-01-01")
TRIALS = 30
SEED = 2026
MAX_TREES = 3000
EARLY_STOP = 100
N_SEEDS = 3  # D-042


# ------------------------------------------------------------------ models


def _sample_params(kind: str, rng: np.random.Generator) -> dict:
    lr = float(np.exp(rng.uniform(np.log(0.02), np.log(0.2))))
    sub = float(rng.uniform(0.6, 1.0))
    col = float(rng.uniform(0.5, 1.0))
    lam = float(np.exp(rng.uniform(np.log(0.1), np.log(10))))
    if kind == "xgboost":
        return {
            "max_depth": int(rng.integers(3, 11)),
            "learning_rate": lr,
            "min_child_weight": float(rng.uniform(1, 20)),
            "subsample": sub,
            "colsample_bytree": col,
            "reg_lambda": lam,
        }
    return {
        "num_leaves": int(rng.integers(15, 128)),
        "learning_rate": lr,
        "min_child_samples": int(rng.integers(5, 51)),
        "subsample": sub,
        "subsample_freq": 1,
        "colsample_bytree": col,
        "reg_lambda": lam,
    }


def make_model(kind: str, params: dict, n_trees: int, seed: int, early_stop: bool):
    if kind == "xgboost":
        return xgb.XGBRegressor(
            n_estimators=n_trees,
            tree_method="hist",
            enable_categorical=True,
            max_cat_to_onehot=1,
            early_stopping_rounds=EARLY_STOP if early_stop else None,
            random_state=seed,
            n_jobs=-1,
            **params,
        )
    return lgb.LGBMRegressor(n_estimators=n_trees, random_state=seed, verbose=-1, **params)


def fit(kind, model, X, y, Xv=None, yv=None):
    if Xv is None:
        model.fit(X, y)
    elif kind == "xgboost":
        model.fit(X, y, eval_set=[(Xv, yv)], verbose=False)
    else:
        model.fit(
            X,
            y,
            eval_X=Xv,
            eval_y=yv,
            callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)],
        )
    return model


def best_trees(kind: str, model) -> int:
    return int(model.best_iteration + 1) if kind == "xgboost" else int(model.best_iteration_)


def tune(kind, X, y, Xv, yv, trials=TRIALS, seed=SEED) -> tuple[dict, int, pd.DataFrame]:
    """Random search on the inner split; returns the best params, tree count and the log."""
    rng = np.random.default_rng(seed)
    log = []
    for t in range(trials):
        params = _sample_params(kind, rng)
        m = fit(kind, make_model(kind, params, MAX_TREES, seed, True), X, y, Xv, yv)
        n = best_trees(kind, m)
        pred = np.exp(m.predict(Xv))
        e = ape(pred, np.exp(yv))
        log.append(
            {
                "trial": t,
                **params,
                "trees": n,
                "val_mdape": float(np.median(e)),
                "val_within_15": float((e <= WITHIN).mean()),
            }
        )
    log = pd.DataFrame(log).sort_values("val_mdape", kind="stable")
    best = log.iloc[0]
    params = {k: best[k] for k in _sample_params(kind, np.random.default_rng(0))}
    params = {
        k: (int(v) if float(v).is_integer() and k not in ("learning_rate",) else float(v))
        for k, v in params.items()
    }
    return params, int(best["trees"]), log


# ------------------------------------------------------------------ pipeline


def _mdape(log_pred, log_actual) -> float:
    return float(np.median(ape(np.exp(log_pred), np.exp(log_actual))))


prepare = F.prepare


def run(con) -> dict:
    rows, X, y, train_mask, test, cats = prepare(con)
    _, _, sel, X_lines = F.contract_lines(con, rows, cats)
    d = rows["bid_open_date"]
    inner_fit = train_mask & (d < INNER_CUTOFF)
    inner_val = train_mask & (d >= INNER_CUTOFF)
    pred = test.copy()
    pred["family"] = report_family(pred["item_family"])
    pred["year"] = pred["bid_open_date"].dt.year
    pred["trailing_median"] = np.exp(X.loc[test.index, "log_trailing_median"]).pipe(
        lambda s: F.from_ref(s, test["bid_open_date"])
    )
    tuning, info, importance = {}, {}, []
    MODELS.mkdir(parents=True, exist_ok=True)
    for kind in ("xgboost", "lightgbm"):
        t0 = time.perf_counter()
        params, trees, log = tune(kind, X[inner_fit], y[inner_fit], X[inner_val], y[inner_val])
        tune_s = time.perf_counter() - t0
        # Seed check (D-041) and the three-seed average (D-042), on the inner split.
        seed_mdape, seed_logs = [], []
        for s in range(SEED, SEED + 6):
            m = fit(kind, make_model(kind, params, trees, s, False), X[inner_fit], y[inner_fit])
            lp = m.predict(X[inner_val])
            seed_logs.append(lp)
            seed_mdape.append(_mdape(lp, y[inner_val]))
        avg_mdape = [
            _mdape(np.mean(seed_logs[k : k + N_SEEDS], axis=0), y[inner_val]) for k in (0, N_SEEDS)
        ]
        t0 = time.perf_counter()
        models = [
            fit(kind, make_model(kind, params, trees, s, False), X[train_mask], y[train_mask])
            for s in range(SEED, SEED + N_SEEDS)
        ]
        fit_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        p_ref = np.exp(np.mean([m.predict(X.loc[test.index]) for m in models], axis=0))
        infer_s = time.perf_counter() - t0
        pred[kind] = F.from_ref(p_ref, test["bid_open_date"])
        F.save_line_predictions(kind, sel, np.mean([m.predict(X_lines) for m in models], axis=0))
        imp: dict[str, float] = {}
        for i, model in enumerate(models):
            if kind == "xgboost":
                model.save_model(MODELS / f"xgboost_baseline_{i}.json")
                gains = model.get_booster().get_score(importance_type="total_gain")
            else:
                model.booster_.save_model(str(MODELS / f"lightgbm_baseline_{i}.txt"))
                gains = dict(
                    zip(
                        model.booster_.feature_name(),
                        model.booster_.feature_importance("gain"),
                        strict=True,
                    )
                )
            total = sum(gains.values())
            for k, v in gains.items():
                imp[k] = imp.get(k, 0.0) + v / total / N_SEEDS
        importance += [{"model": kind, "feature": k, "share_of_gain": v} for k, v in imp.items()]
        tuning[kind] = log
        info[kind] = {
            "params": params,
            "trees": trees,
            "val_mdape": float(log["val_mdape"].iloc[0]),
            "val_mdape_single_seeds": seed_mdape,
            "val_mdape_averaged": avg_mdape,
            "tune_seconds": round(tune_s, 1),
            "fit_seconds": round(fit_s, 2),
            "predict_seconds": round(infer_s, 4),
            "train_rows": int(train_mask.sum()),
            "test_rows": int(len(test)),
        }
    return {
        "pred": pred,
        "tuning": tuning,
        "info": info,
        "importance": pd.DataFrame(importance).sort_values(
            ["model", "share_of_gain"], ascending=[True, False]
        ),
    }


def load_saved(kind: str) -> list:
    """The three fitted models of a library (D-042), as saved by `run`."""
    if kind == "xgboost":
        models = []
        for i in range(N_SEEDS):
            m = xgb.XGBRegressor()
            m.load_model(MODELS / f"xgboost_baseline_{i}.json")
            models.append(m)
        return models
    return [
        lgb.Booster(model_file=str(MODELS / f"lightgbm_baseline_{i}.txt")) for i in range(N_SEEDS)
    ]


def predict_saved(models: list, X: pd.DataFrame) -> np.ndarray:
    """Average log price over the fitted models (2023 Q4 dollars)."""
    return np.mean([m.predict(X) for m in models], axis=0)


MODEL_LABELS = {
    "trailing_median": "Trailing 12-month median (2.1 benchmark)",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
}


def score_table(pred: pd.DataFrame) -> pd.DataFrame:
    tables = []
    for label, df in (("all prices", pred), ("without outliers", pred[~pred["is_outlier"]])):
        for by in ("family", "year"):
            for col in MODEL_LABELS:
                t = score(df, by, pred=col)
                t.insert(0, "model", col)
                t.insert(0, "by", by)
                t.insert(0, "test_set", label)
                tables.append(t)
    return pd.concat(tables, ignore_index=True)


def _pct(x):
    return f"{100 * x:.1f}%"


def write_outputs(out: Path, res: dict) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    pred, info = res["pred"], res["info"]
    scores = score_table(pred)
    scores.to_csv(out / "scores.csv", index=False, float_format="%.4f")
    pred[
        [
            "bid_item_id",
            "contract_number",
            "bid_open_date",
            "district",
            "item_code",
            "unit",
            "family",
            "quantity",
            "unit_price",
            "trailing_median",
            "xgboost",
            "lightgbm",
            "is_outlier",
        ]
    ].rename(columns={"unit_price": "low_bid_unit_price"}).to_csv(
        out / "predictions.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d"
    )
    for kind, log in res["tuning"].items():
        log.to_csv(out / f"tuning_{kind}.csv", index=False, float_format="%.5f")
    res["importance"].to_csv(out / "feature_importance.csv", index=False, float_format="%.4f")

    fam = scores[(scores["test_set"] == "all prices") & (scores["by"] == "family")]
    wide = fam.pivot_table(
        index="group", columns="model", values=["mdape", "within_15"], sort=False
    )
    n = fam[fam["model"] == "xgboost"].set_index("group")["n"]
    order = list(n.index)
    lines = [
        "| Item family | Prices | Median MdAPE | XGBoost MdAPE | LightGBM MdAPE | "
        "Median within 15% | XGBoost within 15% | LightGBM within 15% | Best |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    losses = []
    for g in order:
        md = {m: wide.loc[g, ("mdape", m)] for m in MODEL_LABELS}
        wi = {m: wide.loc[g, ("within_15", m)] for m in MODEL_LABELS}
        best = min(md, key=md.get)
        if best == "trailing_median" and g != "All":
            losses.append(g)
        lines.append(
            f"| {g} | {int(n[g]):,} | {_pct(md['trailing_median'])} | {_pct(md['xgboost'])} | "
            f"{_pct(md['lightgbm'])} | {_pct(wi['trailing_median'])} | {_pct(wi['xgboost'])} | "
            f"{_pct(wi['lightgbm'])} | {MODEL_LABELS[best].split(' (')[0]} |"
        )
    year = scores[(scores["test_set"] == "all prices") & (scores["by"] == "year")]
    ywide = year.pivot_table(index="group", columns="model", values="mdape", sort=False)
    ylines = ["| Bid year | Median | XGBoost | LightGBM |", "| --- | ---: | ---: | ---: |"]
    for g, r in ywide.iterrows():
        ylines.append(
            f"| {g} | {_pct(r['trailing_median'])} | {_pct(r['xgboost'])} | {_pct(r['lightgbm'])} |"
        )
    clean = scores[
        (scores["test_set"] == "without outliers")
        & (scores["by"] == "family")
        & (scores["group"] == "All")
    ].set_index("model")
    allp = fam[fam["group"] == "All"].set_index("model")
    imp = res["importance"]
    top = {k: imp[imp["model"] == k].head(5) for k in ("xgboost", "lightgbm")}
    ee_share = {
        k: float(
            imp[(imp["model"] == k) & (imp["feature"] == "log_engineers_estimate")][
                "share_of_gain"
            ].sum()
        )
        for k in top
    }
    tune_lines = ["| | XGBoost | LightGBM |", "| --- | ---: | ---: |"]
    xi, li = info["xgboost"], info["lightgbm"]
    tune_lines += [
        f"| Validation MdAPE (2023 bids) | {_pct(xi['val_mdape'])} | {_pct(li['val_mdape'])} |",
        f"| Same setting, six single seeds | "
        f"{_pct(min(xi['val_mdape_single_seeds']))} to {_pct(max(xi['val_mdape_single_seeds']))} | "
        f"{_pct(min(li['val_mdape_single_seeds']))} to {_pct(max(li['val_mdape_single_seeds']))} |",
        f"| Three-seed average, two seed sets (used, D-042) | "
        f"{', '.join(_pct(v) for v in xi['val_mdape_averaged'])} | "
        f"{', '.join(_pct(v) for v in li['val_mdape_averaged'])} |",
        f"| Trees | {xi['trees']:,} | {li['trees']:,} |",
        f"| Tuning time (30 trials) | {xi['tune_seconds']:.0f} s | {li['tune_seconds']:.0f} s |",
        f"| Final fit time (three fits) | {xi['fit_seconds']:.1f} s | {li['fit_seconds']:.1f} s |",
        f"| Time to price all {xi['test_rows']:,} test items | "
        f"{1000 * xi['predict_seconds']:.0f} ms | {1000 * li['predict_seconds']:.0f} ms |",
    ]

    def _imp(k):
        return "; ".join(f"{r.feature} {_pct(r.share_of_gain)}" for r in top[k].itertuples())

    body = f"""
Two machine-learning models that price bid items, scored on the step 2.1 test (step 2.3).

## What we did

Both models (XGBoost and LightGBM, two widely used decision-tree methods) learn the low
bidder's unit price from bids opened before {CUTOFF:%d %B %Y}, then price every test item
from {CUTOFF:%B %Y} on. They see only what an estimator knows before bids open (decision
D-041): the item and its family, the quantity (and how it compares with the item's usual
quantity), district and county, the time of year and the date, the contract's size
(engineer's estimate, working days, number of items), the type of work from the contract
description, and the item's recent median price. Prices are in constant dollars (stage
09) while learning, and converted back to each bid's date.

Settings were chosen on the training years only: fit on bids before 2023 and pick the
best of 30 random settings on 2023 bids. Each final model averages three fits with
different random seeds (decision D-042), because a single fit's score moved by about two
points from seed to seed.

## Results

All test prices: XGBoost misses the low-bid unit price by a median of
**{_pct(allp.loc["xgboost", "mdape"])}**, LightGBM by **{_pct(allp.loc["lightgbm", "mdape"])}**,
against {_pct(allp.loc["trailing_median", "mdape"])} for the trailing median. Within 15% of
the low bid: {_pct(allp.loc["xgboost", "within_15"])}, {_pct(allp.loc["lightgbm", "within_15"])}
and {_pct(allp.loc["trailing_median", "within_15"])}. Without flagged outliers:
{_pct(clean.loc["xgboost", "mdape"])}, {_pct(clean.loc["lightgbm", "mdape"])} and
{_pct(clean.loc["trailing_median", "mdape"])}.

By item family (all test prices; "Best" is the lowest MdAPE):

{chr(10).join(lines)}

Families where the trailing median beats both models: {", ".join(losses) if losses else "none"}.

By bid year (MdAPE):

{chr(10).join(ylines)}

## What the models rely on

Share of each model's learning gain, top five: XGBoost: {_imp("xgboost")}. LightGBM:
{_imp("lightgbm")}. The engineer's estimate carries {_pct(ee_share["xgboost"])} (XGBoost) and
{_pct(ee_share["lightgbm"])} (LightGBM) of the gain.

## Tuning and speed

{chr(10).join(tune_lines)}

## Files

- `scores.csv`: MdAPE, within-15% and coverage for each model, by family and by year, with
  and without outliers.
- `predictions.csv`: every test price with the three predictions.
- `tuning_xgboost.csv`, `tuning_lightgbm.csv`: all 30 settings tried and their 2023 scores.
- `feature_importance.csv`: each feature's share of each model's gain.

The fitted models (three per library) are saved in `data/models/` (not committed; rebuild
with the command below).

## How it was produced

`uv run python -m bidlens.pricing.baseline` (code in `src/bidlens/pricing/baseline.py` and
`features.py`). Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text(
        "# 10 Baselines: XGBoost and LightGBM\n\n" + body.strip() + "\n", encoding="utf-8"
    )
    summary = {
        "all_prices": {
            m: {"mdape": float(allp.loc[m, "mdape"]), "within_15": float(allp.loc[m, "within_15"])}
            for m in MODEL_LABELS
        },
        "without_outliers": {m: float(clean.loc[m, "mdape"]) for m in MODEL_LABELS},
        "families_where_median_wins": losses,
        "engineers_estimate_gain_share": ee_share,
        "models": info,
    }
    (out / "results.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
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
    print(json.dumps({k: v for k, v in summary.items() if k != "models"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
