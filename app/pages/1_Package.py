"""Package: what the bid documents require, with the page for every finding (step 4.1)."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from common import TOPIC_ORDER, cite, estimate, findings, header, scored

contract = header("Package")
st.title("Package")
if contract:
    items, run, model = findings(contract)
    if items.empty:
        st.warning("No document extraction for this package yet.")
        st.stop()
    st.caption(
        f"Read by {model}. Every finding quotes the document and gives its page; BidLens "
        "checks that each quote really is on that page. Review the page before you rely "
        "on a finding."
    )
    f = scored(items)
    names = f.drop_duplicates("category").set_index("category")["category_name"].to_dict()
    tabs = st.tabs(
        [names.get(t, t) for t in TOPIC_ORDER if t in names]
        + ["Closure hours", "Late closure damages", "Addendum changes"]
    )
    i = 0
    for t in TOPIC_ORDER:
        if t not in names:
            continue
        with tabs[i]:
            for r in f[f["category"] == t].itertuples():
                value = f" **{r.value}**" if r.value else ""
                st.markdown(f"- {r.statement}{value}")
                st.caption(f"{cite(r)} · “{r.evidence}”")
        i += 1

    with tabs[i]:
        ch = items[items["category"] == "closure_hours"]
        st.caption(
            "Hours when each lane, ramp or connector closure is allowed, read from the "
            "closure charts in the special provisions (hour columns rebuilt from the page "
            "layout). Outside these hours, work only where no closure is needed."
        )
        q = st.text_input("Filter (route, ramp, location or chart number)", "")
        for r in ch.itertuples():
            if q and q.lower() not in r.statement.lower():
                continue
            title, *days = r.statement.split("\n")
            with st.expander(title.split(":")[0] + ": " + title.split(":", 1)[1][:90]):
                st.markdown(title)
                for d in days:
                    st.markdown(f"- {d}")
                st.caption(cite(r))
    with tabs[i + 1]:
        dm = items[items["category"] == "closure_damages"]
        st.caption(
            "Liquidated damages for each 10 minutes a closure is reopened late, by facility "
            "and direction (read from the special provisions table)."
        )
        st.dataframe(
            pd.DataFrame(
                {"Late reopening": dm["statement"], "Source": [cite(r) for r in dm.itertuples()]}
            ),
            hide_index=True,
            width="stretch",
        )
    with tabs[i + 2]:
        est = estimate(contract)
        ch = est[est["changed_by"].fillna("") != ""]
        st.caption("Bid items the addenda added or changed (from the bid item list).")
        st.dataframe(
            ch[["item_no", "item_code", "description", "unit", "quantity", "changed_by"]].rename(
                columns={
                    "item_no": "Item",
                    "item_code": "Code",
                    "description": "Description",
                    "unit": "Unit",
                    "quantity": "Quantity",
                    "changed_by": "Changed by",
                }
            ),
            hide_index=True,
            width="stretch",
        )
