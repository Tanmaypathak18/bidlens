"""Market: how many bidders to expect and where the low bid should land (step 4.1)."""

from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st
from common import ROOT, header, millions, pct, summary
from design import GREEN, NAVY, SLATE, chart, how_to_read, tile

contract = header("Market")
if contract:
    s = summary(contract)
    mk = s.get("market") or {}
    if not mk:
        st.warning("No market outlook for this package yet.")
        st.stop()
    ee, low = s["engineers_estimate"], s.get("low_bid_cost")
    lo, mid, hi = (ee * (1 + mk[k]) for k in ("spread_low", "spread_kumo", "spread_high"))

    a, b, c = st.columns(3)
    tile(
        a,
        "Expected low bid (whole-job view)",
        millions(mid),
        f"{pct(mk['spread_kumo'])} vs the engineer's estimate",
    )
    tile(
        b,
        "Likely range for the low bid",
        f"{millions(lo)} to {millions(hi)}",
        f"{pct(mk['spread_low'])} to {pct(mk['spread_high'])} vs the estimate",
    )
    tile(
        c,
        "Expected bidders",
        f"{mk['bidders_kumo']:.0f}",
        f"likely {mk['bidders_low']:.0f} to {mk['bidders_high']:.0f}",
    )

    st.write("")
    draft = s["estimate_total"]
    inside = lo <= draft <= hi
    st.markdown(
        f"""**Two ways to estimate the low bid.** They answer the same question from different
evidence, so they rarely match:

- **Item by item, the BidLens draft: {millions(draft)}** (Home and Prices pages). Every bid item
  is priced from earlier low bids for that item, at this job's quantities, and added up.
- **Whole job, this page: {millions(mid)}, likely {millions(lo)} to {millions(hi)}.** It starts
  from the engineer's estimate and applies how far low bids have landed from it on similar
  jobs. It never looks at the bid items.

"""
        + (
            "The item-by-item draft sits inside the whole-job range, so the two views are "
            "consistent. "
            if inside
            else "The item-by-item draft sits outside the whole-job range: check the largest "
            "items on the Prices page before relying on either number. "
        )
        + "Use the draft for pricing and the whole-job view as a cross-check."
        + (f" On this sample job the actual low bid was {millions(low)}." if low else "")
    )
    st.subheader("Where the low bid is likely to land")
    st.markdown(
        "Caltrans' engineer's estimate is the agency's own price for the job. On recent jobs "
        "like this one, low bids have landed well away from it in both directions. BidLens "
        "looks at jobs bid before this one (size, type of work, district, time of year, how "
        "many contractors took out plans, and recent bidding) to say where the low bid should "
        "land."
    )
    band = pd.DataFrame(
        [
            {
                "lo": mk["spread_low"],
                "hi": mk["spread_high"],
                "mid": mk["spread_kumo"],
                "y": "This job",
            }
        ]
    )
    x = alt.X(
        "lo:Q",
        title="Low bid compared with the engineer's estimate (%)",
        axis=alt.Axis(format="+.0%"),
        scale=alt.Scale(domain=[-0.6, 0.6]),
    )
    # A blank row above the band holds the labels, so they are never clipped.
    y = alt.Y("y:N", title=None, scale=alt.Scale(domain=[" ", "This job"]))
    layers = alt.Chart(band).mark_rule(strokeWidth=22, color="#C7D2E0").encode(x=x, x2="hi:Q", y=y)
    layers += (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(color=SLATE, strokeDash=[4, 3])
        .encode(x="x:Q")
    )
    layers += alt.Chart(band).mark_tick(color=NAVY, thickness=4, size=34).encode(x="mid:Q", y=y)
    marks = [
        {"x": mk["spread_kumo"], "t": f"Expected {pct(mk['spread_kumo'])}", "c": NAVY},
    ]
    if low:
        act = low / ee - 1
        layers += (
            alt.Chart(pd.DataFrame({"x": [act], "y": ["This job"]}))
            .mark_point(shape="diamond", size=220, filled=True, color=GREEN)
            .encode(x="x:Q", y=y)
        )
        marks.append({"x": act, "t": f"Actual {pct(act)}", "c": GREEN})
    lab = pd.DataFrame(marks).assign(y=" ")
    layers += (
        alt.Chart(lab)
        .mark_text(fontSize=12, fontWeight="bold", dy=8)
        .encode(x="x:Q", y=y, text="t:N", color=alt.Color("c:N", scale=None))
    )
    layers += (
        alt.Chart(pd.DataFrame({"x": [0], "y": [" "], "t": ["Engineer's estimate"]}))
        .mark_text(fontSize=12, fontWeight="bold", dy=8, dx=6, align="left", color=SLATE)
        .encode(x="x:Q", y=y, text="t:N")
    )
    st.altair_chart(chart(layers, height=150), width="stretch")
    how_to_read(
        "the grey band holds the low bid on about 8 in 10 similar past jobs; the navy tick is the "
        "expected landing point; the dashed line is the engineer's estimate"
        + ("; the green diamond is where the low bid actually landed." if low else ".")
    )

    st.subheader("How many contractors will bid")
    n = pd.DataFrame(
        [
            {
                "lo": mk["bidders_low"],
                "hi": mk["bidders_high"],
                "mid": mk["bidders_kumo"],
                "y": "This job",
            }
        ]
    )
    x = alt.X(
        "lo:Q",
        title="Number of bidders",
        scale=alt.Scale(domain=[0, 14]),
        axis=alt.Axis(tickMinStep=1, format="d"),
    )
    layers = alt.Chart(n).mark_rule(strokeWidth=22, color="#C7D2E0").encode(x=x, x2="hi:Q", y=y)
    layers += alt.Chart(n).mark_tick(color=NAVY, thickness=4, size=34).encode(x="mid:Q", y=y)
    if low:
        layers += (
            alt.Chart(pd.DataFrame({"x": [s["bidders"]], "y": ["This job"]}))
            .mark_point(shape="diamond", size=220, filled=True, color=GREEN)
            .encode(x="x:Q", y=y)
        )
    st.altair_chart(chart(layers, height=90), width="stretch")
    how_to_read(
        "grey band = likely number of bidders (8 in 10 similar jobs); navy tick = expected"
        + (f"; green diamond = the {s['bidders']} who actually bid." if low else ".")
    )
    ph = s.get("plan_holders")
    st.markdown(
        (
            f"**{ph} contractors took out plans** for this job. BidLens uses that count: it is "
            "public before bids open, and it is the best single clue to how many will bid. "
            if ph
            else ""
        )
        + "More bidders usually means a sharper low bid; a thin field leaves more room."
    )
    res = ROOT / "outputs" / "15_market_context" / "results.json"
    if res.exists():
        r = json.loads(res.read_text())
        sp, bd = r["spread"], r["bidders"]
        st.caption(
            f"Track record on {sp['contracts']} past jobs (all jobs bid in 2024 to 2026 with an "
            "engineer's estimate, each predicted only from jobs bid before it; the Home page's "
            "item-by-item record uses 178 of them, those with enough item history): "
            "the expected landing point was off by "
            f"{100 * sp['methods']['kumo']['mae']:.0f} percentage points on average and the "
            f"bidder count by {bd['methods']['kumo']['mae']:.1f} bidders; the ranges held the "
            f"actual result {sp['range_coverage']:.0%} and {bd['range_coverage']:.0%} of the time."
            " Treat these as a guide."
        )
