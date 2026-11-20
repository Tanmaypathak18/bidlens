"""Look and feel shared by every page (decision D-066): colors, header, risk ratings,
page chips that open the PDF page, and chart defaults."""

from __future__ import annotations

import html
import os
import re
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from bidlens.documents.review import support

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "data" / "raw" / "bid_package"

NAVY = "#1F3A5F"
SLATE = "#64748B"
LIGHT = "#CBD5E1"
GREEN, AMBER, RED = "#2E7D32", "#B26A00", "#C62828"
TINT = {"risk": "#FDECEC", "watch": "#FFF4E0", "info": "#EEF2F7", "good": "#E8F5E9"}
COLOR = {"risk": RED, "watch": AMBER, "info": SLATE, "good": GREEN}
LABEL = {"risk": "Risk", "watch": "Watch", "info": "Note", "good": "Good"}

COUNTIES = {
    "ALA": "Alameda",
    "CC": "Contra Costa",
    "MRN": "Marin",
    "NAP": "Napa",
    "SF": "San Francisco",
    "SM": "San Mateo",
    "SCL": "Santa Clara",
    "SOL": "Solano",
    "SON": "Sonoma",
    "MON": "Monterey",
    "SBT": "San Benito",
    "SCR": "Santa Cruz",
    "SLO": "San Luis Obispo",
    "SB": "Santa Barbara",
}

CSS = f"""
<style>
.block-container {{padding-top: 1.6rem; max-width: 1200px;}}
.bl-head {{border-bottom: 1px solid {LIGHT}; padding-bottom: .6rem; margin-bottom: 1rem;}}
.bl-head h1 {{font-size: 1.55rem; margin: 0 0 .15rem 0; color: {NAVY};}}
.bl-sub {{color: {SLATE}; font-size: .95rem;}}
.bl-badge {{display:inline-block; background:{TINT["good"]}; color:{GREEN};
  border:1px solid #B7DDB9; border-radius: 999px; padding: 1px 10px; font-size:.78rem;
  margin-left:.4rem; white-space:nowrap;}}
.bl-tile {{border:1px solid {LIGHT}; border-radius:10px; padding:.9rem 1rem; height:100%;}}
.bl-tile .k {{color:{SLATE}; font-size:.85rem;}}
.bl-tile .v {{font-size:clamp(1.25rem, 2.6vw, 1.9rem); font-weight:700; color:{NAVY};
  line-height:1.2; white-space:nowrap;}}
.bl-sample {{background:#EEF2F7; border:1px solid {LIGHT}; border-radius:8px;
  padding:.45rem .8rem; margin:-.4rem 0 1rem 0; font-size:.88rem; color:#1E293B;}}
.bl-tile .d {{font-size:.85rem; margin-top:.2rem;}}
.bl-card {{border-left:5px solid; border-radius:6px; padding:.55rem .8rem; margin:.15rem 0;}}
.bl-card .t {{font-size:.95rem;}}
.bl-card .m {{color:{SLATE}; font-size:.8rem; margin-top:.2rem;}}
.bl-pill {{display:inline-block; border-radius:999px; padding:0 8px; font-size:.72rem;
  font-weight:600; margin-right:.4rem; color:white;}}
.bl-how {{color:{SLATE}; font-size:.82rem; margin-top:-.4rem;}}
</style>
"""


def hosted() -> bool:
    """True on a Hugging Face Space (the demo, D-072), which sets SPACE_ID."""
    return bool(os.environ.get("SPACE_ID"))


def precomputed(contract: str) -> bool:
    """True when the findings come from the committed sample, not a run on this computer."""
    from bidlens.sample import SAMPLE, docs_dir

    return docs_dir(contract) == SAMPLE / contract


def setup(title: str) -> None:
    st.set_page_config(page_title=f"BidLens · {title}", page_icon="📐", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def counties(code: str) -> str:
    names = [COUNTIES.get(c.strip().upper(), c.strip()) for c in str(code).split(",")]
    if len(names) == 1:
        return f"{names[0]} County"
    return ", ".join(names[:-1]) + f" and {names[-1]} counties"


def nice_date(d: str) -> str:
    x = date.fromisoformat(d)
    return x.strftime("%a, %b %-d, %Y")


def page_header(s: dict, page: str) -> None:
    """Contract, work, location, bid date and the runs-locally badge, on every page."""
    work = s.get("work") or s["type_of_work"].capitalize()
    badge = (
        "Demo on public sample data · no bid documents uploaded"
        if hosted()
        else "Runs locally · documents never leave this computer"
    )
    where = f"{counties(s['county'])} · {s['routes']}" if s.get("routes") else counties(s["county"])
    st.markdown(
        f"""<div class="bl-head"><h1>{html.escape(page)} · Contract {s["contract"]}</h1>
<div class="bl-sub"><b>{html.escape(work)}</b><br>{html.escape(where)} · District
{s["district"]} · Bids open {nice_date(s["bid_open_date"])}
<span class="bl-badge">{badge}</span></div></div>""",
        unsafe_allow_html=True,
    )
    notes = []
    if s.get("low_bid_cost"):
        notes.append(
            f"""<b>Sample job, already bid.</b> Bids for {s["contract"]} opened on
{nice_date(s["bid_open_date"])} and the results are public. BidLens priced it only from bids
opened before that date; the actual low bid is shown to check BidLens against the real
result, and never feeds the draft."""
        )
    if precomputed(s["contract"]):
        notes.append(
            """<b>Document findings were pre-computed on a laptop with local models</b>
(qwen3:8b and llama3.1:8b through Ollama, plus plain pattern rules) and saved with this
sample. This copy of the app shows those saved results; it does not run a model."""
        )
    if notes:
        st.markdown(f'<div class="bl-sample">{"<br>".join(notes)}</div>', unsafe_allow_html=True)


def tile(col, label: str, value: str, detail: str = "", status: str | None = None) -> None:
    color = COLOR.get(status, SLATE) if status else SLATE
    col.markdown(
        f"""<div class="bl-tile"><div class="k">{html.escape(label)}</div>
<div class="v">{html.escape(value)}</div>
<div class="d" style="color:{color}">{html.escape(detail)}</div></div>""",
        unsafe_allow_html=True,
    )


def how_to_read(text: str) -> None:
    st.markdown(
        f'<div class="bl-how">How to read this: {html.escape(text)}</div>', unsafe_allow_html=True
    )


# ----------------------------------------------------------------- risk ratings

RISK_WORDS = re.compile(
    r"liquidated damages|penalt|withh[oe]ld|deduct|forfeit|reject|mandatory|hazardous|"
    r"class i\b|type z-2|at (?:your|the contractor'?s) (?:own )?(?:cost|expense)|"
    r"does not pay|not paid|no payment|stop (?:all )?work|late (?:re)?open",
    re.I,
)
WATCH_WORDS = re.compile(
    r"\b\d+ (?:business |working |calendar )?(?:days?|hours?|minutes?)\b|before|within|"
    r"season|survey|notif|notice|only|not allowed|prohibit|do not|must not|no more than|"
    r"at least|limit|restrict|closure|night|permit|monitor|training|submit",
    re.I,
)
MONEY = re.compile(r"\$\s?\d")
# Money coming back (a withhold returned or released) is a date to watch, not a risk.
RELIEF = re.compile(r"\b(?:returns?|releases?|refunds?)\b[^.]*\bwithh[oe]ld", re.I)
CATEGORY_ORDER = [
    "time_damages",
    "traffic",
    "hazardous",
    "environmental",
    "payment",
    "bid_requirements",
    "geotechnical",
    "utilities",
    "submittals",
    "scope",
]


def severity(statement: str, value: str = "", evidence: str = "") -> str:
    """risk / watch / info, by plain keyword rules (D-066), not by a model."""
    text = f"{statement} {value}"
    if RELIEF.search(text):
        return "watch"
    if RISK_WORDS.search(text) or (MONEY.search(text) and RISK_WORDS.search(evidence)):
        return "risk"
    if WATCH_WORDS.search(text):
        return "watch"
    return "info"


def rate(items: pd.DataFrame) -> pd.DataFrame:
    if items.empty:
        return items.assign(severity=[])
    return items.assign(
        severity=[severity(r.statement, r.value, r.evidence) for r in items.itertuples()]
    )


def damages_summary(table: pd.DataFrame) -> pd.DataFrame:
    """One finding that sums up the late closure damages table (read by code)."""
    if table.empty:
        return table
    vals = [int(x.replace("$", "").replace(",", ""))
            for t in table["statement"] for x in re.findall(r"\$[\d,]+", t)]  # fmt: skip
    first = table.iloc[0]
    return pd.DataFrame([{
        **first.to_dict(),
        "category": "time_damages",
        "category_name": "Working days and liquidated damages",
        "source": "pattern",
        "statement": f"Reopening a lane or ramp closure late costs ${min(vals):,} to "
                     f"${max(vals):,} in liquidated damages for every 10 minutes, depending on "
                     f"the route ({len(table)} routes in the table).",
        "value": "",
        "as_quoted": False,
    }])  # fmt: skip


def top_watch(items: pd.DataFrame, n: int = 5, table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Risk findings, one per category, in category order: exact facts read by code first,
    then model statements that passed the quote check (D-071), then those with a value."""
    if table is not None and len(table):
        items = pd.concat([damages_summary(table), items], ignore_index=True)
    r = rate(items)
    r = r[r["severity"] == "risk"].copy()
    if r.empty:
        return r
    r["cat_rank"] = r["category"].map({c: i for i, c in enumerate(CATEGORY_ORDER)}).fillna(99)
    r["has_value"] = (r["value"].fillna("") != "").astype(int)
    r["money"] = r["statement"].str.contains(MONEY).astype(int)
    # Facts read by plain code (pattern rules) are exact, so they come first.
    src = r["source"] if "source" in r else pd.Series("model", index=r.index)
    r["exact"] = (src.fillna("model") == "pattern").astype(int)
    r["support"] = [support(a, b) for a, b in zip(r["statement"], r["evidence"], strict=True)]
    quoted = r["as_quoted"] if "as_quoted" in r else pd.Series(False, index=r.index)
    r = r[(r["exact"] == 1) | ~quoted.fillna(False).astype(bool)]
    r = r.sort_values(
        ["cat_rank", "exact", "support", "money", "has_value"],
        ascending=[True, False, False, False, False],
    )
    first = r.drop_duplicates("category")
    rest = r.drop(first.index)
    return pd.concat([first, rest]).head(n)


# ----------------------------------------------------------------- pages of the PDF


@st.cache_data(show_spinner=False)
def page_image(contract: str, file: str, page: int) -> bytes | None:
    import io

    path = PACKAGES / contract / file
    if not path.exists():
        return None
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    img = pdf[page - 1].render(scale=1.6).to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@st.dialog("Source page", width="large")
def show_page(contract: str, file: str, page: int, quote: str, where: str) -> None:
    st.caption(where)
    st.markdown(f"> {quote}")
    png = page_image(contract, file, page)
    if png is None:
        st.info(
            "The bid package PDF is not included here, so the page can't be shown. "
            "The quote above is copied word for word from it."
        )
    else:
        st.image(png, width=760)


def short_doc(title: str) -> str:
    """Plain short names for the package documents."""
    t = str(title)
    if t.startswith("Notice to Bidders"):
        return "Special provisions"
    if t.startswith("Special Provisions"):
        return "Special provisions"
    return t.replace("Information Handout", "Information handout")


def shows_value(statement: str, value: str) -> bool:
    """Show the value in bold only when the statement doesn't already say it."""
    if not value:
        return False
    nums = re.findall(r"\d[\d,.]*", value)
    plain = statement.replace(",", "")
    if nums and all(n.replace(",", "").rstrip(".") in plain for n in nums):
        return False
    return value.lower() not in statement.lower()


def card(contract: str, r, key: str, where: str) -> None:
    """One finding as a colored card with its page chip."""
    sev = getattr(r, "severity", "info")
    value = f" <b>({html.escape(str(r.value))})</b>" if shows_value(r.statement, r.value) else ""
    if getattr(r, "as_quoted", False):
        # The summary did not match its quote closely, so the document's words are shown.
        where = f"Quoted as written · {where}"
    c1, c2 = st.columns([12, 1.6], vertical_alignment="center")
    c1.markdown(
        f"""<div class="bl-card" style="border-color:{COLOR[sev]}; background:{TINT[sev]}">
<div class="t"><span class="bl-pill" style="background:{COLOR[sev]}">{LABEL[sev]}</span>
{html.escape(r.statement)}{value}</div>
<div class="m">{html.escape(where)}</div></div>""",
        unsafe_allow_html=True,
    )
    if c2.button(f"p. {r.page}", key=key, help="Open this page of the document"):
        show_page(contract, r.file, int(r.page), r.evidence, where)


# ----------------------------------------------------------------- charts


def chart(c: alt.Chart, height: int = 260) -> alt.Chart:
    return (
        c.properties(height=height)
        .configure_axis(
            labelColor=SLATE,
            titleColor=SLATE,
            gridColor="#EDF0F4",
            labelFontSize=12,
            titleFontSize=12,
        )
        .configure_view(strokeWidth=0)
        .configure_legend(labelColor=SLATE, titleColor=SLATE)
    )
