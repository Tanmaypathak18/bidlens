"""Shared loading and formatting for the BidLens app pages (decision D-064)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bidlens.documents.extract import DEFAULT_RUN, RUN_FALLBACKS, TABLES  # noqa: E402

APP = ROOT / "data" / "interim" / "app"
DOCS = ROOT / "data" / "interim" / "docs"

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
    return sorted(p.name for p in APP.glob("*") if (p / "summary.json").exists())


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
    return json.loads((APP / contract / "summary.json").read_text())


@st.cache_data
def estimate(contract: str) -> pd.DataFrame:
    return pd.read_parquet(APP / contract / "estimate.parquet")


@st.cache_data
def comparables(contract: str) -> pd.DataFrame:
    p = APP / contract / "comparables.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def findings(contract: str) -> tuple[pd.DataFrame, str, str]:
    """Findings of the default extraction run: (items, run name, model label)."""
    for run in (DEFAULT_RUN, *RUN_FALLBACKS):
        p = DOCS / contract / f"extraction_{run}.json"
        if p.exists():
            res = json.loads(p.read_text())
            return pd.DataFrame(res["items"]), run, res.get("model", run)
    return pd.DataFrame(), "", ""


def scored(items: pd.DataFrame) -> pd.DataFrame:
    return items[~items["category"].isin(TABLES)] if len(items) else items


def money(x: float | None, cents: bool = False) -> str:
    if x is None or pd.isna(x):
        return "–"
    return f"${x:,.2f}" if cents else f"${x:,.0f}"


def pct(x: float | None) -> str:
    return "–" if x is None or pd.isna(x) else f"{100 * x:+.0f}%"


def cite(r) -> str:
    sec = f", section {r.section_number}" if getattr(r, "section_number", "") else ""
    printed = f" (printed page {r.printed_page})" if getattr(r, "printed_page", "") else ""
    return f"{r.document}, PDF page {r.page}{printed}{sec}"


def header(title: str) -> str | None:
    st.set_page_config(page_title=f"BidLens · {title}", layout="wide")
    contract = pick_package()
    st.sidebar.caption(
        "BidLens runs on this computer. Bid documents never leave it, and no paid service is used."
    )
    return contract
