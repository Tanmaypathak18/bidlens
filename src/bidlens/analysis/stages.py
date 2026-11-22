"""Tables and charts for notebooks 02 to 07, read from the committed stage outputs.

Nothing here reruns a model: every function reads a stage's CSV or JSON files in `outputs/`
and returns a small pandas table or a matplotlib figure. No bidder identities: rank only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from bidlens.analysis.overview import BLUE, GRID, INK, INK_2, ORANGE, SURFACE, _style
from bidlens.analysis.overview import save as _save

OUTPUTS = Path("outputs")
S08, S09, S10, S11, S12, S13, S14, S15 = (
    OUTPUTS / n
    for n in (
        "08_target_split_metrics",
        "09_price_escalation",
        "10_baselines",
        "11_kumo_tabular",
        "12_sanity_check",
        "13_model_comparison",
        "14_price_ranges",
        "15_market_context",
    )
)
S17, S19, S20, S21 = (
    OUTPUTS / n
    for n in (
        "17_document_parsing",
        "19_extraction_evaluation",
        "20_extraction_round2",
        "21_app",
    )
)
SAMPLE = Path("data/sample/app/04-0W0504")

# Fixed method colours across every notebook: the chosen model always blue.
AQUA, GREY, PURPLE = "#1baf7a", "#9a9893", "#7c5cc4"
METHODS = {
    "trailing_median": ("Historical median", GREY),
    "xgboost": ("XGBoost", ORANGE),
    "lightgbm": ("LightGBM", AQUA),
    "kumo": ("Kumo Tabular", BLUE),
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def pct(x: float, signed: bool = False) -> str:
    return f"{100 * x:+.1f}%" if signed else f"{100 * x:.1f}%"


def _hgrid(ax) -> None:
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)


def _legend(ax, **kw) -> None:
    ax.legend(frameon=False, **kw)


def _legend_top(ax, ncols: int) -> None:
    """Legend in a row between the title and the plot, clear of the bars."""
    ax.legend(
        frameon=False,
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        ncols=ncols,
        borderaxespad=0.3,
        fontsize=9,
    )
    ax.set_title(ax.get_title(loc="left"), loc="left", fontsize=12, color=INK, pad=28)


def save(fig: Figure, name: str, out: Path) -> Path:
    """Charts go into the stage folder the notebook explains, prefixed `nb_`."""
    return _save(fig, f"nb_{name}", out)


def note_in_readme(out: Path, notebook: str) -> Path:
    """Add (or refresh) a short section listing the notebook's charts in the stage README."""
    readme = out / "README.md"
    files = sorted(p.name for p in out.glob("nb_*.png"))
    head = "## Charts from the notebook"
    section = (
        f"{head}\n\n`notebooks/{notebook}` explains this stage and saved these charts here: "
        + ", ".join(f"`{f}`" for f in files)
        + ".\n"
    )
    text = readme.read_text(encoding="utf-8")
    text = re.sub(rf"\n{head}\n.*?(?=\n## |\Z)", "", text, flags=re.S).rstrip() + "\n"
    readme.write_text(f"{text}\n{section}", encoding="utf-8")
    return readme


# --------------------------------------------------------------------------- 02 escalation


def cost_index() -> pd.DataFrame:
    d = pd.read_csv(S09 / "cost_index.csv")
    d["t"] = d["year"] + (d["quarter"] - 1) / 4
    return d


def price_levels() -> pd.DataFrame:
    return pd.read_csv(S09 / "price_level_check.csv").rename(
        columns={
            "year": "Bid year",
            "items": "Items",
            "unescalated": "Prices as bid",
            "escalated": "After escalation",
        }
    )


def chart_cost_index(d: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=110)
    pub = d[d["published"]]
    ax.plot(
        pub["t"],
        pub["quarterly_index"],
        color=GREY,
        linewidth=1,
        marker="o",
        markersize=3,
        label="Published quarterly index",
    )
    known = d[d["published"] | (d["t"] <= pub["t"].max() + 0.25)]
    ax.plot(
        known["t"],
        known["value_4q_mean"],
        color=BLUE,
        linewidth=2.2,
        label="Value used: mean of the 4 earlier quarters",
    )
    later = d[d["t"] >= pub["t"].max() + 0.25]
    ax.plot(
        later["t"],
        later["value_4q_mean"],
        color=BLUE,
        linewidth=2.2,
        linestyle=":",
        label="Not yet published: last value carried forward",
    )
    _style(ax, "Caltrans highway construction cost index (2020 = 100)", ylabel="Index")
    _legend(ax, loc="upper left")
    fig.tight_layout()
    return fig


def chart_price_levels(d: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
    x = d["Bid year"]
    ax.axhline(1, color=INK_2, linewidth=1, linestyle="--")
    ax.plot(x, d["Prices as bid"], color=ORANGE, marker="o", linewidth=2, label="Prices as bid")
    ax.plot(
        x,
        d["After escalation"],
        color=BLUE,
        marker="o",
        linewidth=2,
        label="After escalation to one date",
    )
    for col, color in (("Prices as bid", ORANGE), ("After escalation", BLUE)):
        y = d[col].iloc[-1]
        ax.annotate(
            f"{y:.2f}",
            (x.iloc[-1], y),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=color,
        )
    _style(
        ax,
        "Typical item price level, relative to the same item in 2020",
        ylabel="Ratio to 2020 (1.00 = same)",
    )
    _legend(ax, loc="upper left")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 03 baselines


def split_summary() -> pd.DataFrame:
    d = pd.read_csv(S08 / "split_summary.csv")
    d.columns = ["Set", "Prices", "Contracts"]
    return d.astype({"Prices": "Int64"}, errors="ignore")


def baseline_scores() -> pd.DataFrame:
    return pd.read_csv(S10 / "scores.csv")


def baseline_overall() -> pd.DataFrame:
    r = _json(S10 / "results.json")
    rows = []
    for key in ("trailing_median", "xgboost", "lightgbm"):
        a = r["all_prices"][key]
        rows.append(
            {
                "Method": METHODS[key][0],
                "Median miss": pct(a["mdape"]),
                "Within 15% of the low bid": pct(a["within_15"]),
                "Median miss without flagged outliers": pct(r["without_outliers"][key]),
            }
        )
    return pd.DataFrame(rows)


def tuning_summary() -> pd.DataFrame:
    m = _json(S10 / "results.json")["models"]
    return pd.DataFrame(
        {
            "": [
                "Median miss on 2023 bids (one fit)",
                "Range over six single seeds",
                "Three-seed average (used)",
                "Trees",
                "Fit time (three fits)",
                "Time to price 4,507 test items",
            ],
            **{
                name: [
                    pct(v["val_mdape"]),
                    " to ".join(pct(f(v["val_mdape_single_seeds"])) for f in (min, max)),
                    pct(v["val_mdape_averaged"][0]),
                    v["trees"],
                    f"{v['fit_seconds']:.1f} s",
                    f"{1000 * v['predict_seconds']:.0f} ms",
                ]
                for name, v in (("XGBoost", m["xgboost"]), ("LightGBM", m["lightgbm"]))
            },
        }
    )


def feature_importance() -> pd.DataFrame:
    return pd.read_csv(S10 / "feature_importance.csv")


FEATURE_NAMES = {
    "item_code": "Item code",
    "log_trailing_median": "Item's recent median price",
    "log_quantity": "Quantity",
    "log_engineers_estimate": "Contract size (engineer's estimate)",
    "unit": "Pay unit",
    "item_family": "Item family",
    "log_quantity_vs_history": "Quantity vs the item's usual",
    "n_history": "Number of recent prices",
    "n_items": "Number of bid items",
    "log_working_days": "Working days",
    "months_since_2018": "Bid date",
    "county": "County",
}


def chart_feature_importance(d: pd.DataFrame, top: int = 6) -> Figure:
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), dpi=110, sharex=True)
    for ax, (model, label) in zip(
        axes, (("xgboost", "XGBoost"), ("lightgbm", "LightGBM")), strict=True
    ):
        s = d[d["model"] == model].nlargest(top, "share_of_gain").iloc[::-1]
        names = [FEATURE_NAMES.get(f, f) for f in s["feature"]]
        bars = ax.barh(names, 100 * s["share_of_gain"], 0.65, color=METHODS[model][1])
        for b in bars:
            ax.annotate(
                f"{b.get_width():.0f}%",
                (b.get_width(), b.get_y() + b.get_height() / 2),
                xytext=(3, 0),
                textcoords="offset points",
                va="center",
                fontsize=8,
                color=INK_2,
            )
        _style(ax, f"{label}: what it relies on", xlabel="Share of learning gain (%)")
        _hgrid(ax)
    fig.tight_layout()
    return fig


def chart_family_mdape(
    d: pd.DataFrame, methods: list[str], title: str, family: str = "family", prices: str = "prices"
) -> Figure:
    """Median miss per item family (largest families on top) for several methods."""
    d = d[d[family] != "Other"].sort_values(prices)
    n = len(methods)
    h = 0.8 / n
    fig, ax = plt.subplots(figsize=(9.5, 0.42 * len(d) + 1.4), dpi=110)
    y = np.arange(len(d))
    for i, m in enumerate(methods):
        label, color = METHODS[m]
        ax.barh(y + (i - (n - 1) / 2) * h, 100 * d[m], h * 0.92, color=color, label=label)
    ax.set_yticks(y, [f"{f} ({p:,})" for f, p in zip(d[family], d[prices], strict=True)])
    _style(ax, title, xlabel="Median miss against the low-bid unit price (%), lower is better")
    _hgrid(ax)
    _legend_top(ax, n)
    fig.tight_layout()
    return fig


def family_table(scores: pd.DataFrame, methods: list[str]) -> pd.DataFrame:
    s = scores[(scores["test_set"] == "all prices") & (scores["by"] == "family")]
    w = s.pivot_table(index="group", columns="model", values="mdape")
    n = s.groupby("group")["n"].first()
    out = w[methods].assign(prices=n.astype(int)).reset_index()
    return out.rename(columns={"group": "family"})


def chart_by_year(
    rows: pd.DataFrame, methods: list[str], title: str, ylabel: str, signed: bool = False
) -> Figure:
    """rows: one row per year with a column per method (fractions)."""
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
    x = np.arange(len(rows))
    w = 0.8 / len(methods)
    for i, m in enumerate(methods):
        label, color = METHODS.get(m, (m, INK_2))
        bars = ax.bar(
            x + (i - (len(methods) - 1) / 2) * w, 100 * rows[m], w * 0.92, color=color, label=label
        )
        for b in bars:
            v = b.get_height()
            ax.annotate(
                f"{v:+.0f}%" if signed else f"{v:.0f}%",
                (b.get_x() + b.get_width() / 2, v),
                xytext=(0, 3 if v >= 0 else -11),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=INK_2,
            )
    if signed:
        ax.axhline(0, color=INK_2, linewidth=1)
    ax.set_xticks(x, rows["year"].astype(str))
    _style(ax, title, ylabel=ylabel)
    _legend(ax, loc="upper left", ncols=len(methods))
    fig.tight_layout()
    return fig


def baseline_by_year(scores: pd.DataFrame) -> pd.DataFrame:
    s = scores[(scores["test_set"] == "all prices") & (scores["by"] == "year")]
    w = s.pivot_table(index="group", columns="model", values="mdape").reset_index()
    return w.rename(columns={"group": "year"})


# --------------------------------------------------------------------------- 04 Kumo


def kumo_overall() -> pd.DataFrame:
    r = _json(S11 / "results.json")
    return pd.DataFrame(
        [
            {
                "Method": METHODS[k][0],
                "Median miss": pct(r["mdape"][k]),
                "Within 15% of the low bid": pct(r["within_15"][k]),
            }
            for k in ("trailing_median", "xgboost", "lightgbm", "kumo")
        ]
    )


def error_breakdown() -> pd.DataFrame:
    d = pd.read_csv(S12 / "item_error_breakdown.csv")
    return d.rename(columns={f"{m}_mdape": m for m in METHODS})


def noise_floor() -> dict:
    return _json(S12 / "results.json")["noise_floor"]


def chart_kinds(d: pd.DataFrame, floor: dict) -> Figure:
    """Median miss by kind of item and by quantity, with the second-bidder noise floor."""
    order = [
        "Lump sum (quantity 1)",
        "Much larger (over 3x)",
        "Much smaller (under 1/3)",
        "Larger",
        "Smaller",
        "Typical (0.8 to 1.25x)",
    ]
    s = d[d["by"] == "job_size"].set_index("group").reindex(order).reset_index()
    methods = list(METHODS)
    fig, ax = plt.subplots(figsize=(9.5, 4.2), dpi=110)
    y = np.arange(len(s))[::-1]
    h = 0.8 / len(methods)
    for i, m in enumerate(methods):
        ax.barh(y - (i - 1.5) * h, 100 * s[m], h * 0.92, color=METHODS[m][1], label=METHODS[m][0])
    ax.axvline(100 * floor["mdape"], color=INK, linewidth=1.2, linestyle="--")
    ax.annotate(
        f"Second-lowest bidder vs the low bidder: {100 * floor['mdape']:.1f}%",
        (100 * floor["mdape"], -0.75),
        xytext=(4, 0),
        textcoords="offset points",
        fontsize=8,
        color=INK,
    )
    ax.set_ylim(-1.0, y.max() + 0.6)
    ax.set_yticks(y, [f"{g} ({p:,})" for g, p in zip(s["group"], s["prices"], strict=True)])
    _style(
        ax,
        "Median miss by quantity compared with the item's usual quantity",
        xlabel="Median miss (%), lower is better",
    )
    _hgrid(ax)
    _legend_top(ax, 4)
    fig.tight_layout()
    return fig


def frozen_drift() -> pd.DataFrame:
    """Median over (+) / under (-) the low bid by bid year, for the models frozen at 2023."""
    b = pd.read_csv(S10 / "predictions.csv", parse_dates=["bid_open_date"])
    k = pd.read_csv(S11 / "predictions.csv", usecols=["bid_item_id", "kumo"])
    d = b.merge(k, on="bid_item_id")
    yr = d["bid_open_date"].dt.year
    out = {m: (d[m] / d["low_bid_unit_price"] - 1).groupby(yr).median() for m in METHODS}
    return pd.DataFrame(out).rename_axis("year").reset_index()


# --------------------------------------------------------------------------- 05 comparison


def validation_choice() -> pd.DataFrame:
    v = pd.read_csv(S13 / "validation_choice.csv").iloc[0]
    return pd.DataFrame(
        [
            {"Method": METHODS[m][0], "Median miss on 2023 bids": pct(v[f"overall_{m}"])}
            for m in METHODS
        ]
    )


def refreshed_vs_frozen() -> pd.DataFrame:
    r = _json(S13 / "results.json")["test"]
    rows = []
    for m in ("xgboost", "lightgbm", "kumo"):
        for kind, key in (
            ("Frozen at the end of 2023", f"{m}_frozen"),
            ("Refreshed each quarter", m),
        ):
            rows.append(
                {
                    "Method": METHODS[m][0],
                    "How it runs": kind,
                    "Median miss": pct(r[key]["mdape"]),
                    "Within 15%": pct(r[key]["within_15"]),
                    "Median over (+) / under (-)": pct(r[key]["median_signed"], True),
                }
            )
    return pd.DataFrame(rows)


def kumo_drift_frozen_vs_refreshed() -> pd.DataFrame:
    f = frozen_drift()[["year", "kumo"]].rename(columns={"kumo": "frozen"})
    r = pd.read_csv(S13 / "test_predictions_refreshed.csv", parse_dates=["bid_open_date"])
    s = (r["kumo"] / r["low_bid_unit_price"] - 1).groupby(r["bid_open_date"].dt.year).median()
    return f.merge(s.rename("refreshed").rename_axis("year").reset_index(), on="year")


def chart_drift(d: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
    x = np.arange(len(d))
    for i, (col, label, color) in enumerate(
        (
            ("frozen", "Kumo frozen at the end of 2023", ORANGE),
            ("refreshed", "Kumo refreshed each quarter (used)", BLUE),
        )
    ):
        bars = ax.bar(x + (i - 0.5) * 0.38, 100 * d[col], 0.36, color=color, label=label)
        for b in bars:
            v = b.get_height()
            ax.annotate(
                f"{v:+.0f}%",
                (b.get_x() + b.get_width() / 2, v),
                xytext=(0, 3 if v >= 0 else -11),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=INK_2,
            )
    ax.axhline(0, color=INK_2, linewidth=1)
    ax.set_xticks(x, d["year"].astype(str))
    _style(
        ax,
        "Median over (+) or under (-) the low-bid unit price, by bid year",
        ylabel="Median signed miss (%)",
    )
    _legend(ax, loc="upper left")
    fig.tight_layout()
    return fig


def headline() -> pd.DataFrame:
    c = _json(S13 / "results.json")["contract_level"]
    rows = []
    for m in ("trailing_median", "xgboost", "lightgbm", "kumo"):
        h = c[m]["headline"]
        rows.append(
            {
                "Total built with": METHODS[m][0],
                "Closer than the EE": pct(h["bidlens_closer_share"]),
                "Typical miss": pct(h["bidlens_median_abs_error"]),
                "Median over (+) / under (-)": pct(h["bidlens_median_error"], True),
                "Within 15%": pct(h["bidlens_within_15"]),
            }
        )
    h = c["production"]["headline"]
    rows.append(
        {
            "Total built with": "Engineer's estimate",
            "Closer than the EE": "",
            "Typical miss": pct(h["ee_median_abs_error"]),
            "Median over (+) / under (-)": pct(h["ee_median_error"], True),
            "Within 15%": pct(h["ee_within_15"]),
        }
    )
    out = pd.DataFrame(rows)
    out.loc[out["Total built with"] == "Kumo Tabular", "Total built with"] = (
        "Kumo Tabular (BidLens, chosen)"
    )
    return out


def contract_totals() -> pd.DataFrame:
    c = pd.read_csv(S13 / "contract_totals_refreshed.csv")
    return c[c["in_headline"]]


def chart_contract_errors(c: pd.DataFrame) -> Figure:
    """Where each total lands against the actual low bid, one dot per contract."""
    fig, ax = plt.subplots(figsize=(9, 3.4), dpi=110)
    rng = np.random.default_rng(0)
    for yv, col, color in (
        (1, "production_error", BLUE),
        (0, "ee_error", ORANGE),
    ):
        v = 100 * c[col].clip(-0.6, 1.5)
        ax.scatter(v, yv + rng.uniform(-0.18, 0.18, len(v)), s=12, color=color, alpha=0.55)
        med = 100 * c[col].median()
        ax.plot([med, med], [yv - 0.32, yv + 0.32], color=INK, linewidth=2)
        ax.annotate(f"median {med:+.1f}%", (med, yv + 0.34), ha="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=INK_2, linewidth=1, linestyle="--")
    ax.set_yticks([0, 1], ["Engineer's estimate", "BidLens total"])
    ax.set_ylim(-0.6, 1.7)
    _style(
        ax,
        f"{len(c)} test contracts, 2024 to 2026: total vs the actual low bid",
        xlabel="Over (+) or under (-) the low bid (%); clipped at -60% and +150%",
    )
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout()
    return fig


def range_coverage() -> pd.DataFrame:
    return pd.read_csv(S14 / "coverage_by_group.csv")


def range_summary() -> pd.DataFrame:
    r = _json(S14 / "results.json")
    rows = [
        ("Kumo's own 10th to 90th percentile range", r["native"]),
        ("BidLens range (recalibrated each quarter)", r["calibrated"]),
    ]
    return pd.DataFrame(
        [
            {
                "Range": n,
                "Held the low bid": pct(v["coverage"]),
                "Below low": pct(v["below"]),
                "Above high": pct(v["above"]),
                "Typical width (high / low)": f"{v['median_width']:.1f}x",
            }
            for n, v in rows
        ]
    )


def chart_range_coverage(d: pd.DataFrame) -> Figure:
    s = d[(d["by"] == "family") & (d["group"] != "Other")].sort_values("native_prices")
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(s) + 1.4), dpi=110)
    y = np.arange(len(s))
    ax.axvspan(75, 85, color=GRID, alpha=0.6, lw=0)
    ax.axvline(80, color=INK_2, linewidth=1, linestyle="--")
    ax.scatter(100 * s["calibrated_coverage"], y, color=BLUE, s=36, zorder=3)
    ax.set_xlim(min(68, 100 * s["calibrated_coverage"].min() - 2), 90)
    ax.set_yticks(y, [f"{g} ({p:,})" for g, p in zip(s["group"], s["native_prices"], strict=True)])
    _style(
        ax,
        "How often the 80% range held the low bid, by item family",
        xlabel="Share of test prices inside the range (%); target 80%, band 75 to 85%",
    )
    _hgrid(ax)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 06 market


def market_predictions() -> pd.DataFrame:
    return pd.read_csv(S15 / "test_predictions.csv", parse_dates=["bid_open_date"])


def market_scores() -> pd.DataFrame:
    r = _json(S15 / "results.json")
    names = {
        "kumo": "Kumo Tabular",
        "linear": "Linear model",
        "median": "Trailing 12-month median",
        "kumo_no_planholders": "Kumo Tabular, without plan holders",
        "linear_no_planholders": "Linear model, without plan holders",
    }
    rows = []
    for k, name in names.items():
        s, b = r["spread"]["methods"][k], r["bidders"]["methods"][k]
        rows.append(
            {
                "Method": name,
                "Spread: typical miss (points)": f"{100 * s['mae']:.1f}",
                "Spread: within 10 points": pct(s["within"]),
                "Bidders: typical miss": f"{b['mae']:.2f}",
                "Bidders: within 1": pct(b["within"]),
            }
        )
    return pd.DataFrame(rows)


def market_ranges() -> dict:
    r = _json(S15 / "results.json")
    return {
        k: {"coverage": r[k]["range_coverage"], "contracts": r[k].get("contracts")}
        for k in ("spread", "bidders")
    }


def chart_spread(d: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(6.4, 6), dpi=110)
    inside = (d["spread"] >= d["spread_low"]) & (d["spread"] <= d["spread_high"])
    ax.scatter(
        100 * d.loc[inside, "spread_kumo"],
        100 * d.loc[inside, "spread"],
        s=16,
        color=BLUE,
        alpha=0.6,
        label=f"Inside the 80% range ({inside.sum()})",
    )
    ax.scatter(
        100 * d.loc[~inside, "spread_kumo"],
        100 * d.loc[~inside, "spread"],
        s=22,
        color=ORANGE,
        edgecolor=SURFACE,
        linewidth=0.8,
        label=f"Outside the range ({(~inside).sum()})",
    )
    lo, hi = -70, 80
    ax.plot([lo, hi], [lo, hi], color=INK_2, linewidth=1, linestyle="--")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, 120)
    _style(
        ax,
        "Low bid vs the engineer's estimate: expected and actual",
        xlabel="Expected (Kumo, %)",
        ylabel="Actual (%)",
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    _legend(ax, loc="upper left")
    fig.tight_layout()
    return fig


def chart_bidders(d: pd.DataFrame) -> Figure:
    p = d["bidders_kumo"].round().astype(int)
    a = d["bidders"].astype(int)
    counts = pd.crosstab(a, p)
    fig, ax = plt.subplots(figsize=(6.4, 5.4), dpi=110)
    for (actual, pred), n in counts.stack().items():
        if n:
            ax.scatter(pred, actual, s=24 * n, color=BLUE, alpha=0.55, edgecolor=SURFACE)
            if n >= 5:
                ax.annotate(
                    str(n), (pred, actual), ha="center", va="center", fontsize=8, color="white"
                )
    m = max(a.max(), p.max()) + 1
    ax.plot([0, m], [0, m], color=INK_2, linewidth=1, linestyle="--")
    ax.set_xlim(0, m)
    ax.set_ylim(0, m)
    _style(
        ax,
        "Number of bidders: expected and actual (circle size = contracts)",
        xlabel="Expected (Kumo, rounded)",
        ylabel="Actual",
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout()
    return fig


def market_examples(d: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    t = d.sort_values("bid_open_date").tail(n)
    return pd.DataFrame(
        {
            "Contract": t["contract_number"],
            "Bid date": t["bid_open_date"].dt.date.astype(str),
            "Engineer's estimate": t["engineers_estimate"].map("${:,.0f}".format),
            "Expected low bid vs EE (80% range)": [
                f"{100 * k:+.0f}% ({100 * lo:+.0f}% to {100 * hi:+.0f}%)"
                for k, lo, hi in zip(
                    t["spread_kumo"], t["spread_low"], t["spread_high"], strict=True
                )
            ],
            "Actual": (100 * t["spread"]).map("{:+.0f}%".format),
            "Expected bidders (range)": [
                f"{round(k)} ({round(lo)} to {round(hi)})"
                for k, lo, hi in zip(
                    t["bidders_kumo"], t["bidders_low"], t["bidders_high"], strict=True
                )
            ],
            "Actual bidders": t["bidders"].astype(int),
        }
    )


# --------------------------------------------------------------------------- 07 documents


def documents() -> pd.DataFrame:
    d = pd.read_csv(S17 / "documents.csv")
    return d.rename(
        columns={
            "file": "File",
            "title": "Document",
            "pages": "Pages",
            "empty_pages": "Pages without text",
            "characters": "Characters",
            "chunks": "Passages",
        }
    )


def bid_item_check() -> dict:
    return _json(S17 / "results.json")


RUN_NAMES = {
    "local_llama3.1-8b": "Round 1: llama3.1:8b, open list",
    "local_qwen3-8b": "Round 1: qwen3:8b, open list",
    "local_qwen3-8b_v2": "qwen3:8b, checklist",
    "local_llama3.1-8b_v2": "llama3.1:8b, checklist",
    "patterns": "Pattern rules only",
    "qwen_patterns": "qwen3:8b checklist + patterns",
    "combined": "Combined: both models + patterns (default)",
}


def extraction_metrics() -> pd.DataFrame:
    cols = [
        "run",
        "items_kept",
        "precision",
        "gold_facts_found",
        "recall",
        "f1",
        "citation_accuracy",
        "minutes",
    ]
    d = pd.concat([pd.read_csv(S19 / "metrics.csv")[cols], pd.read_csv(S20 / "metrics.csv")[cols]])
    d["Run"] = d["run"].map(RUN_NAMES)
    return d.reset_index(drop=True)


def extraction_table(d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Run": d["Run"],
            "Findings": d["items_kept"],
            "Precision": d["precision"].map(pct),
            "Gold facts found (of 89)": d["gold_facts_found"],
            "Recall": d["recall"].map(pct),
            "F1": d["f1"].map(pct),
            "Citation accuracy": d["citation_accuracy"].map(pct),
            "Minutes": d["minutes"].round(0).astype(int),
        }
    )


def chart_extraction(d: pd.DataFrame) -> Figure:
    order = [
        "local_llama3.1-8b",
        "local_qwen3-8b",
        "patterns",
        "local_llama3.1-8b_v2",
        "local_qwen3-8b_v2",
        "qwen_patterns",
        "combined",
    ]
    s = d.set_index("run").loc[order[::-1]]
    fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=110)
    y = np.arange(len(s))
    for i, (col, label, color) in enumerate(
        (
            ("precision", "Precision", AQUA),
            ("recall", "Recall", ORANGE),
            ("f1", "F1 (balance of the two)", BLUE),
        )
    ):
        bars = ax.barh(y + (1 - i) * 0.26, 100 * s[col], 0.24, color=color, label=label)
        if col == "f1":
            for b in bars:
                ax.annotate(
                    f"{b.get_width():.1f}%",
                    (b.get_width(), b.get_y() + 0.12),
                    xytext=(3, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8,
                    color=INK,
                )
    ax.set_yticks(y, s["Run"])
    ax.set_xlim(0, 108)
    _style(
        ax,
        "Reading contract 04-0W0504: 89 facts an estimator needs",
        xlabel="Percent (higher is better)",
    )
    _hgrid(ax)
    _legend_top(ax, 3)
    fig.tight_layout()
    return fig


TOPIC_NAMES = {
    "scope": "Scope",
    "time_damages": "Time and damages",
    "traffic": "Traffic and closures",
    "environmental": "Environmental",
    "hazardous": "Hazardous materials",
    "geotechnical": "Site conditions",
    "utilities": "Utilities",
    "bid_requirements": "Bid requirements",
    "submittals": "Submittals",
    "payment": "Payment terms",
}


def recall_by_topic() -> pd.DataFrame:
    r1 = pd.read_csv(S19 / "metrics.csv").set_index("run").loc["local_qwen3-8b"]
    r2 = pd.read_csv(S20 / "metrics.csv").set_index("run").loc["combined"]
    gold = pd.read_csv(S19 / "gold_facts.csv")["topic"].value_counts()
    rows = [
        {
            "topic": t,
            "Topic": n,
            "gold": int(gold.get(t, 0)),
            "round1": r1[f"recall_{t}"],
            "combined": r2[f"recall_{t}"],
        }
        for t, n in TOPIC_NAMES.items()
    ]
    return pd.DataFrame(rows)


def chart_recall_by_topic(d: pd.DataFrame) -> Figure:
    s = d.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=110)
    y = np.arange(len(s))
    ax.barh(y + 0.19, 100 * s["round1"], 0.36, color=GREY, label="Round 1: qwen3:8b alone")
    ax.barh(y - 0.19, 100 * s["combined"], 0.36, color=BLUE, label="Round 2: combined (default)")
    ax.set_yticks(y, [f"{t} ({g})" for t, g in zip(s["Topic"], s["gold"], strict=True)])
    ax.set_xlim(0, 100)
    _style(ax, "Share of gold facts found, by topic (gold facts in brackets)", xlabel="Recall (%)")
    _hgrid(ax)
    _legend_top(ax, 2)
    fig.tight_layout()
    return fig


def example_findings(n_per_source: int = 3) -> pd.DataFrame:
    """A few findings of the default run that were judged correct, with their citations."""
    d = pd.read_csv(S20 / "extracted_combined.csv")
    j = pd.read_csv(S20 / "judging_sheet.csv")[["statement", "evidence", "verdict"]]
    d = d.merge(j.drop_duplicates(["statement", "evidence"]), on=["statement", "evidence"])
    d = d[d["category"].isin(TOPIC_NAMES) & (d["verdict"] == "correct")]
    pick = pd.concat(
        [
            d[d["source"] == "pattern"].head(n_per_source),
            d[d["source"] != "pattern"].drop_duplicates("category").head(n_per_source),
        ]
    )
    return pd.DataFrame(
        {
            "Topic": pick["category"].map(TOPIC_NAMES),
            "Found by": pick["source"].map(
                lambda s: "pattern rule" if s == "pattern" else "local model"
            ),
            "Finding": pick["statement"],
            "Document": pick["document"].str.slice(0, 40),
            "PDF page": pick["page"],
            "Section": pick["section_number"].fillna(""),
        }
    )


def draft_check() -> dict:
    return _json(SAMPLE / "summary.json")


def chart_draft(s: dict) -> Figure:
    low = s["low_bid_cost"]
    rows = [
        ("BidLens draft", s["estimate_total"], BLUE),
        ("Engineer's estimate", s["engineers_estimate"], ORANGE),
        ("Actual low bid", low, GREY),
    ]
    fig, ax = plt.subplots(figsize=(9, 2.8), dpi=110)
    y = np.arange(len(rows))[::-1]
    for yi, (name, v, color) in zip(y, rows, strict=True):
        ax.barh(yi, v / 1e6, 0.6, color=color)
        note = "" if name == "Actual low bid" else f"  ({100 * (v / low - 1):+.0f}% vs the low bid)"
        ax.annotate(
            f"${v / 1e6:,.2f}M{note}",
            (v / 1e6, yi),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
        )
    ax.set_yticks(y, [r[0] for r in rows])
    ax.set_xlim(0, s["engineers_estimate"] / 1e6 * 1.45)
    _style(
        ax,
        f"Contract {s['contract']}: the BidLens draft against the real result",
        xlabel="Millions of dollars",
    )
    _hgrid(ax)
    fig.tight_layout()
    return fig
