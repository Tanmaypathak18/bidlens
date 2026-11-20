"""Package: what the bid documents require, each finding one click from its page
(step 4.1, D-064, D-066)."""

from __future__ import annotations

import re

import altair as alt
import pandas as pd
import streamlit as st
from common import DOCS, estimate, findings, header, scored, summary
from design import (
    AMBER,
    COLOR,
    GREEN,
    NAVY,
    RED,
    SLATE,
    card,
    chart,
    how_to_read,
    rate,
    short_doc,
    show_page,
    shows_value,
)

GROUPS = [
    ("Schedule and damages", ["time_damages"]),
    ("Traffic", ["traffic"]),
    ("Environmental and hazardous materials", ["environmental", "hazardous"]),
    ("Site conditions and utilities", ["geotechnical", "utilities"]),
    ("Payment", ["payment"]),
    ("Scope", ["scope"]),
]
CHECKLIST = [("Bidding requirements", "bid_requirements"), ("Submittals", "submittals")]
ORDER = {"risk": 0, "watch": 1, "info": 2}

contract = header("Package")
if contract:
    s = summary(contract)
    items, run, model = findings(contract)
    if items.empty:
        st.warning("No document findings for this package yet.")
        st.stop()
    f = rate(scored(items))
    n = f["severity"].value_counts()
    st.markdown(
        f"<b>{len(f)} findings</b> from the special provisions, addenda and information "
        f"handout: <span style='color:{RED}'>● {n.get('risk', 0)} risks</span> (money at stake "
        f"or a hard stop) · <span style='color:{AMBER}'>● {n.get('watch', 0)} to watch</span> "
        f"(limits and deadlines) · <span style='color:{SLATE}'>● {n.get('info', 0)} notes</span>."
        " Click a page number to see the page.",
        unsafe_allow_html=True,
    )

    # --- key dates
    st.subheader("Key dates")
    kd = pd.DataFrame(s.get("key_dates") or [])
    if len(kd):
        kd["when"] = pd.to_datetime(kd["date"])
        kd["kind"] = kd["label"].map(
            lambda x: (
                "Bids open" if x == "Bids open" else ("Meeting" if "meeting" in x else "Document")
            )
        )
        kd["row"] = range(len(kd))
        kd["text"] = kd["label"] + " · " + kd["when"].dt.strftime("%b %-d")
        kd["y"] = [(-1) ** i * (1 + (i // 2) % 2) for i in range(len(kd))]
        colors = alt.Scale(domain=["Document", "Meeting", "Bids open"], range=[SLATE, AMBER, NAVY])
        axis = alt.X(
            "when:T",
            title=None,
            axis=alt.Axis(format="%b %-d", grid=False, tickCount={"interval": "week", "step": 1}),
        )
        y = alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-2.8, 2.8]))
        dots = (
            alt.Chart(kd)
            .mark_circle(size=140)
            .encode(
                x=axis,
                y=y,
                color=alt.Color("kind:N", scale=colors, legend=None),
                tooltip=["label", alt.Tooltip("when:T", format="%a, %b %-d, %Y")],
            )
        )
        labels = (
            alt.Chart(kd)
            .mark_text(dy=-14, fontSize=12, color="#1E293B")
            .encode(x=axis, y=y, text="text:N")
        )
        base = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#94A3B8").encode(y=y)
        kd["zero"] = 0.0
        stems = alt.Chart(kd).mark_rule(color="#CBD5E1").encode(x=axis, y=y, y2="zero:Q")
        st.altair_chart(chart(base + stems + dots + labels, height=200), width="stretch")
        how_to_read("each dot is a dated event in the package, from issue to bid opening.")
        start = f.loc[f["statement"].str.contains(r"Start job site activities within", na=False)]
        wd = s.get("working_days")
        st.markdown(
            f"**Contract time:** {wd:,.0f} working days (roughly {wd / 21:,.0f} months of "
            "working days, before weather and holidays)"
            + (f". {start.iloc[0]['statement']}" if len(start) else ".")
        )

    # --- risk cards by group
    st.subheader("Risks and requirements by topic")
    show = st.segmented_control(
        "Show", ["Risks", "Risks and watch items", "Everything"], default="Risks and watch items"
    )
    keep = {"Risks": {"risk"}, "Risks and watch items": {"risk", "watch"}}.get(
        show, {"risk", "watch", "info"}
    )
    tabs = st.tabs([g for g, _ in GROUPS])
    for (_, cats), tab in zip(GROUPS, tabs, strict=True):
        with tab:
            g = f[f["category"].isin(cats) & f["severity"].isin(keep)]
            g = g.sort_values(by="severity", key=lambda x: x.map(ORDER), kind="stable")
            if g.empty:
                st.write("Nothing at this level for this topic.")
            for r in g.itertuples():
                sec = f", section {r.section_number}" if r.section_number else ""
                card(
                    contract, r, f"c{r.Index}", f"{r.category_name} · {short_doc(r.document)}{sec}"
                )

    # --- checklists
    st.subheader("Requirements and submittals checklist")
    st.caption("Tick items off as you plan for them. Ticks are kept while this page is open.")
    cols = st.columns(2, gap="large")
    for (title, cat), col in zip(CHECKLIST, cols, strict=True):
        with col:
            st.markdown(f"**{title}**")
            for r in f[f["category"] == cat].itertuples():
                c0, c1, c2 = st.columns([0.7, 10, 2.6], vertical_alignment="top")
                c0.checkbox(r.statement, key=f"chk{r.Index}", label_visibility="collapsed")
                extra = f" ({r.value})" if shows_value(r.statement, r.value) else ""
                c1.markdown(r.statement + extra)
                if c2.button(f"p. {r.page}", key=f"chkp{r.Index}", help="Open this page"):
                    show_page(contract, r.file, int(r.page), r.evidence, short_doc(r.document))

    # --- closure hours
    st.subheader("When lanes and ramps may be closed")
    cp = DOCS / contract / "charts.parquet"
    if cp.exists():
        charts = pd.read_parquet(cp)
        charts["name"] = (
            charts["chart"]
            + " · "
            + charts["county"]
            + " "
            + charts["route"]
            + " · "
            + charts["limits"].str.slice(0, 60)
        )
        pick = st.selectbox("Closure chart", charts["name"], index=0)
        c = charts[charts["name"] == pick].iloc[0]
        legend = dict(x.split(" = ", 1) for x in c["legend"].split("; ") if " = " in x)
        rows = []
        for part in c["grid"].split("; "):
            day, _, cells = part.partition(": ")
            got = {int(x[:2]): x[2:] for x in cells.split()}
            for h in range(24):
                code = got.get(h)
                rows.append(
                    {
                        "day": day,
                        "hour": h,
                        "code": code or "",
                        "what": legend.get(code, "No closure") if code else "No closure",
                    }
                )
        g = pd.DataFrame(rows)

        def simple(w: str) -> str:
            if w == "No closure":
                return "No closure"
            if w.lower().startswith("shoulder"):
                return "Shoulder only"
            m = re.search(r"at least (\d+)", w)
            if "closed completely" in w:
                return "Full closure allowed"
            return f"Lane closure, keep {m.group(1)} open" if m else w

        g["what"] = g["what"].map(simple)
        dom = sorted(g["what"].unique(), key=lambda x: (x == "No closure", x))
        pal = {"Full closure allowed": GREEN, "Shoulder only": "#A5D6A7", "No closure": "#EEF2F7"}
        greens = ["#2E7D32", "#43A047", "#66BB6A", "#81C784"]
        rng = [pal.get(d) or greens[i % 4] for i, d in enumerate(dom)]
        days = list(dict.fromkeys(g["day"]))
        g["d0"] = g["day"].map({d: i for i, d in enumerate(days)})
        g["d1"], g["h1"] = g["d0"] + 0.9, g["hour"] + 0.94
        label_expr = " : ".join(f"datum.value == {i + 0.45} ? '{d}'" for i, d in enumerate(days))
        heat = (
            alt.Chart(g)
            .mark_rect(cornerRadius=2)
            .encode(
                x=alt.X(
                    "hour:Q",
                    title="Hour of day (0 = midnight)",
                    scale=alt.Scale(domain=[0, 24], nice=False),
                    axis=alt.Axis(values=list(range(0, 25, 2)), grid=False),
                ),
                x2="h1:Q",
                y=alt.Y(
                    "d0:Q",
                    title=None,
                    scale=alt.Scale(domain=[len(days), 0], nice=False),
                    axis=alt.Axis(
                        values=[i + 0.45 for i in range(len(days))],
                        labelExpr=label_expr + " : ''",
                        grid=False,
                        ticks=False,
                        domain=False,
                    ),
                ),
                y2="d1:Q",
                color=alt.Color(
                    "what:N",
                    scale=alt.Scale(domain=dom, range=rng),
                    legend=alt.Legend(title=None, orient="top", direction="horizontal"),
                ),
                tooltip=["day", "hour", "what"],
            )
        )
        st.altair_chart(chart(heat, height=300), width="stretch")
        how_to_read(
            "green hours are when this closure is allowed; grey hours allow work only where no "
            f"closure is needed. Chart {c['chart']}, special provisions page {c['page']}."
        )
        if st.button(f"p. {c['page']}", key="chartpage", help="Open the chart's page"):
            show_page(
                contract, c["file"], int(c["page"]), f"Chart No. {c['chart']}", "Special Provisions"
            )
        dm = items[items["category"] == "closure_damages"]
        if len(dm):
            with st.expander(f"Damages for reopening a closure late ({len(dm)} routes)"):
                for r in dm.itertuples():
                    st.markdown(
                        f"- {r.statement} <span style='color:{SLATE}'>(p. {r.page})</span>",
                        unsafe_allow_html=True,
                    )

    est = estimate(contract)
    ch = est[est["changed_by"].fillna("") != ""]
    if len(ch):
        with st.expander(f"Bid items changed by addenda ({len(ch)})"):
            st.dataframe(
                ch[
                    ["item_no", "item_code", "description", "unit", "quantity", "changed_by"]
                ].rename(
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
    _ = COLOR
