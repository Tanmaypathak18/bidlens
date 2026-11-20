"""Data overview for notebooks/01_data_overview.ipynb (decision D-032).

Each function returns a small pandas table or a matplotlib figure. No bidder identities are
read: bids are identified by rank only.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.figure import Figure

DB = Path("data/bidlens.duckdb")
OUT = Path("outputs/07_data_overview")

# Reference palette (dataviz skill), validated: blue, orange, aqua. Fixed order.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def connect(db: Path = DB) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db), read_only=True)


def _style(ax, title: str, xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK_2)
    ax.set_ylabel(ylabel, color=INK_2)
    ax.tick_params(colors=INK_2, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


# --------------------------------------------------------------------------- tables


def headline(con) -> pd.DataFrame:
    rows = {
        "Bid prices": "SELECT count(*) FROM bid",
        "Bid items (priced lines)": "SELECT count(*) FROM bid_item",
        "Contract openings": "SELECT count(*) FROM contract",
        "Contracts with a bid summary": "SELECT count(*) FROM contract WHERE has_bid_summary",
        "Item codes in scope": "SELECT count(DISTINCT item_code) FROM bid_item",
        "First bid date": "SELECT min(bid_open_date) FROM contract",
        "Last bid date": "SELECT max(bid_open_date) FROM contract",
    }
    return pd.DataFrame(
        [(k, con.execute(q).fetchone()[0]) for k, q in rows.items()], columns=["Measure", "Value"]
    )


def contracts_by_year(con) -> pd.DataFrame:
    return con.execute("""
        SELECT year(bid_open_date) AS year,
               count(*) FILTER (WHERE district = '04') AS "District 4",
               count(*) FILTER (WHERE district = '05') AS "District 5"
        FROM contract GROUP BY 1 ORDER BY 1
    """).df()


def summary_coverage_by_year(con) -> pd.DataFrame:
    return con.execute("""
        SELECT year(bid_open_date) AS year,
               count(*) FILTER (WHERE has_bid_summary) AS "Usable bid summary",
               count(*) FILTER (WHERE NOT has_bid_summary) AS "No usable summary"
        FROM contract GROUP BY 1 ORDER BY 1
    """).df()


def families(con) -> pd.DataFrame:
    return con.execute("""
        SELECT item_family AS "Item family", count(DISTINCT item_code) AS "Items",
               count(DISTINCT contract_id) AS "Contracts", count(*) AS "Bid prices",
               round(sum(total) FILTER (WHERE bid_rank = 1) / 1e6, 1) AS "Low-bid $M"
        FROM bid_normalized GROUP BY 1 ORDER BY 5 DESC
    """).df()


def cross_check(path: Path = Path("outputs/04_cross_check/cross_check.csv")) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"item_code": str})


def cross_check_table(xc: pd.DataFrame) -> pd.DataFrame:
    reason = xc["reason"].fillna("")
    return pd.DataFrame(
        {
            "Result": [
                "Identical to the cent",
                "Differs: sources name a different low bidder",
                "Differs on one item only",
            ],
            "Prices": [
                int((xc["match"] == "yes").sum()),
                int(reason.str.startswith("Sources disagree").sum()),
                int(reason.str.startswith("Price differs").sum()),
            ],
        }
    ).assign(Share=lambda d: (d["Prices"] / d["Prices"].sum()).map("{:.1%}".format))


def quality(con) -> pd.DataFrame:
    bids = con.execute("SELECT flag, count(*) FROM bid_flag GROUP BY 1").df()
    contracts = con.execute("SELECT flag, count(*) FROM contract_flag GROUP BY 1").df()
    bids.columns = contracts.columns = ["Check", "Flagged"]
    bids.insert(0, "Applies to", "Bid price")
    contracts.insert(0, "Applies to", "Contract")
    return pd.concat([bids, contracts], ignore_index=True)


def hma_prices(con, item_code: str = "390132") -> pd.DataFrame:
    return con.execute(f"""
        SELECT c.bid_open_date, b.unit_price::DOUBLE AS unit_price, b.bid_rank,
               i.quantity::DOUBLE AS quantity
        FROM bid b JOIN bid_item i USING (bid_item_id) JOIN contract c USING (contract_id)
        WHERE i.item_code = '{item_code}' AND b.bid_rank = 1
          AND (b.bid_item_id, b.bid_rank) NOT IN (SELECT bid_item_id, bid_rank FROM bid_flag)
        ORDER BY 1
    """).df()


# --------------------------------------------------------------------------- charts


def _label_bars(ax, bars, fmt="{:,.0f}") -> None:
    for bar in bars:
        h = bar.get_height()
        if h:
            ax.annotate(
                fmt.format(h),
                (bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color=INK_2,
            )


def chart_contracts_by_year(df: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
    x = range(len(df))
    w = 0.38
    b1 = ax.bar([i - w / 2 - 0.01 for i in x], df["District 4"], w, color=BLUE, label="District 4")
    b2 = ax.bar(
        [i + w / 2 + 0.01 for i in x], df["District 5"], w, color=ORANGE, label="District 5"
    )
    _label_bars(ax, b1)
    _label_bars(ax, b2)
    ax.set_xticks(list(x), df["year"].astype(str))
    _style(ax, "Contract openings per year", ylabel="Contracts")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    return fig


def chart_summary_coverage(df: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=110)
    x = df["year"].astype(str)
    usable = ax.bar(x, df["Usable bid summary"], 0.7, color=BLUE, label="Usable bid summary")
    ax.bar(
        x,
        df["No usable summary"],
        0.7,
        bottom=df["Usable bid summary"] + 0.6,  # thin surface gap between segments
        color=ORANGE,
        label="No usable summary",
    )
    for bar in usable:  # labels inside the blue segment, clear of the orange one
        h = bar.get_height()
        if h:
            ax.annotate(
                f"{h:,.0f}",
                (bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, -12),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="white",
            )
    _style(ax, "Contracts with a usable bid summary, by year", ylabel="Contracts")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    return fig


def chart_families(df: pd.DataFrame) -> Figure:
    d = df.sort_values("Low-bid $M")
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=110)
    bars = ax.barh(d["Item family"], d["Low-bid $M"], 0.65, color=BLUE)
    for bar in bars:
        ax.annotate(
            f"${bar.get_width():,.0f}M",
            (bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK_2,
        )
    _style(ax, "Low-bid dollars by item family, 2018-2026", xlabel="Millions of dollars")
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    fig.tight_layout()
    return fig


def chart_cross_check(xc: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(6, 6), dpi=110)
    a = xc["cost_database_unit_price"].clip(lower=0.01)
    b = xc["bid_summary_unit_price"].clip(lower=0.01)
    same = xc["match"] == "yes"
    ax.scatter(a[same], b[same], s=10, color=BLUE, alpha=0.5, label=f"Identical ({same.sum():,})")
    ax.scatter(
        a[~same],
        b[~same],
        s=18,
        color=ORANGE,
        edgecolor=SURFACE,
        linewidth=0.8,
        label=f"Different ({(~same).sum():,})",
    )
    lo, hi = min(a.min(), b.min()), max(a.max(), b.max())
    ax.plot([lo, hi], [lo, hi], color=INK_2, linewidth=1, linestyle="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    _style(
        ax,
        "Low bidder's unit price: cost database vs bid summary",
        xlabel="Cost database ($ per unit, log scale)",
        ylabel="Bid summary ($ per unit, log scale)",
    )
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    return fig


def chart_hma(df: pd.DataFrame) -> Figure:
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=110)
    ax.scatter(
        df["bid_open_date"],
        df["unit_price"],
        s=10,
        color=BLUE,
        alpha=0.45,
        label="Low bid on one contract",
    )
    yearly = df.groupby(df["bid_open_date"].dt.year)["unit_price"].median()
    mids = pd.to_datetime([f"{y}-07-01" for y in yearly.index])
    ax.plot(
        mids,
        yearly.values,
        color=ORANGE,
        linewidth=2,
        marker="o",
        markersize=5,
        label="Median for the year",
    )
    for x, y in zip(mids[[0, -1]], yearly.values[[0, -1]], strict=True):
        ax.annotate(
            f"${y:,.0f}",
            (x, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=INK,
        )
    ax.set_yscale("log")
    _style(ax, "Hot mix asphalt (Type A), low bid per ton", ylabel="$ per ton (log scale)")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    return fig


def save(fig: Figure, name: str, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor())
    return path


def save_tables(tables: dict[str, pd.DataFrame], out: Path = OUT) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, df in tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths


def write_readme(out: Path = OUT) -> Path:
    files = sorted(p.name for p in out.iterdir() if p.name != "README.md")
    rows = "\n".join(f"| `{f}` |" for f in files)
    text = f"""# 07 Data overview

The results of `notebooks/01_data_overview.ipynb`: a plain-language tour of the data
collected in stages 02 to 06. It covers coverage by district and year, bid summary
coverage, item families, the cross-check between the two Caltrans sources, and data
quality.

| File |
| --- |
{rows}

**How it was produced:** run the notebook top to bottom:
`uv run jupyter nbconvert --execute --to notebook --inplace notebooks/01_data_overview.ipynb`.
It reads `data/bidlens.duckdb` (built by `make data`) and calls
`src/bidlens/analysis/overview.py`. The charts here are the same ones shown in the notebook.
No file names a bidder.
"""
    path = out / "README.md"
    path.write_text(text, encoding="utf-8")
    return path
