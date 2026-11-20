"""Prices: every bid item by dollar impact, its range, comparable bids and price history
(step 4.1, D-064, D-066)."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from common import comparables, estimate, header, history, money, pct, short_money, summary
from design import AMBER, GREEN, NAVY, SLATE, chart, how_to_read, tile

contract = header("Prices")
if contract:
    s = summary(contract)
    est = estimate(contract).copy()
    comps, hist = comparables(contract), history(contract)
    total = est["pred_amount"].sum()
    est["share"] = est["pred_amount"] / total
    est = est.sort_values("pred_amount", ascending=False).reset_index(drop=True)
    est["qty"] = est["quantity"].map(lambda q: "1" if pd.isna(q) else f"{q:,.10g}")
    est["label"] = est["item_no"] + " " + est["description"].str.slice(0, 38)

    a, b, c = st.columns(3)
    tile(a, "Draft total (likely prices)", money(total), f"{len(est)} bid items")
    top10 = est.head(10)["share"].sum()
    tile(b, "Top 10 items", f"{top10:.0%} of the total", "check these prices first", "watch")
    tile(
        c,
        "Items with a price range",
        f"{int((est['tier'] == 0).sum())}",
        f"{s['model_share']:.0%} of the draft total",
    )

    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Where the money is")
        t = est.head(10).assign(pct_label=lambda d: d["share"].map(lambda x: f"{x:.1%}"))
        enc = alt.Chart(t).encode(
            y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X(
                "share:Q",
                title="Share of the draft total (%)",
                axis=alt.Axis(format=".0%"),
                scale=alt.Scale(domainMax=float(t["share"].max()) * 1.25),
            ),
        )
        bars = enc.mark_bar(color=NAVY, cornerRadiusEnd=3)
        txt = enc.mark_text(align="left", dx=4, color="#1E293B").encode(text="pct_label:N")
        st.altair_chart(chart(bars + txt, height=300), width="stretch")
        how_to_read(
            f"the 10 largest items make up {top10:.0%} of the draft; get these right first."
        )
    with right:
        st.subheader("How sure each price is")
        r = est[est["tier"] == 0].head(10).copy()
        r["lo"] = r["low"] / r["pred_unit_price"]
        r["hi"] = r["high"] / r["pred_unit_price"]
        r["mid"] = 1.0
        x = alt.X(
            "lo:Q",
            title="Price ÷ likely price (log scale)",
            scale=alt.Scale(type="log", domain=[0.1, 10]),
            axis=alt.Axis(values=[0.1, 0.25, 0.5, 1, 2, 4, 10], format="~g"),
        )
        y = alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260))
        rng = alt.Chart(r).mark_rule(strokeWidth=7, color="#C7D2E0").encode(x=x, x2="hi:Q", y=y)
        dot = (
            alt.Chart(r)
            .mark_tick(color=NAVY, thickness=3, size=16)
            .encode(
                x="mid:Q",
                y=y,
                tooltip=[
                    alt.Tooltip("description:N", title="Item"),
                    alt.Tooltip("low:Q", format="$,.2f", title="Low"),
                    alt.Tooltip("pred_unit_price:Q", format="$,.2f", title="Likely"),
                    alt.Tooltip("high:Q", format="$,.2f", title="High"),
                ],
            )
        )
        st.altair_chart(chart(rng + dot, height=300), width="stretch")
        how_to_read(
            "for the 10 largest items with a range: the grey bar runs from low to high (8 in 10 "
            "past low bids fall inside), the tick is the likely price. Wider means less certain."
        )

    st.subheader("All bid items, largest first")
    st.caption("Select a row to see its range, comparable past bids and price history.")
    table = pd.DataFrame(
        {
            "Item": est["item_no"],
            "Description": est["description"],
            "Unit": est["unit"],
            "Quantity": est["qty"],
            "Likely": est["pred_unit_price"],
            "Range": [
                "—" if pd.isna(lo) else f"{short_money(lo)} to {short_money(hi)}"
                for lo, hi in zip(est["low"], est["high"], strict=True)
            ],
            "Amount": est["pred_amount"],
            "Share": est["share"] * 100,
            "Priced from": est["source"],
        }
    )
    pick = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=360,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Range": st.column_config.TextColumn("Low to high ($/unit)"),
            "Likely": st.column_config.NumberColumn("Likely ($/unit)", format="$%,.2f"),
            "Amount": st.column_config.NumberColumn("Amount ($)", format="$%,.0f"),
            "Share": st.column_config.ProgressColumn(
                "Share of total",
                format="%.1f%%",
                min_value=0,
                max_value=float(table["Share"].max()),
            ),
            "Description": st.column_config.TextColumn(width="large"),
        },
    )
    rows = pick.selection.rows if pick and pick.selection else []
    # Without a selection, show the largest item that has a range and comparables.
    first = int(est.index[est["tier"] == 0][0]) if (est["tier"] == 0).any() else 0
    r = est.iloc[rows[0] if rows else first]
    st.subheader(f"Item {r['item_no']} · {r['description']}")
    hint = (
        ""
        if rows
        else f" <span style='color:{SLATE}'>(Showing the largest item with a range; select a row "
        "above to change it.)</span>"
    )
    src = r["source"][0].lower() + r["source"][1:]
    st.markdown(
        f"{r['item_code']} · {r['qty']} {r['unit']} · likely "
        f"**{money(r['pred_unit_price'], True)}** per {r['unit']} = **{money(r['pred_amount'])}** "
        f"({r['share']:.1%} of the draft). Priced from: {src}.{hint}",
        unsafe_allow_html=True,
    )
    c = comps[comps["item_no"] == r["item_no"]] if len(comps) else comps
    h = hist[hist["item_no"] == r["item_no"]] if len(hist) else hist
    on = pd.Timestamp(s["bid_open_date"])

    if pd.notna(r["low"]):
        band = pd.DataFrame(
            {"low": [r["low"]], "high": [r["high"]], "likely": [r["pred_unit_price"]]}
        )
        x = alt.X(
            "low:Q",
            title=f"Unit price ($ per {r['unit']}, bid-date dollars)",
            axis=alt.Axis(format="$,.0f"),
        )
        layers = alt.Chart(band).mark_rule(strokeWidth=14, color="#C7D2E0").encode(x=x, x2="high:Q")
        layers += alt.Chart(band).mark_tick(color=NAVY, thickness=3, size=30).encode(x="likely:Q")
        if len(c):
            layers += (
                alt.Chart(c)
                .mark_circle(color=AMBER, size=60, opacity=0.8)
                .encode(
                    x=alt.X("unit_price_in_query_dollars:Q"),
                    tooltip=[
                        alt.Tooltip("contract_number:N", title="Contract"),
                        alt.Tooltip("unit_price_in_query_dollars:Q", format="$,.2f", title="Price"),
                    ],
                )
            )
        st.altair_chart(chart(layers, height=80), width="stretch")
        how_to_read(
            f"grey bar = range {money(r['low'], True)} to {money(r['high'], True)}; navy tick = "
            "likely price; amber dots = the comparable past bids below, in bid-date dollars."
        )

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**Price history**")
        if h.empty:
            st.write(
                "This is a contract-specific item (its code starts with 01 to 04), so it has no "
                "price history of its own; it is priced from earlier items with the same "
                "description."
                if str(r["item_code"])[:2] in ("01", "02", "03", "04")
                else "No earlier low bids for this exact item."
            )
        else:
            h = h.assign(when=pd.to_datetime(h["bid_open_date"]))
            p = h["unit_price_in_bid_dollars"]
            log = p.max() / max(p.min(), 0.01) > 30
            y = alt.Y(
                "unit_price_in_bid_dollars:Q",
                title=f"Low bid ($ per {r['unit']}, bid-date dollars)",
                scale=alt.Scale(type="log" if log else "linear"),
                axis=alt.Axis(format="$,.0f"),
            )
            pts = (
                alt.Chart(h)
                .mark_circle(color=SLATE, opacity=0.45, size=30)
                .encode(
                    x=alt.X("when:T", title="Bid date"),
                    y=y,
                    tooltip=[
                        alt.Tooltip("when:T", title="Bid date"),
                        alt.Tooltip("unit_price_in_bid_dollars:Q", format="$,.2f", title="Price"),
                        alt.Tooltip("quantity:Q", format=",.0f", title="Quantity"),
                    ],
                )
            )
            now = pd.DataFrame(
                {
                    "when": [on],
                    "unit_price_in_bid_dollars": [r["pred_unit_price"]],
                    "lo": [r["low"]],
                    "hi": [r["high"]],
                }
            )
            layers = pts + alt.Chart(now).mark_point(
                shape="diamond", size=180, filled=True, color=NAVY
            ).encode(x="when:T", y="unit_price_in_bid_dollars:Q")
            if pd.notna(r["low"]):
                layers += (
                    alt.Chart(now)
                    .mark_rule(color=NAVY, strokeWidth=2)
                    .encode(x="when:T", y="lo:Q", y2="hi:Q")
                )
            st.altair_chart(chart(layers, height=260), width="stretch")
            how_to_read(
                f"grey dots are {len(h)} earlier low bids for this item, in bid-date dollars; the "
                "navy diamond is BidLens's likely price on this bid date"
                + (", with its range as a line." if pd.notna(r["low"]) else ".")
            )
    with right:
        st.markdown("**Comparable past bids**")
        if c.empty:
            st.write("No earlier low bids for this exact item and unit.")
        else:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Contract": c["contract_number"],
                        "Date": pd.to_datetime(c["bid_open_date"]).dt.strftime("%b %Y"),
                        "Qty": c["quantity"],
                        "Price (bid-date $)": c["unit_price_in_query_dollars"],
                        "Source": c["source"],
                    }
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "Qty": st.column_config.NumberColumn(format="%,.0f"),
                    "Price (bid-date $)": st.column_config.NumberColumn(format="$%,.0f"),
                    "Source": st.column_config.LinkColumn(display_text="Caltrans"),
                },
            )
            st.caption(
                "The 10 closest earlier low bids: similar quantity, recent, same district and "
                "similar job size count as closer. Prices are brought to the bid date with the "
                "Caltrans cost index."
            )

    if s.get("low_bid_cost"):
        with st.expander("Check against the actual low bid (this sample's results are public)"):
            chk = est.dropna(subset=["low_bid_amount"])
            inside = chk.dropna(subset=["low"])
            ok = (inside["low_bid_unit_price"] >= inside["low"]) & (
                inside["low_bid_unit_price"] <= inside["high"]
            )
            gap = s["estimate_total"] / s["low_bid_cost"] - 1
            col = GREEN if abs(gap) <= 0.10 else AMBER
            st.markdown(
                f"Low bid {money(s['low_bid_cost'])}; BidLens draft {money(s['estimate_total'])} "
                f"(<span style='color:{col}'><b>{pct(gap)}</b></span>). The low bidder's price "
                f"fell inside the BidLens range on **{ok.mean():.0%}** of the {len(inside)} items "
                "with a range.",
                unsafe_allow_html=True,
            )
            st.caption("Shown only to check BidLens on a past bid; never used in the draft.")
