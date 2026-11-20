"""Prices: every bid item with its low / likely / high price and comparable bids (step 4.1)."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from common import comparables, estimate, header, money, pct, summary

contract = header("Prices")
st.title("Prices")
if contract:
    s = summary(contract)
    est = estimate(contract)
    comps = comparables(contract)
    mk = s.get("market") or {}

    st.caption(
        "Unit prices in bid-date dollars. **Likely** is the price BidLens expects from the "
        "low bidder; **low** and **high** bracket 8 in 10 past low bids for items priced by "
        "the pricing model. Other items are priced from earlier bids and show their source."
    )
    a, b, c = st.columns(3)
    a.metric("Draft total (likely prices)", money(s["estimate_total"]))
    b.metric("Engineer's estimate", money(s["engineers_estimate"]))
    if mk:
        c.metric(
            "Expected low bid vs estimate",
            pct(mk["spread_kumo"]),
            f"likely {pct(mk['spread_low'])} to {pct(mk['spread_high'])}",
            delta_color="off",
        )

    view = est.assign(
        qty=est["quantity"].map(lambda q: "LS" if pd.isna(q) or q == 1 else f"{q:,.10g}"),
    )
    only_model = st.toggle("Only items with a modeled range", False)
    if only_model:
        view = view[view["tier"] == 0]
    table = pd.DataFrame(
        {
            "Item": view["item_no"],
            "Code": view["item_code"],
            "Description": view["description"],
            "Unit": view["unit"],
            "Quantity": view["qty"],
            "Low": view["low"],
            "Likely": view["pred_unit_price"],
            "High": view["high"],
            "Amount (likely)": view["pred_amount"],
            "Share of total": view["pred_amount"] / est["pred_amount"].sum(),
            "Priced from": view["source"],
        }
    )
    pick = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Low": st.column_config.NumberColumn(format="$%,.2f"),
            "Likely": st.column_config.NumberColumn(format="$%,.2f"),
            "High": st.column_config.NumberColumn(format="$%,.2f"),
            "Amount (likely)": st.column_config.NumberColumn(format="$%,.0f"),
            "Share of total": st.column_config.ProgressColumn(format="%.1f%%", max_value=1),
        },
    )
    rows = pick.selection.rows if pick and pick.selection else []
    st.subheader("Comparable bids")
    if not rows:
        st.write("Select a bid item above to see the earlier low bids it is compared with.")
    else:
        r = view.iloc[rows[0]]
        st.markdown(
            f"**Item {r['item_no']} · {r['description']}** ({r['item_code']}, {r['qty']} "
            f"{r['unit']}): likely {money(r['pred_unit_price'], True)}"
            + (
                f", range {money(r['low'], True)} to {money(r['high'], True)}"
                if pd.notna(r["low"])
                else ""
            )
            + f". Priced from: {r['source'].lower()}."
        )
        c = comps[comps["item_no"] == r["item_no"]] if len(comps) else comps
        if c.empty:
            st.write("No earlier low bids for this exact item and unit.")
        else:
            st.dataframe(
                pd.DataFrame(
                    {
                        "Contract": c["contract_number"],
                        "Bid date": pd.to_datetime(c["bid_open_date"]).dt.date,
                        "District": c["district"],
                        "Quantity": c["quantity"],
                        "Low bid unit price": c["unit_price"],
                        "In today's dollars": c["unit_price_in_query_dollars"],
                        "Caltrans page": c["source"],
                    }
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "Low bid unit price": st.column_config.NumberColumn(format="$%,.2f"),
                    "In today's dollars": st.column_config.NumberColumn(format="$%,.2f"),
                    "Caltrans page": st.column_config.LinkColumn(display_text="open"),
                },
            )
            st.caption(
                "The 10 closest earlier low bids for this item: similar quantity, recent, same "
                "district and similar contract size count as closer. Prices are brought to the "
                "bid date with the Caltrans construction cost index."
            )

    if s.get("low_bid_cost"):
        with st.expander("Check against the actual low bid (this sample's results are public)"):
            chk = est.dropna(subset=["low_bid_amount"])
            inside = chk.dropna(subset=["low"])
            ok = (inside["low_bid_unit_price"] >= inside["low"]) & (
                inside["low_bid_unit_price"] <= inside["high"]
            )
            gap = pct(s["estimate_total"] / s["low_bid_cost"] - 1)
            st.write(
                f"Low bid total {money(s['low_bid_cost'])}; BidLens draft "
                f"{money(s['estimate_total'])} ({gap}). "
                f"The low bidder's unit price fell inside the BidLens range on "
                f"{ok.mean():.0%} of the {len(inside)} modeled items."
            )
            st.dataframe(
                pd.DataFrame(
                    {
                        "Item": chk["item_no"],
                        "Description": chk["description"],
                        "BidLens likely": chk["pred_unit_price"],
                        "Low bid": chk["low_bid_unit_price"],
                        "Difference": chk["pred_unit_price"] / chk["low_bid_unit_price"] - 1,
                    }
                ),
                hide_index=True,
                width="stretch",
                column_config={
                    "BidLens likely": st.column_config.NumberColumn(format="$%,.2f"),
                    "Low bid": st.column_config.NumberColumn(format="$%,.2f"),
                    "Difference": st.column_config.NumberColumn(format="percent"),
                },
            )
            st.caption("Shown only to check BidLens on a past bid; never used in the draft.")
