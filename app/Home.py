"""BidLens home: the headline numbers and what to watch (step 4.1, D-064, D-066)."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from common import estimate, findings, header, money, pct, scored, summary, track_record
from design import GREEN, NAVY, SLATE, card, chart, how_to_read, short_doc, tile, top_watch

contract = header("Home")
if contract:
    s = summary(contract)
    est = estimate(contract)
    ee, draft, low = s["engineers_estimate"], s["estimate_total"], s.get("low_bid_cost")

    # --- three tiles
    a, b, c = st.columns(3)
    if low:
        gap, egap = draft / low - 1, ee / low - 1
        tile(
            a,
            "BidLens draft estimate",
            money(draft),
            f"{pct(gap)} vs the actual low bid",
            "good" if abs(gap) <= 0.10 else "watch",
        )
        tile(
            b,
            "Caltrans engineer's estimate",
            money(ee),
            f"{pct(egap)} vs the actual low bid",
            "good" if abs(egap) <= 0.10 else "watch",
        )
        tile(c, "Actual low bid", money(low), f"{s['bidders']} bidders")
    else:
        tile(a, "BidLens draft estimate", money(draft), f"{pct(draft / ee - 1)} vs the estimate")
        tile(b, "Caltrans engineer's estimate", money(ee))
        tile(c, "Actual low bid", "Not bid yet", "Shown here once bids open")

    st.write("")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("The three numbers side by side")
        rows = [("BidLens draft", draft), ("Engineer's estimate", ee)]
        if low:
            rows.append(("Actual low bid", low))
        df = pd.DataFrame(rows, columns=["what", "amount"])
        ref = low or ee
        df["label"] = [
            f"{money(v)}"
            if (low and w == "Actual low bid")
            else f"{money(v)}  ({pct(v / ref - 1)})"
            for w, v in zip(df["what"], df["amount"], strict=True)
        ]
        df["color"] = [NAVY, SLATE, GREEN][: len(df)]
        df["millions"] = df["amount"] / 1e6
        base = alt.Chart(df).encode(
            y=alt.Y(
                "what:N", sort=None, title=None, axis=alt.Axis(labelFontSize=13, labelLimit=200)
            ),
            x=alt.X(
                "millions:Q",
                title="Contract total ($ millions)",
                axis=alt.Axis(format="$,.0f", tickCount=6),
                scale=alt.Scale(domainMax=float(df["millions"].max()) * 1.45),
            ),
        )
        bars = base.mark_bar(cornerRadiusEnd=4).encode(color=alt.Color("color:N", scale=None))
        text = base.mark_text(align="left", dx=6, fontSize=13, color="#1E293B").encode(
            text="label:N"
        )
        st.altair_chart(chart(bars + text, height=180), width="stretch")
        how_to_read(
            "longer bars are higher totals; the percentage is each number's difference from "
            + ("the actual low bid." if low else "the engineer's estimate.")
        )

    with right:
        st.subheader("How BidLens did on past bids")
        tr = track_record()
        if tr:
            st.markdown(
                f"""On **{tr["contracts"]} past Caltrans contracts** (bid 2024 to 2026, each
priced only from bids before it):

- BidLens was **closer to the low bid than the engineer's estimate
  {tr["bidlens_closer_share"]:.0%} of the time**.
- Typical miss: **{tr["bidlens_median_abs_error"]:.0%}** for BidLens, against
  **{tr["ee_median_abs_error"]:.0%}** for the engineer's estimate.
- Within 15% of the low bid on {tr["bidlens_within_15"]:.0%} of jobs, against
  {tr["ee_within_15"]:.0%}."""
            )
        st.caption("Districts 4 and 5. A starting point for the estimator, not a bid.")

    # --- top 5 to watch
    st.subheader("Top 5 things to watch")
    items, run, model = findings(contract)
    f = scored(items)
    watch = top_watch(f)
    if watch.empty:
        st.write("No document findings yet for this package.")
    else:
        for i, r in enumerate(watch.itertuples()):
            sec = f", section {r.section_number}" if r.section_number else ""
            card(contract, r, f"top{i}", f"{r.category_name} · {short_doc(r.document)}{sec}")
        st.caption(
            f"Picked from {len(f)} findings read from the documents on this computer: money at "
            "stake or a hard stop, one per topic. Click a page to see it. Every finding is on "
            "the Package page."
        )

    model_items = int((est["tier"] == 0).sum())
    st.markdown(
        f"<span style='color:{SLATE}'>Prices: {model_items} of {s['lines']} bid items "
        f"({s['model_share']:.0%} of the draft) have a low to high range and comparable past "
        "bids; the rest are priced from earlier bids for the same item. Work through the "
        "pages on the left in order: Package, Prices, Market, Export.</span>",
        unsafe_allow_html=True,
    )
