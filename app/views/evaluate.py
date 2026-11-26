"""Evaluate: price a past Caltrans job or an uploaded bid item list, live, step by step."""

from __future__ import annotations

import html
import time
from datetime import date

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from common import (
    ROOT,
    engine,
    findings,
    millions,
    money,
    pct,
    scored,
    short_money,
    sidebar_links,
    stage,
    test_contracts,
)
from design import (
    AMBER,
    COUNTIES,
    GREEN,
    NAVY,
    RED,
    SLATE,
    chart,
    counties,
    hosted,
    how_to_read,
    nice_date,
    rate,
    setup,
    tile,
    top_watch,
)

from bidlens.live.engine import WORK_LABELS, UploadError, read_upload, upload_job

setup("Evaluate")
sidebar_links()

STATUS_COLOR = {"below": "#2563EB", "inside": GREEN, "above": RED}
STATUS_TEXT = {"below": "Below the range", "inside": "Inside the range", "above": "Above the range"}
SAMPLE_JOB = "04-0W0504"
EXAMPLE = ROOT / "data" / "sample" / "example_bid_items.csv"
# Ten jobs to try without knowing a contract number: one or two per kind of work, both
# districts, $0.5M to $23M. Picked for variety, not for good results: on two of them the
# engineer's estimate lands closer to the low bid than BidLens does.
EXAMPLES = {
    "04-0W0504": "Trash capture, guardrail, lighting · Alameda and Contra Costa · $22.7M",
    "04-1W7104": "Pavement repair and drainage · Alameda · $3.6M",
    "05-1Q1604": "Bridge repair · Monterey · $14.7M",
    "05-1J8904": "Culverts and pump plants · Monterey · $18.5M",
    "05-1H6104": "Shoulders, rumble strips, guardrail · Santa Barbara · $19.2M",
    "04-2K3604": "Slope repair and soil nail wall · Sonoma · $6.6M",
    "04-4AC404": "Warning signs · Sonoma · $2.2M",
    "04-2Y5604": "Concrete slab replacement · San Mateo · $1.0M",
    "05-1R4404": "Sidewalk, curb ramps, signals · San Luis Obispo · $1.4M",
    "04-3G9014": "Planting upkeep and erosion control · Sonoma · $0.5M",
}

badge = (
    "Hosted demo · public Caltrans data"
    if hosted()
    else "Runs locally · uploads never leave this computer"
)
st.markdown(
    f"""<div class="bl-head"><h1>Evaluate a bid</h1>
<div class="bl-sub">Pick a past Caltrans job or upload your own bid item list. BidLens prices
every item from earlier Caltrans low bids, live, and shows each step as it runs.
<span class="bl-badge">{badge}</span></div></div>""",
    unsafe_allow_html=True,
)

eng = engine()


def label(row) -> str:
    return f"{row.item_no} {str(row.description)[:40]}"


def short_model(kind: str | None = None) -> str:
    return "Kumo Tabular" if (kind or eng.model_kind) == "kumo" else "LightGBM"


# ----------------------------------------------------------------- what to evaluate

source = st.radio(
    "What to evaluate",
    ["A past Caltrans job (bid 2024 to 2026)", "My own bid item list"],
    horizontal=True,
    key="source",
)
spec = None
if source.startswith("A past"):
    tc = test_contracts()
    examples = [c for c in EXAMPLES if c in set(tc["contract_number"])]

    def use_example() -> None:
        code = st.session_state.get("example")
        if code:
            st.session_state.update(job_q=code, job_district="All", job_county=[], job_work=[])

    st.pills(
        "Don't know a contract number? Try one of these jobs (amounts are the engineer's estimate)",
        examples,
        format_func=lambda c: f"{c} · {EXAMPLES[c]}",
        key="example",
        on_change=use_example,
    )
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    q = c1.text_input("Contract number", placeholder="for example 04-0W0504", key="job_q")
    dist = c2.selectbox("District", ["All", "04", "05"], key="job_district")
    names = sorted({c for v in tc["county"].dropna() for c in v.split(",")})
    cty = c3.multiselect(
        "County", names, format_func=lambda c: COUNTIES.get(c, c), key="job_county"
    )
    wt = c4.multiselect("Work type", list(WORK_LABELS.values()), key="job_work")
    f = tc
    if q.strip():
        f = f[f["contract_number"].str.contains(q.strip().upper(), regex=False)]
    if dist != "All":
        f = f[f["district"] == dist]
    if cty:
        f = f[f["county"].fillna("").map(lambda v: any(c in v.split(",") for c in cty))]
    for w in wt:
        f = f[f["work_types"].str.contains(w, regex=False)]
    if f.empty:
        st.warning("No job matches. Clear a filter to see more.")
    else:
        opts = list(range(len(f)))
        first = f["contract_number"].tolist()
        default = first.index(SAMPLE_JOB) if SAMPLE_JOB in first else 0

        def fmt(i: int) -> str:
            r = f.iloc[i]
            ee = f" · EE {millions(r['engineers_estimate'])}" if r["engineers_estimate"] > 0 else ""
            work = f" · {r['work_types']}" if r["work_types"] else ""
            return (
                f"{r['contract_number']} · bid {r['bid_open_date']:%b %-d, %Y} · "
                f"{r['county']}{ee} · {r['items']} items{work}"
            )

        pick = st.selectbox(
            "1 job matches" if len(f) == 1 else f"{len(f)} jobs match",
            opts,
            index=default,
            format_func=fmt,
        )
        r = f.iloc[pick]
        spec = ("contract", r["contract_number"], r["bid_open_date"])
        st.caption(
            "Bids for these jobs have opened, so BidLens prices them only from bids opened "
            "before the job's quarter, then checks its draft against the real results."
        )
else:
    left, right = st.columns([3, 2], gap="large")
    with left:
        up = st.file_uploader(
            "Bid item list (CSV or Excel, up to 1,000 rows)", type=["csv", "xlsx"]
        )
    with right:
        st.markdown(
            "**Columns:** item code, description, unit, quantity, and optionally your unit "
            'price. Names are matched loosely ("Item No", "Qty", "Unit Price" work). '
            "Leave quantity blank for lump sum items."
        )
        if EXAMPLE.exists():
            st.download_button(
                "Download an example file",
                EXAMPLE.read_bytes(),
                file_name="example_bid_items.csv",
                mime="text/csv",
            )
    with st.expander("Job details (optional; they sharpen the prices and the market view)"):
        a, b, c = st.columns(3)
        bid_date = a.date_input("Bid date", value=date.today())
        district = b.selectbox(
            "Caltrans district", ["04", "05"], help="Bay Area = 04, Central Coast = 05"
        )
        county = c.selectbox(
            "County", [""] + sorted(COUNTIES), format_func=lambda k: COUNTIES.get(k, "Not given")
        )
        d, e = st.columns(2)
        ee = d.number_input("Engineer's estimate ($)", min_value=0.0, step=100000.0, value=0.0)
        wd = e.number_input("Working days", min_value=0, step=10, value=0)
        work = st.text_input("Work description", placeholder="for example: COLD PLANE AND OVERLAY")
    if up is not None:
        try:
            df = read_upload(up.name, up.getvalue())
            info = {
                "bid_date": bid_date,
                "district": district,
                "county": county or None,
                "engineers_estimate": ee or None,
                "working_days": wd or None,
                "type_of_work": work.upper(),
                "label": up.name,
            }
            job = upload_job(eng, df, info)
            spec = ("upload", job)
            has = "your_unit_price" in df and df["your_unit_price"].notna().any()
            st.success(
                f"Read {len(df)} items from {up.name}"
                + (" with your unit prices: BidLens will check them." if has else ".")
            )
        except UploadError as err:
            st.error(str(err))
    if eng.model_kind == "kumo":
        st.caption(
            "Your list is priced live by Kumo Tabular, the model behind the track record"
            + (
                ": on this free hosted CPU that takes about 1 to 3 minutes."
                if hosted()
                else " (about 15 seconds on this computer)."
            )
        )
    else:
        st.caption(
            "Your list is priced by LightGBM, the lighter online model (Kumo Tabular is not "
            "installed here), in a few seconds."
        )

go = st.button("Evaluate", type="primary", disabled=spec is None)
dash = st.container()


# ----------------------------------------------------------------- the five steps


def show_items(res: dict) -> None:
    items = res["items"]
    a, b, c = st.columns(3)
    tile(a, "Bid items", f"{len(items)}", f"{int(items['special'].sum())} special (one-job) items")
    tile(b, "Top-100 items", f"{int(items['in_scope'].sum())}", "priced by the pricing model")
    tile(c, "Earlier low bids", f"{items.attrs['earlier_bids']:,}", "all opened before this job")
    fam = items["item_family"].fillna("Special or unlisted").value_counts().head(8).reset_index()
    fam.columns = ["family", "items"]
    bars = (
        alt.Chart(fam)
        .mark_bar(color=SLATE, cornerRadiusEnd=3)
        .encode(
            y=alt.Y("family:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("items:Q", title="Number of bid items"),
            tooltip=["family", "items"],
        )
    )
    st.altair_chart(chart(bars, height=200), width="stretch")
    how_to_read("the kinds of work on this item list, by number of items.")


def top_items_chart(est: pd.DataFrame, height: int = 300) -> None:
    t = est.nlargest(10, "pred_amount").copy()
    t["label"] = [label(r) for r in t.itertuples()]
    t["text"] = t["pred_amount"].map(short_money)
    t["priced"] = np.where(t["tier"] == 0, "Model", "Earlier bids")
    enc = alt.Chart(t).encode(
        y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X(
            "pred_amount:Q",
            title="Likely amount ($)",
            axis=alt.Axis(format="$~s"),
            scale=alt.Scale(domainMax=float(t["pred_amount"].max()) * 1.25),
        ),
    )
    bars = enc.mark_bar(cornerRadiusEnd=3).encode(
        color=alt.Color(
            "priced:N",
            scale=alt.Scale(domain=["Model", "Earlier bids"], range=[NAVY, "#94A3B8"]),
            legend=alt.Legend(orient="top", title=None),
        ),
        tooltip=["item_no", "description", alt.Tooltip("pred_amount:Q", format="$,.0f"), "source"],
    )
    txt = enc.mark_text(align="left", dx=4, color="#1E293B").encode(text="text:N")
    st.altair_chart(chart(bars + txt, height=height), width="stretch")


def show_prices(res: dict) -> None:
    est = res["priced"]
    at = est.attrs
    total = est["pred_amount"].sum()
    a, b, c = st.columns(3)
    tile(a, "Draft total so far", millions(total), f"{len(est)} items priced")
    share = est.loc[est["tier"] == 0, "pred_amount"].sum() / total if total else 0
    tile(
        b,
        "Priced by the model",
        f"{share:.0%} of the total",
        f"{int((est['tier'] == 0).sum())} items",
    )
    if at.get("saved"):
        how = "prices from the track record's run"
    elif at["reused"]:
        how = "reused this session's run for the same quarter"
    else:
        how = f"ran in {at['fit_seconds']:.1f} s"
    tile(c, short_model(at["model"]), f"{at['model_rows']:,} earlier bids", how)
    top_items_chart(est)
    how_to_read(
        "the ten items with the most dollars at stake. Dark bars are priced by the model; "
        "grey bars from earlier low bids for the same item."
    )


def show_ranges(res: dict) -> None:
    est = res["est"]
    kinds = est["range_kind"].replace("", "none").value_counts()
    a, b, c = st.columns(3)
    tile(
        a, "Model range", f"{kinds.get('model', 0)} items", "80% range from the model's past misses"
    )
    tile(
        b,
        "History range",
        f"{kinds.get('history', 0)} items",
        "10th to 90th percentile of earlier bids",
    )
    tile(
        c,
        "No range",
        f"{kinds.get('none', 0)} items",
        "too few earlier bids",
        "watch" if kinds.get("none", 0) else None,
    )
    widest_chart(est)
    how_to_read(
        "each bar runs from the low to the high amount for the item; the dark tick is the likely "
        "amount. Wide bars are where your own pricing matters most."
    )


def widest_chart(est: pd.DataFrame, n: int = 8, height: int = 260) -> None:
    w = est.dropna(subset=["range_dollars"]).nlargest(n, "range_dollars").copy()
    if w.empty:
        st.info("No item has a price range.")
        return
    w["label"] = [label(r) for r in w.itertuples()]
    y = alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260))
    x = alt.X("low_amount:Q", title="Amount, low to high ($)", axis=alt.Axis(format="$~s"))
    tip = [
        "item_no",
        "description",
        alt.Tooltip("low_amount:Q", format="$,.0f"),
        alt.Tooltip("pred_amount:Q", format="$,.0f", title="likely"),
        alt.Tooltip("high_amount:Q", format="$,.0f"),
    ]
    rng = (
        alt.Chart(w)
        .mark_bar(color="#C7D2E0", height=12, cornerRadius=3)
        .encode(x=x, x2="high_amount:Q", y=y, tooltip=tip)
    )
    mid = alt.Chart(w).mark_tick(color=NAVY, thickness=3, size=16).encode(x="pred_amount:Q", y=y)
    st.altair_chart(chart(rng + mid, height=height), width="stretch")


def show_market(res: dict) -> None:
    mk, job = res["market"], res["job"]
    a, b, c = st.columns(3)
    bd = mk.get("bidders")
    if bd:
        tile(
            a,
            "Expected bidders",
            f"{bd['likely']:.0f}",
            f"likely {bd['low']:.0f} to {bd['high']:.0f}",
        )
    if mk.get("low_bid"):
        lb = mk["low_bid"]
        tile(
            b,
            "Expected low bid (whole job)",
            millions(lb["likely"]),
            f"{pct(mk['spread']['likely'])} vs the engineer's estimate",
        )
        tile(
            c,
            "Likely low bid range",
            f"{millions(lb['low'])} to {millions(lb['high'])}",
            "8 in 10 jobs",
        )
    else:
        tile(b, "Expected low bid", "Needs the estimate", "add the engineer's estimate above")
    rec = mk.get("recent") or {}
    st.caption(
        f"Fitted on {mk['contracts']} earlier Caltrans jobs."
        + (
            f" In the 12 months before this bid, {rec['contracts']} jobs drew a median of "
            f"{rec['median_bidders']:.0f} bidders, and the low bid came in a median "
            f"{pct(rec['median_spread'])} from the engineer's estimate."
            if rec.get("contracts")
            else ""
        )
    )
    rows = [("BidLens draft (item by item)", res["est"]["pred_amount"].sum(), NAVY)]
    if job.engineers_estimate:
        rows.append(("Engineer's estimate", job.engineers_estimate, SLATE))
    if job.actual.get("low_bid"):
        rows.append(("Actual low bid", job.actual["low_bid"], GREEN))
    df = pd.DataFrame(rows, columns=["what", "amount", "color"])
    df["m"] = df["amount"] / 1e6
    y = alt.Y("what:N", sort=None, title=None, axis=alt.Axis(labelLimit=220))
    layers = []
    if mk.get("low_bid"):
        lb = mk["low_bid"]
        band = pd.DataFrame({"lo": [lb["low"] / 1e6], "hi": [lb["high"] / 1e6]})
        layers.append(
            alt.Chart(band).mark_rect(color="#E8F5E9", opacity=0.9).encode(x="lo:Q", x2="hi:Q")
        )
        layers.append(
            alt.Chart(pd.DataFrame({"x": [lb["likely"] / 1e6]}))
            .mark_rule(color=GREEN, strokeDash=[4, 3])
            .encode(x="x:Q")
        )
    pts = (
        alt.Chart(df)
        .mark_circle(size=220, opacity=1)
        .encode(
            x=alt.X(
                "m:Q",
                title="Contract total ($ millions)",
                axis=alt.Axis(format="$,.1f"),
                scale=alt.Scale(zero=False, padding=30),
            ),
            y=y,
            color=alt.Color("color:N", scale=None),
            tooltip=["what", alt.Tooltip("amount:Q", format="$,.0f")],
        )
    )
    st.altair_chart(chart(alt.layer(*layers, pts), height=170), width="stretch")
    how_to_read(
        "the green band is where the low bid should land judging from how far low bids came in "
        "from the engineer's estimate on earlier jobs (dashed line: most likely). The dots are "
        "the item-by-item draft"
        + (
            ", the engineer's estimate and the actual low bid."
            if job.actual.get("low_bid")
            else " and the estimate."
        )
    )


def show_risks(res: dict) -> None:
    rk = res["risks"]
    if rk is None:
        st.markdown(
            "No bid documents for this job, so there is nothing to read for risks. BidLens reads "
            "special provisions and addenda with local models; this copy has the documents of "
            f"the sample job {SAMPLE_JOB} (see the pages under *Sample job with bid documents*)."
        )
        return
    counts = rk["counts"]
    a, b, c = st.columns(3)
    tile(a, "Risks", f"{counts.get('risk', 0)}", "money at stake or a hard stop", "risk")
    tile(b, "To watch", f"{counts.get('watch', 0)}", "limits and deadlines", "watch")
    tile(c, "Notes", f"{counts.get('info', 0)}", "other requirements")
    cat = rk["by_topic"]
    bars = (
        alt.Chart(cat)
        .mark_bar()
        .encode(
            y=alt.Y("topic:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("findings:Q", title="Findings", stack="zero"),
            color=alt.Color(
                "rating:N",
                scale=alt.Scale(domain=["risk", "watch", "info"], range=[RED, AMBER, SLATE]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["topic", "rating", "findings"],
        )
    )
    st.altair_chart(chart(bars, height=260), width="stretch")
    how_to_read("findings read from the bid documents, by topic and rating.")
    for r in rk["top"].itertuples():
        st.markdown(
            f"<div class='bl-card' style='border-color:{RED}; background:#FDECEC'>"
            f"<div class='t'>{html.escape(r.statement)}</div><div class='m'>"
            f"{html.escape(r.category_name)} · {html.escape(str(r.document))}, page {r.page}</div></div>",
            unsafe_allow_html=True,
        )
    st.caption(f"Read by {rk['model']}. Every finding with its page is on the Package page.")


def risks_for(job) -> dict | None:
    if not job.contract_number:
        return None
    items, run, model = findings(job.contract_number)
    if items.empty:
        return None
    f = rate(scored(items))
    by = f.groupby(["category_name", "severity"]).size().reset_index()
    by.columns = ["topic", "rating", "findings"]
    table = items[items["category"] == "closure_damages"]
    return {
        "counts": f["severity"].value_counts().to_dict(),
        "by_topic": by,
        "top": top_watch(f, n=3, table=table),
        "model": model,
    }


STEPS = [
    ("Load the bid items", show_items),
    ("Price each item", show_prices),
    ("Build price ranges", show_ranges),
    ("Market view", show_market),
    ("Risk summary", show_risks),
]


def run_live(job) -> dict:
    res = {"job": job, "seconds": {}}
    t_all = time.perf_counter()

    def step(i: int, title: str, running: str, work) -> None:
        with st.status(f"{i} · {running}", expanded=True) as s:
            t0 = time.perf_counter()
            work()
            res["seconds"][i] = time.perf_counter() - t0
            STEPS[i - 1][1](res)
            s.update(
                label=f"{i} · {title} · {res['seconds'][i]:.1f} s", state="complete", expanded=True
            )

    def items():
        res["items"] = eng.load_items(job)

    def price():
        res["priced"] = eng.price_items(job, res["items"])

    def ranges():
        res["est"] = eng.build_ranges(job, res["priced"])

    def market():
        res["market"] = eng.market_view(job, float(res["est"]["pred_amount"].sum()))

    def risks():
        res["risks"] = risks_for(job)

    step(1, STEPS[0][0], f"Loading {len(job.lines)} bid items…", items)
    if eng.saved_kumo(job) is not None:
        run_text = (
            "Reading Kumo Tabular's prices for this job from the track record's run, and "
            "pricing the other items from earlier bids…"
        )
    elif eng.model_kind == "kumo":
        run_text = "Running Kumo Tabular on every earlier Caltrans low bid " + (
            "(on this free hosted CPU it takes about 1 to 3 minutes)…"
            if hosted()
            else "(in its own process; about 15 to 30 s)…"
        )
    else:
        run_text = "Fitting LightGBM, the lighter online model, on every earlier Caltrans low bid…"
    step(2, STEPS[1][0], run_text, price)
    step(3, STEPS[2][0], "Building low to high ranges…", ranges)
    step(4, STEPS[3][0], "Fitting the market model on earlier jobs…", market)
    step(5, STEPS[4][0], "Summarising risks from the bid documents…", risks)
    res["total_seconds"] = time.perf_counter() - t_all
    return res


def replay(res: dict) -> None:
    for i, (title, show) in enumerate(STEPS, start=1):
        with st.status(
            f"{i} · {title} · {res['seconds'][i]:.1f} s", state="complete", expanded=False
        ):
            show(res)


# ----------------------------------------------------------------- dashboard


def dashboard(res: dict) -> None:
    job, est, mk = res["job"], res["est"], res["market"]
    total = est["pred_amount"].sum()
    when = nice_date(job.bid_date.date().isoformat())
    where = counties(job.county) if job.county else "County not given"
    st.markdown(f"### {html.escape(job.label)}")
    st.caption(
        f"{where} · District {job.district} · Bid {when} · {len(est)} items · "
        f"priced by {est.attrs['model_label']} · {res['total_seconds']:.0f} s"
    )
    if not job.engineers_estimate:
        st.warning(
            "No engineer's estimate was given. Lump-sum items such as mobilization and traffic "
            "control depend on the size of the job, so add the estimate under *Job details* for "
            "sharper prices and the expected low bid."
        )
    cols = st.columns(5)
    low = job.actual.get("low_bid")
    tile(
        cols[0],
        "BidLens draft",
        millions(total),
        f"{pct(total / low - 1)} vs the low bid" if low else "sum of likely prices",
        ("good" if abs(total / low - 1) <= 0.10 else "watch") if low else None,
    )
    ee = job.engineers_estimate
    if ee:
        tile(
            cols[1],
            "Engineer's estimate",
            millions(ee),
            f"{pct(ee / low - 1)} vs the low bid" if low else f"draft is {pct(total / ee - 1)}",
            ("good" if abs(ee / low - 1) <= 0.10 else "watch") if low else None,
        )
    else:
        tile(cols[1], "Engineer's estimate", "Not given")
    if low:
        tile(
            cols[2], "Actual low bid", millions(low), f"{job.actual.get('bidders') or '–'} bidders"
        )
    else:
        tile(cols[2], "Actual low bid", "Not bid yet")
    bd = mk.get("bidders")
    tile(
        cols[3],
        "Expected bidders",
        f"{bd['likely']:.0f}" if bd else "–",
        f"likely {bd['low']:.0f} to {bd['high']:.0f}" if bd else "",
    )
    rk = res.get("risks")
    if rk:
        tile(
            cols[4],
            "Risks in the documents",
            f"{rk['counts'].get('risk', 0)}",
            f"{rk['counts'].get('watch', 0)} more to watch",
            "risk",
        )
    else:
        tile(cols[4], "Risks in the documents", "–", "no documents for this job")
    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Top 10 items by dollar impact**")
        top_items_chart(est, height=290)
        share = est.nlargest(10, "pred_amount")["pred_amount"].sum() / total
        how_to_read(f"these ten items are {share:.0%} of the draft; get them right first.")
    with right:
        st.markdown("**Items with the widest ranges**")
        widest_chart(est, height=290)
        how_to_read("the dollar spread between the low and high price at this job's quantities.")


# ----------------------------------------------------------------- check my bid


def check_my_bid(res: dict) -> None:
    job, est = res["job"], res["est"]
    if "check" not in est or not est["check"].isin(list(STATUS_TEXT)).any():
        return
    mine = job.check_label == "Your unit price"
    st.subheader("Check my bid" if mine else "Check the actual low bid against BidLens")
    if not mine:
        st.caption(
            "This job has been bid, so the low bidder's unit prices are checked here the same way "
            "your own prices would be. Upload a list with a unit price column to check yours."
        )
    e = est[est["check_price"].notna()].copy()
    e["your_amount"] = e["check_price"] * e["quantity"]
    e["diff"] = e["your_amount"] - e["pred_amount"]
    yours, draft = e["your_amount"].sum(), e["pred_amount"].sum()
    n = e["check"].value_counts()
    a, b, c, d = st.columns(4)
    who = "Your total" if mine else "Low bid total"
    tile(a, who, millions(yours), f"{pct(yours / draft - 1)} vs BidLens on these items")
    tile(b, "Inside the range", f"{n.get('inside', 0)} items", "", "good")
    tile(
        c,
        "Above the range",
        f"{n.get('above', 0)} items",
        "priced high: check",
        "risk" if n.get("above") else None,
    )
    tile(
        d,
        "Below the range",
        f"{n.get('below', 0)} items",
        "priced low: check",
        "watch" if n.get("below") else None,
    )
    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Each price against its range** (15 largest items)")
        r = e[e["check"].isin(list(STATUS_TEXT))].nlargest(15, "pred_amount").copy()
        r["label"] = [label(x) for x in r.itertuples()]
        r["lo"], r["hi"] = r["low"] / r["pred_unit_price"], r["high"] / r["pred_unit_price"]
        r["you"] = (r["check_price"] / r["pred_unit_price"]).clip(0.05, 20)
        r["status"] = r["check"].map(STATUS_TEXT)
        y = alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=240))
        scale = alt.Scale(type="log", domain=[0.1, 10], clamp=True)
        x = alt.X(
            "lo:Q",
            title="Price ÷ BidLens likely price (log scale)",
            scale=scale,
            axis=alt.Axis(values=[0.1, 0.25, 0.5, 1, 2, 4, 10], format="~g"),
        )
        rng = (
            alt.Chart(r)
            .mark_bar(color="#DCE3EC", height=12, cornerRadius=3)
            .encode(x=x, x2="hi:Q", y=y)
        )
        one = (
            alt.Chart(pd.DataFrame({"x": [1.0]}))
            .mark_rule(color=NAVY, strokeDash=[3, 3])
            .encode(x=alt.X("x:Q", scale=scale))
        )
        dot = (
            alt.Chart(r)
            .mark_circle(size=110, opacity=1)
            .encode(
                x=alt.X("you:Q", scale=scale),
                y=y,
                color=alt.Color(
                    "status:N",
                    scale=alt.Scale(
                        domain=list(STATUS_TEXT.values()), range=list(STATUS_COLOR.values())
                    ),
                    legend=alt.Legend(orient="top", title=None),
                ),
                tooltip=[
                    "item_no",
                    "description",
                    alt.Tooltip("check_price:Q", format="$,.2f", title=job.check_label),
                    alt.Tooltip("low:Q", format="$,.2f"),
                    alt.Tooltip("pred_unit_price:Q", format="$,.2f", title="likely"),
                    alt.Tooltip("high:Q", format="$,.2f"),
                ],
            )
        )
        st.altair_chart(chart(rng + one + dot, height=380), width="stretch")
        how_to_read(
            "grey bars are BidLens's low to high range, scaled so the likely price is 1 (dashed line). "
            "Dots are the checked prices: green inside, red above, blue below."
        )
    with right:
        st.markdown("**What moves the total most**")
        m = e.reindex(e["diff"].abs().sort_values(ascending=False).index).head(10).copy()
        m["label"] = [label(x) for x in m.itertuples()]
        m["side"] = np.where(m["diff"] > 0, "Higher", "Lower")
        m["text"] = [("+" if v > 0 else "") + short_money(v) for v in m["diff"]]
        enc = alt.Chart(m).encode(
            y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=240)),
            x=alt.X(
                "diff:Q",
                title="Checked amount minus BidLens likely amount ($)",
                axis=alt.Axis(format="$~s"),
            ),
        )
        bars = enc.mark_bar(cornerRadius=3).encode(
            color=alt.Color(
                "side:N",
                scale=alt.Scale(domain=["Higher", "Lower"], range=[RED, "#2563EB"]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["item_no", "description", alt.Tooltip("diff:Q", format="$,.0f")],
        )
        txt = enc.mark_text(align="left", dx=4, color="#1E293B").encode(text="text:N")
        st.altair_chart(chart(bars + txt, height=380), width="stretch")
        how_to_read(
            "the ten items where the checked price differs most from BidLens in dollars (red: "
            f"higher than BidLens, blue: lower). Together they add {short_money(m['diff'].sum())}; "
            f"all items together add {short_money(yours - draft)}."
        )
    flagged = e[e["check"].isin(["above", "below"])].sort_values("diff", key=abs, ascending=False)
    if len(flagged):
        with st.expander(f"{len(flagged)} prices outside the range, largest dollar gap first"):
            show = flagged[
                [
                    "item_no",
                    "description",
                    "unit",
                    "quantity",
                    "check_price",
                    "low",
                    "pred_unit_price",
                    "high",
                    "check",
                    "diff",
                ]
            ]
            st.dataframe(
                show,
                hide_index=True,
                width="stretch",
                column_config={
                    "item_no": "Item",
                    "description": "Description",
                    "unit": "Unit",
                    "quantity": st.column_config.NumberColumn("Quantity", format="%,.0f"),
                    "check_price": st.column_config.NumberColumn(job.check_label, format="dollar"),
                    "low": st.column_config.NumberColumn("Low", format="dollar"),
                    "pred_unit_price": st.column_config.NumberColumn("Likely", format="dollar"),
                    "high": st.column_config.NumberColumn("High", format="dollar"),
                    "check": "Check",
                    "diff": st.column_config.NumberColumn("Dollar gap", format="dollar"),
                },
            )


# ----------------------------------------------------------------- one item


def item_explorer(res: dict) -> None:
    job, est = res["job"], res["est"]
    st.subheader("Look at one item")
    e = est.sort_values("pred_amount", ascending=False).reset_index(drop=True)
    ranged = e.index[e["low"].notna()]
    i = st.selectbox(
        "Item",
        range(len(e)),
        index=int(ranged[0]) if len(ranged) else 0,
        format_func=lambda k: f"{label(e.iloc[k])} · {short_money(e.iloc[k]['pred_amount'])}",
        key="item_pick",
    )
    r = e.iloc[i]
    a, b, c = st.columns(3)
    tile(
        a,
        "Likely unit price",
        money(r["pred_unit_price"], cents=True),
        f"per {r['unit']} · {r['source']}",
    )
    if pd.notna(r["low"]):
        kind = (
            "model range" if r["range_kind"] == "model" else "earlier bids, 10th to 90th percentile"
        )
        tile(b, "Low to high", f"{short_money(r['low'])} to {short_money(r['high'])}", kind)
    else:
        tile(b, "Low to high", "No range", "too few earlier bids")
    if "check_price" in r and pd.notna(r["check_price"]):
        st_ = r["check"]
        tile(
            c,
            job.check_label,
            money(r["check_price"], cents=True),
            STATUS_TEXT.get(st_, st_),
            {"inside": "good", "above": "risk", "below": "watch"}.get(st_),
        )
    h = eng.price_history(job, r)
    left, right = st.columns([3, 2], gap="large")
    with left:
        if h.empty:
            st.info(
                "No earlier low bids for this item, so it is priced from the typical price for "
                "its item family and unit. Check this price yourself."
            )
        else:
            pts = (
                alt.Chart(h)
                .mark_circle(color=SLATE, opacity=0.6, size=40)
                .encode(
                    x=alt.X("bid_open_date:T", title="Bid date"),
                    y=alt.Y(
                        "unit_price:Q",
                        title=f"Low bid per {r['unit']} (this job's dollars, log)",
                        scale=alt.Scale(type="log"),
                        axis=alt.Axis(format="$~s"),
                    ),
                    tooltip=[
                        alt.Tooltip("bid_open_date:T"),
                        alt.Tooltip("quantity:Q", format=",.0f"),
                        alt.Tooltip("unit_price:Q", format="$,.2f"),
                    ],
                )
            )
            layers = [pts]
            ref = pd.DataFrame({"y": [r["pred_unit_price"]]})
            if pd.notna(r["low"]):
                band = pd.DataFrame({"lo": [r["low"]], "hi": [r["high"]]})
                layers.insert(
                    0,
                    alt.Chart(band)
                    .mark_rect(color="#DCE3EC", opacity=0.6)
                    .encode(y="lo:Q", y2="hi:Q"),
                )
            layers.append(alt.Chart(ref).mark_rule(color=NAVY, strokeWidth=2).encode(y="y:Q"))
            st.altair_chart(chart(alt.layer(*layers), height=280), width="stretch")
            how_to_read(
                f"each dot is an earlier Caltrans low bid for {r['item_code']}, brought to this "
                "job's bid date with the cost index. The line is BidLens's likely price and the band "
                "its range."
            )
    with right:
        comps = eng.comparables(job, r) if r["in_scope"] else pd.DataFrame()
        if len(comps):
            st.markdown("**10 most comparable earlier bids**")
            st.dataframe(
                comps[
                    [
                        "contract_number",
                        "bid_open_date",
                        "quantity",
                        "unit_price_in_query_dollars",
                        "source",
                    ]
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "contract_number": "Contract",
                    "bid_open_date": st.column_config.DateColumn("Bid date"),
                    "quantity": st.column_config.NumberColumn("Qty", format="%,.0f"),
                    "unit_price_in_query_dollars": st.column_config.NumberColumn(
                        "Price, today's $", format="dollar"
                    ),
                    "source": st.column_config.LinkColumn("Caltrans", display_text="open"),
                },
            )
            st.caption(
                "Nearest by quantity, date, district and job size. Low bids only; no bidder names."
            )


def downloads(res: dict) -> None:
    from bidlens.export import evaluation_workbook

    job, est = res["job"], res["est"]
    name = (job.contract_number or "my_bid").replace(" ", "_")
    st.subheader("Take it with you")
    a, b = st.columns(2)
    a.download_button(
        "Download the draft estimate (Excel)",
        evaluation_workbook(job, est, res["market"]),
        file_name=f"bidlens_{name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    cols = [
        "item_no",
        "item_code",
        "description",
        "unit",
        "quantity",
        "low",
        "pred_unit_price",
        "high",
        "pred_amount",
        "source",
        "range_kind",
    ] + (["check_price", "check"] if "check" in est else [])
    b.download_button(
        "Download as CSV",
        est[cols].to_csv(index=False).encode(),
        file_name=f"bidlens_{name}.csv",
        mime="text/csv",
    )


def results(res: dict) -> None:
    check_my_bid(res)
    item_explorer(res)
    downloads(res)
    bt = stage("22_live_evaluation", "results.json")
    tr = stage("13_model_comparison", "results.json")
    at = res["est"].attrs
    if at["model"] == "lightgbm" and bt:
        h = bt["headline"]
        st.caption(
            f"Priced by LightGBM, the lighter online model. On {h['contracts']} past "
            f"jobs it was closer to the low bid than the engineer's estimate {h['live_closer_than_ee']:.0%} "
            f"of the time (typical miss {h['live_median_abs_error']:.0%}). BidLens's production model, "
            f"Kumo Tabular, does better ({h['kumo_closer_than_ee']:.0%}, {h['kumo_median_abs_error']:.0%}) "
            "and runs on a laptop. See Track record."
        )
    elif tr:
        h = tr["contract_level"]["production"]["headline"]
        how = (
            "Kumo Tabular's prices for this job are the ones in the track record, computed ahead "
            "on a laptop; the other steps ran just now. "
            if at.get("saved")
            else "Priced by Kumo Tabular, run just now. "
        )
        st.caption(
            how + f"On {h['contracts']} past jobs it was closer to the low bid than "
            f"the engineer's estimate {h['bidlens_closer_share']:.0%} of the time. See Track record. "
            "A starting point for the estimator, not a bid."
        )


# ----------------------------------------------------------------- run or show

if go and spec is not None:
    job = eng.contract_job(spec[1], spec[2]) if spec[0] == "contract" else spec[1]
    st.session_state.pop("item_pick", None)
    res = run_live(job)
    st.session_state["result"] = res
    with dash:
        dashboard(res)
    results(res)
elif "result" in st.session_state:
    res = st.session_state["result"]
    with dash:
        dashboard(res)
    st.markdown("**How this was computed, step by step** (open a step to see its numbers)")
    replay(res)
    results(res)
else:
    st.info(
        "Choose a job or upload a list, then press **Evaluate**. Each step runs for real on "
        "Caltrans bid history and shows its result as it finishes."
    )
