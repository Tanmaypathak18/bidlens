"""Step 2.2: price escalation with the Caltrans cost index (decisions D-039, D-040).

Usage:
    uv run python -m bidlens.pricing.escalate

Fills `cost_index` and the `bid_escalated` view, and writes outputs/09_price_escalation.

The quarterly index (CHCCI, 2020 base) is recovered from the sv08data results pages in the
raw cache: each page prints the current 12-month index I(c) and every row's original and
adjusted unit price, where adjusted = original x I(c) / I(quarter). No new requests are
made. Escalation uses the 4-quarter trailing mean as known before each bid-opening quarter
(D-044: through the previous quarter); quarters not yet
published carry forward the last published value.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bidlens.ingest.parse_sv08 import ParseError, parse_adjusted

RAW_SERIES = "CHCCI_2020"
SERIES = "CHCCI_2020_KNOWN"  # 4-quarter mean through the previous quarter (D-044)
MIN_PRICE = 100.0  # rows priced lower lose precision to the cent rounding of adjusted prices
MAX_SPREAD = 0.001  # implied index values within a quarter must agree to 0.1%
WINDOW = 4

ROOT = Path(".")
DB = ROOT / "data" / "bidlens.duckdb"
CACHE = ROOT / "data" / "raw" / "sv08data" / "results"
OUT = ROOT / "outputs" / "09_price_escalation"


# --------------------------------------------------------------- the index


def implied_index(pages) -> pd.DataFrame:
    """Quarterly index values implied by results pages (an iterable of HTML strings).

    Returns one row per bid-opening quarter: year, quarter, value (NaN when the quarter is
    not yet published, i.e. every adjusted price equals its original), n_contracts,
    n_rows and the relative spread of the implied values.
    """
    by_q: dict[tuple[int, int], list[float]] = defaultdict(list)
    unchanged: dict[tuple[int, int], bool] = defaultdict(lambda: True)
    contracts: dict[tuple[int, int], set] = defaultdict(set)
    for html in pages:
        try:
            page = parse_adjusted(html)
        except ParseError:
            continue
        for contract, opened, price, adjusted in page.rows:
            if price < MIN_PRICE or adjusted <= 0:
                continue
            q = (opened.year, (opened.month - 1) // 3 + 1)
            contracts[q].add((contract, opened))
            by_q[q].append(page.current_index * price / adjusted)
            unchanged[q] &= abs(adjusted - price) < 0.005
    rows = []
    for q in sorted(by_q):
        v = by_q[q]
        med = statistics.median(v)
        spread = (max(v) - min(v)) / med
        if spread > MAX_SPREAD:
            raise ValueError(f"index for {q[0]} Q{q[1]} is inconsistent (spread {spread:.4%})")
        rows.append(
            {
                "year": q[0],
                "quarter": q[1],
                "value": np.nan if unchanged[q] else round(med, 2),
                "n_contracts": len(contracts[q]),
                "n_rows": len(v),
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def read_cache(cache: Path = CACHE):
    for f in sorted(cache.glob("*.html.gz")):
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            yield fh.read()


def smooth(quarterly: pd.DataFrame, through: date | None = None) -> pd.DataFrame:
    """The index as known before each quarter's bids open (D-040, lagged by D-044): for
    quarter Q, the mean of the published values of the 4 quarters before Q. Caltrans
    computes quarter Q's own value from the bids opened in Q, so it is never used for Q.
    Carried forward to `through` (default: the last quarter in `quarterly`). The first
    quarter has no earlier value and uses its own."""
    pub = quarterly.dropna(subset=["value"])
    s = pd.Series(
        pub["value"].to_numpy(dtype=float),
        index=pd.PeriodIndex(
            [
                pd.Period(year=y, quarter=q, freq="Q")
                for y, q in zip(pub["year"], pub["quarter"], strict=True)
            ],
            freq="Q",
        ),
    ).sort_index()
    mean = s.rolling(WINDOW, min_periods=1).mean()
    last = pd.Period(
        year=int(quarterly["year"].iloc[-1]), quarter=int(quarterly["quarter"].iloc[-1]), freq="Q"
    )
    if through is not None:
        last = max(last, pd.Period(pd.Timestamp(through), freq="Q"))
    full = mean.reindex(pd.period_range(s.index[0], last, freq="Q")).ffill()
    known = full.shift(1)
    known.iloc[0] = full.iloc[0]
    full = known
    return pd.DataFrame(
        {
            "year": full.index.year,
            "quarter": full.index.quarter,
            "value": full.to_numpy().round(4),
            "published": full.index.isin(s.index),
        }
    )


class CostIndex:
    """Quarter -> index value, with escalation factors between dates."""

    def __init__(self, series: pd.DataFrame) -> None:
        s = series.sort_values(["year", "quarter"])
        self.periods = pd.PeriodIndex(
            [
                pd.Period(year=int(y), quarter=int(q), freq="Q")
                for y, q in zip(s["year"], s["quarter"], strict=True)
            ],
            freq="Q",
        )
        self.values = s["value"].to_numpy(dtype=float)
        self._first, self._last = self.periods[0], self.periods[-1]

    def value(self, dates) -> np.ndarray:
        """Index value at each date's quarter (clamped to the ends of the series)."""
        p = pd.PeriodIndex(pd.to_datetime(pd.Series(dates)), freq="Q")
        ordinal = np.clip(p.asi8, self._first.ordinal, self._last.ordinal)
        return self.values[ordinal - self._first.ordinal]

    def escalate(self, prices, from_dates, to_date) -> np.ndarray:
        prices = np.asarray(prices, dtype=float)
        if len(prices) == 0:
            return prices
        return prices * self.value([to_date])[0] / self.value(from_dates)

    @classmethod
    def from_db(cls, con: duckdb.DuckDBPyConnection, series: str = SERIES) -> CostIndex:
        df = con.execute(
            "SELECT year, quarter, value FROM cost_index WHERE series = ? ORDER BY 1, 2",
            [series],
        ).df()
        if df.empty:
            raise RuntimeError(
                f"cost_index has no {series} rows; run `uv run python -m bidlens.pricing.escalate`"
            )
        return cls(df)


# --------------------------------------------------------------- database


def store(con: duckdb.DuckDBPyConnection, quarterly: pd.DataFrame, series: pd.DataFrame) -> None:
    """Write both series to cost_index and (re)create the bid_escalated view."""
    # CHCCI_2020_4Q is the unlagged series used before D-044.
    con.execute(
        "DELETE FROM cost_index WHERE series IN (?, ?, 'CHCCI_2020_4Q')", [RAW_SERIES, SERIES]
    )
    raw = quarterly.dropna(subset=["value"])
    con.executemany(
        "INSERT INTO cost_index VALUES (?, ?, ?, ?)",
        [(RAW_SERIES, int(r.year), int(r.quarter), float(r.value)) for r in raw.itertuples()]
        + [(SERIES, int(r.year), int(r.quarter), float(r.value)) for r in series.itertuples()],
    )
    con.execute(f"""
        CREATE OR REPLACE VIEW bid_escalated AS
        WITH ref AS (
            SELECT year AS ref_year, quarter AS ref_quarter, value AS ref_index
            FROM cost_index WHERE series = '{SERIES}'
            ORDER BY year DESC, quarter DESC LIMIT 1
        )
        SELECT n.*, c.bid_open_date, ci.value AS cost_index, ref.ref_year, ref.ref_quarter,
               ref.ref_index,
               CAST(n.unit_price AS DOUBLE) * ref.ref_index / ci.value AS unit_price_escalated
        FROM bid_normalized n
        JOIN contract c USING (contract_id)
        JOIN cost_index ci ON ci.series = '{SERIES}'
             AND ci.year = year(c.bid_open_date) AND ci.quarter = quarter(c.bid_open_date)
        CROSS JOIN ref
    """)


# --------------------------------------------------------------- check report


def item_trend(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Typical low-bid price level by bid year, relative to 2020, before and after
    escalation: the median over items of (item's median price that year / its 2020 median)."""
    return con.execute("""
        WITH x AS (
            SELECT item_code, unit, year(bid_open_date) AS y,
                   median(CAST(unit_price AS DOUBLE)) AS raw,
                   median(unit_price_escalated) AS esc
            FROM bid_escalated WHERE bid_rank = 1 AND unit_price > 0
            GROUP BY ALL
        )
        SELECT a.y AS year, count(*) AS items,
               exp(median(ln(a.raw / b.raw))) AS unescalated,
               exp(median(ln(a.esc / b.esc))) AS escalated
        FROM x a JOIN x b ON a.item_code = b.item_code AND a.unit = b.unit AND b.y = 2020
        GROUP BY 1 ORDER BY 1
    """).df()


def write_chart(
    path: Path, quarterly: pd.DataFrame, series: pd.DataFrame, trend: pd.DataFrame
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def _x(df):
        return df["year"] + (df["quarter"] - 1) / 4

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.5))
    pub = quarterly.dropna(subset=["value"])
    a1.plot(_x(pub), pub["value"], marker="o", ms=3, lw=1, color="#9aa5b1", label="Quarterly index")
    a1.plot(
        _x(series),
        series["value"],
        lw=2.5,
        color="#1f5fa8",
        label="Known before the quarter: mean of previous 4 (used)",
    )
    fwd = series[~series["published"]]
    if len(fwd):
        a1.plot(
            _x(fwd),
            fwd["value"],
            ls="none",
            marker="s",
            ms=5,
            color="#d9822b",
            label="Not yet published: carried forward",
        )
    a1.set_title("Caltrans highway construction cost index (2020 = 100)")
    a1.set_xlabel("Bid opening quarter")
    a1.legend(frameon=False, fontsize=9)
    a1.grid(alpha=0.3)

    a2.axhline(1, color="#666", lw=0.8)
    a2.plot(
        trend["year"],
        trend["unescalated"],
        marker="o",
        lw=2,
        color="#d9822b",
        label="Prices as bid",
    )
    a2.plot(
        trend["year"],
        trend["escalated"],
        marker="o",
        lw=2,
        color="#1f5fa8",
        label="Prices after escalation",
    )
    a2.set_title("Typical item price vs the same item in 2020")
    a2.set_xlabel("Bid year")
    a2.legend(frameon=False, fontsize=9)
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_outputs(
    out: Path,
    quarterly: pd.DataFrame,
    series: pd.DataFrame,
    trend: pd.DataFrame,
    n_escalated: int,
    ref: tuple[int, int, float],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    q = quarterly.merge(
        series.rename(columns={"value": "value_4q_mean"}), on=["year", "quarter"], how="outer"
    )
    q = q.rename(columns={"value": "quarterly_index"})
    q[
        [
            "year",
            "quarter",
            "quarterly_index",
            "value_4q_mean",
            "published",
            "n_contracts",
            "n_rows",
        ]
    ].to_csv(out / "cost_index.csv", index=False)
    trend.to_csv(out / "price_level_check.csv", index=False, float_format="%.4f")
    write_chart(out / "escalation_check.png", quarterly, series, trend)
    last_pub = series[series["published"]].iloc[-1]
    fwd = series[~series["published"]]
    fwd_txt = (
        ", ".join(f"{int(r.year)} Q{int(r.quarter)}" for r in fwd.itertuples())
        if len(fwd)
        else "none"
    )
    trend_lines = [
        "| Bid year | Items | Prices as bid | After escalation |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for r in trend.itertuples():
        trend_lines.append(f"| {r.year} | {r.items} | {r.unescalated:.2f} | {r.escalated:.2f} |")
    body = f"""
Bringing old bid prices to today's dollars with Caltrans' own cost index (step 2.2).

## The question

A price bid in 2019 is not a fair comparison for a bid in 2025: construction costs rose
sharply after 2021. Before comparing prices across years, each one is adjusted by how much
Caltrans' highway construction cost index moved between the two bid dates.

## Where the index comes from (decision D-039)

Caltrans publishes a quarterly California highway construction cost index (CHCCI, 2020 =
100). Its table sits on a Caltrans site that does not allow automated access, so it is not
downloaded. Instead, the index is recovered from the Caltrans cost database pages we had
already collected: every page shows each price both as bid and "adjusted to today's
dollars" with this index, along with today's index. The ratio between the two gives the
index for the quarter the bid opened. All {int(quarterly["n_contracts"].sum()):,} contracts
give the same value within each quarter (largest disagreement
{quarterly["spread"].max():.4%}), so the recovered numbers are Caltrans' own.

## Which version of the index is used (decisions D-040, D-044)

The quarterly index jumps around (it rests on the few contracts bid each quarter), so
prices are adjusted with its **4-quarter average**, the same idea as Caltrans' own
12-month index. And because Caltrans works out each quarter's index from the bids opened
in that quarter, a bid is valued only with what was known before it opened: the average
of the four previous quarters. On 2022 and 2023 training bids, this removed the
under-pricing that inflation causes in a 12-month historical median (from 8% too low to
0.2% too low).

The last published quarter is {int(last_pub.year)} Q{int(last_pub.quarter)}. Later quarters
({fwd_txt}) are not published yet and use that quarter's value.

![Cost index and price levels](escalation_check.png)

## Check: do escalated prices stay level?

For each item, its median low-bid price in a year is compared with its own 2020 median;
the table shows the typical ratio across items. As bid, prices rose about
{100 * (trend["unescalated"].iloc[-1] - 1):.0f}% from 2020 to {int(trend["year"].iloc[-1])}.
After escalation to the same date they should stay near 1.00.

{chr(10).join(trend_lines)}

Escalation narrows the range of yearly price levels from
{trend["unescalated"].min():.2f}–{trend["unescalated"].max():.2f} as bid to
{trend["escalated"].min():.2f}–{trend["escalated"].max():.2f}. It does not track every year:
the index follows a broad basket of Caltrans work, and items in this slice can move
against it (in this data, item prices dipped in 2025 while the index's 4-quarter average
was still rising). The pricing models in steps 2.3 to 2.5 also see the bid date, so they
can correct what the index misses.

## What is stored

- Database table `cost_index`: series `{RAW_SERIES}` (published quarterly values) and
  `{SERIES}` (the 4-quarter average as known before each quarter, carried forward).
- Database view `bid_escalated`: every bid ({n_escalated:,} rows) with its unit price in
  {ref[0]} Q{ref[1]} dollars (index {ref[2]:.2f}). Models escalate to each bid's own date
  instead, through `bidlens.pricing.setup.escalate`.

## Files

- `cost_index.csv`: every quarter: the published index, the 4-quarter average, and how many
  contracts and prices it was recovered from.
- `price_level_check.csv`: the table above.
- `escalation_check.png`: the chart above.

## How it was produced

`uv run python -m bidlens.pricing.escalate` (code in `src/bidlens/pricing/escalate.py`),
from the raw cache in `data/raw/sv08data/results/`. Generated {date.today().isoformat()}.
"""
    (out / "README.md").write_text(
        "# 09 Price escalation\n\n" + body.strip() + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    quarterly = implied_index(read_cache())
    series = smooth(quarterly, through=date.today())
    con = duckdb.connect(str(DB))
    store(con, quarterly, series)
    trend = item_trend(con)
    n = con.execute("SELECT count(*) FROM bid_escalated").fetchone()[0]
    n_bids = con.execute("SELECT count(*) FROM bid").fetchone()[0]
    if n != n_bids:
        raise RuntimeError(f"bid_escalated has {n} rows, bid has {n_bids}: a quarter is missing")
    ref = con.execute(
        "SELECT ref_year, ref_quarter, ref_index FROM bid_escalated LIMIT 1"
    ).fetchone()
    con.close()
    write_outputs(OUT, quarterly, series, trend, n, ref)

    from bidlens.outputs import write_index

    write_index()
    print(
        json.dumps(
            {
                "published_quarters": int(quarterly["value"].notna().sum()),
                "unpublished_quarters": int(quarterly["value"].isna().sum()),
                "max_spread": float(quarterly["spread"].max()),
                "bid_escalated_rows": n,
                "reference": list(ref),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
