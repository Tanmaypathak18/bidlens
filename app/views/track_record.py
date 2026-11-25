"""Track record: how BidLens totals compared with the engineer's estimate on every test job."""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from common import engine, sidebar_links, stage
from design import NAVY, SLATE, chart, how_to_read, setup, tile

from bidlens.live.backtest import second_bid_gap

setup("Track record")
sidebar_links()
st.markdown(
    """<div class="bl-head"><h1>Track record</h1><div class="bl-sub">Every Caltrans job bid
from January 2024 to November 2026 in Districts 4 and 5 that BidLens could price item by item,
each priced only from bids opened before it, then compared with what actually happened.</div>
</div>""",
    unsafe_allow_html=True,
)

totals = stage("13_model_comparison", "contract_totals_refreshed.csv")
if totals is None:
    st.warning("The model comparison results (outputs/13_model_comparison) are missing.")
    st.stop()
h = totals[totals["in_headline"]].copy()
h["bid_open_date"] = pd.to_datetime(h["bid_open_date"])
gap = second_bid_gap(engine().b.contracts, h)
g = float(gap.median())
bl, ee = h["production_error"], h["ee_error"]
closer = float((bl.abs() < ee.abs()).mean())

a, b, c, d = st.columns(4)
tile(a, "Jobs checked", f"{len(h)}", "bid 2024 to 2026")
tile(
    b, "BidLens closer than the estimate", f"{closer:.0%}", "of jobs, to the actual low bid", "good"
)
tile(
    c,
    "Typical miss",
    f"{bl.abs().median():.0%} vs {ee.abs().median():.0%}",
    "BidLens vs the engineer's estimate",
)
tile(d, "Second bid above the low bid", f"{g:.1%}", "median: the market's own spread")

st.write("")
left, right = st.columns(2, gap="large")
with left:
    st.markdown("**Each job: estimate against the actual low bid**")
    long = pd.concat(
        [
            pd.DataFrame(
                {
                    "low": h["low_bid_cost"],
                    "est": h["production_total"],
                    "who": "BidLens draft",
                    "job": h["contract_number"],
                }
            ),
            pd.DataFrame(
                {
                    "low": h["low_bid_cost"],
                    "est": h["engineers_estimate"],
                    "who": "Engineer's estimate",
                    "job": h["contract_number"],
                }
            ),
        ],
        ignore_index=True,
    )
    long[["low", "est"]] = long[["low", "est"]] / 1e6
    lo, hi = (
        float(long[["low", "est"]].min().min()) * 0.8,
        float(long[["low", "est"]].max().max()) * 1.2,
    )
    sc = alt.Scale(type="log", domain=[lo, hi], nice=False)
    ax = alt.Axis(format="$,.2~f", values=[0.3, 1, 3, 10, 30, 100])
    pts = (
        alt.Chart(long)
        .mark_circle(size=34, opacity=0.65)
        .encode(
            x=alt.X("low:Q", title="Actual low bid ($ millions, log scale)", scale=sc, axis=ax),
            y=alt.Y("est:Q", title="Estimate ($ millions, log scale)", scale=sc, axis=ax),
            color=alt.Color(
                "who:N",
                scale=alt.Scale(
                    domain=["BidLens draft", "Engineer's estimate"], range=[NAVY, "#E39B2D"]
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                "job",
                "who",
                alt.Tooltip("est:Q", format="$,.2f", title="estimate $M"),
                alt.Tooltip("low:Q", format="$,.2f", title="low bid $M"),
            ],
        )
    )
    diag = (
        alt.Chart(pd.DataFrame({"x": [lo, hi], "y": [lo, hi]}))
        .mark_line(color=SLATE, strokeDash=[4, 4])
        .encode(x=alt.X("x:Q", scale=sc), y=alt.Y("y:Q", scale=sc))
    )
    st.altair_chart(chart(diag + pts, height=400), width="stretch")
    how_to_read(
        "each job appears twice: once for the BidLens draft (navy) and once for the engineer's "
        "estimate (orange). Dots on the dashed line hit the low bid exactly; above the line is "
        "too high, below is too low."
    )
with right:
    st.markdown("**How far off, job by job**")
    bins = np.arange(-0.6, 0.61, 0.1)
    rows = []
    for who, e in (("BidLens draft", bl), ("Engineer's estimate", ee)):
        cut = pd.cut(e.clip(-0.599, 0.599), bins)
        for iv, n in cut.value_counts(sort=False).items():
            # Each 10-point bin is split: BidLens on the left half, the estimate on the right.
            left = who == "BidLens draft"
            rows.append(
                {
                    "who": who,
                    "jobs": int(n),
                    "from": iv.left + (0.005 if left else 0.05),
                    "to": iv.mid if left else iv.right - 0.005,
                    "bin": f"{100 * iv.left:+.0f}% to {100 * iv.right:+.0f}%",
                }
            )
    hist = pd.DataFrame(rows)
    band = pd.DataFrame({"lo": [-g], "hi": [g]})
    shade = alt.Chart(band).mark_rect(color="#D7EFD9").encode(x="lo:Q", x2="hi:Q")
    bars = (
        alt.Chart(hist)
        .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(
                "from:Q",
                title="Miss vs the actual low bid (beyond ±60% grouped at the ends)",
                axis=alt.Axis(format="+.0%", values=list(bins)),
                scale=alt.Scale(domain=[-0.6, 0.6]),
            ),
            x2="to:Q",
            y=alt.Y("jobs:Q", title="Jobs"),
            y2=alt.datum(0),
            color=alt.Color(
                "who:N",
                scale=alt.Scale(
                    domain=["BidLens draft", "Engineer's estimate"], range=[NAVY, "#E39B2D"]
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["who", "bin", "jobs"],
        )
    )
    st.altair_chart(chart(shade + bars, height=400), width="stretch")
    how_to_read(
        f"the green band is ±{g:.1%}, the median gap between the second-lowest and the lowest "
        f"bid on these jobs: bidders themselves disagree by about that much, so a miss inside "
        "it is as close as anyone gets. More of BidLens's jobs sit near zero."
    )

within = lambda e: float((e.abs() <= 0.15).mean())  # noqa: E731
st.markdown(
    f"""**In plain numbers.** On {len(h)} jobs, the BidLens draft landed within 15% of the low
bid on **{within(bl):.0%}** of jobs, against **{within(ee):.0%}** for the engineer's estimate. The
median BidLens draft was {100 * bl.median():+.1f}% from the low bid; the median engineer's
estimate was {100 * ee.median():+.1f}%, consistently high. Drafts were priced by Kumo Tabular,
refreshed each quarter on every earlier bid."""
)
bt = stage("22_live_evaluation", "results.json")
if bt:
    hh, cov = bt["headline"], bt["item_range_coverage"]
    st.markdown(
        f"""**The light model on the hosted demo.** The free hosted demo cannot run Kumo, so it
prices with LightGBM, fit live. Run the same way on the same {hh["contracts"]} jobs, it was
closer than the engineer's estimate on {hh["live_closer_than_ee"]:.0%} of jobs (typical miss
{hh["live_median_abs_error"]:.0%}). Its 80% item ranges held the low bidder's price on
{cov.get("model", float("nan")):.0%} of model-priced items and {cov.get("history", float("nan")):.0%}
of history-priced items."""
    )
st.caption(
    "Why 178 jobs: of the 208 jobs bid in 2024 to 2026 with an engineer's estimate, 7 have no "
    "readable item list and 23 have more than 1 in 10 items never bid before, too little history "
    "to price item by item. Details: outputs/13_model_comparison and outputs/22_live_evaluation "
    f"in the repository. Second bid gap from {len(gap)} of these jobs with a second bid."
)
