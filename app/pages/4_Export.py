"""Export: the draft estimate workbook (steps 4.1 and 4.2)."""

from __future__ import annotations

import streamlit as st
from common import ROOT, header

contract = header("Export")
st.title("Export")
if contract:
    from bidlens.export import workbook

    st.write(
        "Download the draft estimate as an Excel workbook: bid items with quantity, unit, "
        "low / likely / high unit prices and amounts as live formulas, the comparable bids "
        "behind each price, and a risk register of the document findings with their pages."
    )
    data = workbook(contract, root=ROOT)
    st.download_button(
        "Download draft estimate (.xlsx)",
        data=data,
        file_name=f"BidLens_draft_estimate_{contract}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.caption("A draft for an estimator to review, not a bid.")
