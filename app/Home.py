"""BidLens home: the bid package at a glance (step 4.1)."""

from __future__ import annotations

import streamlit as st
from common import estimate, findings, header, money, pct, scored, summary

contract = header("Home")
st.title("BidLens")
st.caption("A draft estimate for a Caltrans bid, priced from public bid history.")
if contract:
    s = summary(contract)
    est = estimate(contract)
    mk = s.get("market") or {}
    ee = s["engineers_estimate"]

    st.subheader(f"Contract {contract}")
    st.write(f"**{s['type_of_work']}**")
    st.write(
        f"District {s['district']} · {s['county']} · bids open {s['bid_open_date']} · "
        f"{s['working_days']:,.0f} working days · {s['lines']} bid items"
    )

    a, b, c = st.columns(3)
    a.metric("BidLens draft total", money(s["estimate_total"]))
    b.metric(
        "Engineer's estimate",
        money(ee),
        f"draft is {pct(s['estimate_total'] / ee - 1)} vs the estimate",
        delta_color="off",
    )
    if mk:
        c.metric(
            "Expected bidders",
            f"{mk['bidders_kumo']:.0f}",
            f"likely {mk['bidders_low']:.0f} to {mk['bidders_high']:.0f}",
            delta_color="off",
        )

    if mk:
        lo, mid, hi = (ee * (1 + mk[k]) for k in ("spread_low", "spread_kumo", "spread_high"))
        st.markdown(
            f"**Market context.** Recent bidding suggests the low bid will land about "
            f"**{pct(mk['spread_kumo'])}** from the engineer's estimate (around {money(mid)}), "
            f"likely between {pct(mk['spread_low'])} and {pct(mk['spread_high'])} "
            f"({money(lo)} to {money(hi)})."
        )

    items, run, model = findings(contract)
    f = scored(items)
    st.markdown(
        f"**From the documents.** {len(f)} findings on scope, time, traffic, environmental, "
        f"hazardous materials, site conditions, utilities, bidding, submittals and payment, "
        f"each with its page ({model}). "
        f"{int((items['category'] == 'closure_hours').sum()) if len(items) else 0} closure "
        "charts read into hour tables."
    )
    priced = est["tier"] == 0
    st.markdown(
        f"**Prices.** {int(priced.sum())} items ({s['model_share']:.0%} of the draft total) "
        "are priced by the pricing model with a low to high range and comparable bids; the "
        "rest from earlier bids for the same item."
    )
    st.info(
        "Use the pages on the left in order: **Package** (what the documents require), "
        "**Prices** (each bid item), **Export** (the draft estimate workbook)."
    )

    if s.get("low_bid_cost"):
        with st.expander("Check against the actual bids (this sample's results are public)"):
            low = s["low_bid_cost"]
            st.write(
                f"Actual low bid: **{money(low)}** from {s['bidders']} bidders. "
                f"BidLens draft: {money(s['estimate_total'])} "
                f"({pct(s['estimate_total'] / low - 1)} vs the low bid). "
                f"Engineer's estimate: {money(ee)} ({pct(ee / low - 1)})."
            )
            st.caption(
                "Shown only to check BidLens on a past bid. The draft never uses these results."
            )
