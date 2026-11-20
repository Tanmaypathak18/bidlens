"""Export: preview the draft estimate workbook, then download it (steps 4.1, 4.2, D-066)."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st
from common import ROOT, header, money, summary
from design import tile

contract = header("Export")
if contract:
    from openpyxl import load_workbook

    from bidlens.export import workbook

    s = summary(contract)

    @st.cache_data(show_spinner="Building the workbook…")
    def build(c: str) -> bytes:
        return workbook(c, root=ROOT)

    data = build(contract)
    wb = load_workbook(io.BytesIO(data))

    def sheet(name: str, header_row: int = 1) -> pd.DataFrame:
        rows = list(wb[name].iter_rows(values_only=True))
        df = pd.DataFrame(rows[header_row:], columns=rows[header_row - 1])
        return df.dropna(how="all")

    ws = wb["Estimate"]
    top = next(r for r in range(1, 30) if ws.cell(row=r, column=1).value == "Item")
    est = sheet("Estimate", top)
    est = est[est["Item"].notna()]
    # Formulas are worked out when the file opens in Excel; show the same results here.
    for k in ("Low", "Likely", "High"):
        est[f"{k} amount"] = pd.to_numeric(est[f"{k} unit price"]) * est["Quantity"]
    risk = sheet("Risk register")
    comps = sheet("Comparables")

    a, b, c = st.columns(3)
    tile(
        a, "Draft total in the workbook", money(est["Likely amount"].sum()), f"{len(est)} bid items"
    )
    tile(b, "Risk register", f"{len(risk)} findings", "each with its document and page")
    tile(c, "Comparable bids", f"{len(comps)} rows", "each linked to its Caltrans page")
    st.write("")
    st.download_button(
        "Download the draft estimate (.xlsx)",
        data=data,
        file_name=f"BidLens_draft_estimate_{contract}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        icon=":material/download:",
    )
    st.caption(
        "Opens in Excel or Numbers. Amounts and totals are live formulas: type your own unit "
        "price in the 'Estimator unit price' column and the estimator total updates. A draft for "
        "review, not a bid."
    )

    st.subheader("Preview")
    t1, t2, t3, t4, t5 = st.tabs(
        ["Estimate", "Comparables", "Risk register", "Closure hours", "About"]
    )
    money_cols = {
        k: st.column_config.NumberColumn(format="$%,.2f")
        for k in ("Low unit price", "Likely unit price", "High unit price")
    } | {
        k: st.column_config.NumberColumn(format="$%,.0f")
        for k in ("Low amount", "Likely amount", "High amount")
    }
    with t1:
        cols = [
            "Item",
            "Description",
            "Unit",
            "Quantity",
            "Low unit price",
            "Likely unit price",
            "High unit price",
            "Likely amount",
            "Priced from",
            "Comparable bids",
        ]
        view = est[cols].copy()
        for k in ("Low unit price", "High unit price"):
            view[k] = ["—" if pd.isna(v) else f"${float(v):,.2f}" for v in pd.to_numeric(view[k])]
        st.dataframe(
            view.drop(columns=["Comparable bids"]),
            hide_index=True,
            width="stretch",
            height=380,
            column_config={
                **money_cols,
                "Low unit price": st.column_config.TextColumn("Low"),
                "Likely unit price": st.column_config.NumberColumn("Likely", format="$%,.2f"),
                "High unit price": st.column_config.TextColumn("High"),
                "Description": st.column_config.TextColumn(width="medium"),
            },
        )
        st.caption(
            f"Plus the package header (engineer's estimate {money(s['engineers_estimate'])}, "
            "market outlook), low and high amounts, and the estimator columns."
        )
    with t2:
        st.dataframe(
            comps.head(200),
            hide_index=True,
            width="stretch",
            height=380,
            column_config={
                "Caltrans source": st.column_config.LinkColumn(display_text="open"),
                "Low bid unit price": st.column_config.NumberColumn(format="$%,.2f"),
                "In bid-date dollars": st.column_config.NumberColumn(format="$%,.2f"),
            },
        )
    with t3:
        st.dataframe(
            risk.drop(columns=["Priced? (estimator)", "Notes (estimator)"]),
            hide_index=True,
            width="stretch",
            height=380,
        )
        st.caption("The workbook adds empty 'Priced?' and 'Notes' columns for the estimator.")
    with t4:
        st.dataframe(sheet("Closure hours"), hide_index=True, width="stretch", height=380)
    with t5:
        for row in wb["About"].iter_rows(values_only=True):
            if row[0]:
                st.markdown(f"- {row[0]}")
