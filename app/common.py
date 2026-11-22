"""Shared loading and formatting for the BidLens app pages."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bidlens.documents.extract import DEFAULT_RUN, RUN_FALLBACKS, TABLES  # noqa: E402
from bidlens.sample import app_dir, docs_dir  # noqa: E402

APP = ROOT / "data" / "interim" / "app"
SAMPLE = ROOT / "data" / "sample" / "app"

TOPIC_ORDER = [
    "scope",
    "time_damages",
    "traffic",
    "environmental",
    "hazardous",
    "geotechnical",
    "utilities",
    "bid_requirements",
    "submittals",
    "payment",
]


def packages() -> list[str]:
    # Packages built on this computer, plus the committed sample.
    found = {p.name for d in (APP, SAMPLE) for p in d.glob("*") if (p / "summary.json").exists()}
    return sorted(found)


def pick_package() -> str | None:
    """The package picker shown in the sidebar of every page."""
    pk = packages()
    if not pk:
        st.error(
            "No bid package has been prepared yet. Run "
            "`uv run python -m bidlens.estimate 04-0W0504` first."
        )
        return None
    if "contract" not in st.session_state or st.session_state["contract"] not in pk:
        st.session_state["contract"] = pk[0]
    return st.sidebar.selectbox("Bid package", pk, key="contract")


@st.cache_data
def summary(contract: str) -> dict:
    return json.loads((app_dir(contract) / "summary.json").read_text())


@st.cache_data
def estimate(contract: str) -> pd.DataFrame:
    return pd.read_parquet(app_dir(contract) / "estimate.parquet")


@st.cache_data
def comparables(contract: str) -> pd.DataFrame:
    p = app_dir(contract) / "comparables.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def findings(contract: str) -> tuple[pd.DataFrame, str, str]:
    """Findings of the default extraction run: (items, run name, model label)."""
    for run in (DEFAULT_RUN, *RUN_FALLBACKS):
        p = docs_dir(contract) / f"extraction_{run}.json"
        if p.exists():
            from bidlens.documents.report import mask
            from bidlens.documents.review import tidy

            res = json.loads(p.read_text())
            # No phone numbers or email addresses on screen either.
            items = mask(pd.DataFrame(res["items"]))
            # Findings are checked against their quotes before they are shown.
            table = items["category"].isin(TABLES)
            items = pd.concat([tidy(items[~table]), items[table]], ignore_index=True)
            items["as_quoted"] = items["as_quoted"].fillna(False).astype(bool)
            return items, run, res.get("model", run)
    return pd.DataFrame(), "", ""


def scored(items: pd.DataFrame) -> pd.DataFrame:
    return items[~items["category"].isin(TABLES)] if len(items) else items


def money(x: float | None, cents: bool = False) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"${x:,.2f}" if cents else f"${x:,.0f}"


def millions(x: float | None) -> str:
    """$14.54M: for number tiles, which must not wrap on a phone. Tables keep full amounts."""
    return "–" if x is None or pd.isna(x) else f"${x / 1e6:,.2f}M"


def short_money(x: float | None) -> str:
    """$950, $12.5k, $1.2M: for tight table columns."""
    if x is None or pd.isna(x):
        return "—"
    if x >= 1e6:
        return f"${x / 1e6:,.1f}M"
    if x >= 1e4:
        return f"${x / 1e3:,.0f}k"
    if x >= 100:
        return f"${x:,.0f}"
    return f"${x:,.2f}"


def pct(x: float | None) -> str:
    return "–" if x is None or pd.isna(x) else f"{100 * x:+.0f}%"


def cite(r) -> str:
    sec = f", section {r.section_number}" if getattr(r, "section_number", "") else ""
    printed = f" (printed page {r.printed_page})" if getattr(r, "printed_page", "") else ""
    return f"{r.document}, PDF page {r.page}{printed}{sec}"


REPO_URL = "https://github.com/Tanmaypathak18/bidlens"


def header(title: str) -> str | None:
    """Page setup, the package picker and the shared page header."""
    from design import page_header, setup

    setup(title)
    contract = pick_package()
    from design import hosted

    st.sidebar.caption(
        "Demo: the committed sample package only. No paid service is used."
        if hosted()
        else "No paid service is used. Bid documents stay on this computer."
    )
    st.sidebar.markdown(f"[Source code and method on GitHub]({REPO_URL})")
    if contract:
        page_header(summary(contract), title)
    return contract


@st.cache_data
def history(contract: str) -> pd.DataFrame:
    p = app_dir(contract) / "history.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def track_record() -> dict:
    """The stage 13 headline: BidLens totals vs the engineer's estimate on past contracts."""
    p = ROOT / "outputs" / "13_model_comparison" / "results.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())["contract_level"]["production"]["headline"]
