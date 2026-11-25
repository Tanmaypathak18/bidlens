"""BidLens: the app's entry point and page menu.

Run with `uv run streamlit run app/Home.py`. The landing page is Evaluate, which prices a
past Caltrans job or an uploaded bid item list live; the sample package pages are the deep
dive on one job with its bid documents.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="BidLens", page_icon="📐", layout="wide")

pages = {
    "Evaluate": [
        st.Page("views/evaluate.py", title="Evaluate a bid", icon="⚡", default=True),
        st.Page("views/track_record.py", title="Track record", icon="🎯",
                url_path="track-record"),
    ],
    "Sample job with bid documents": [
        st.Page("views/overview.py", title="Overview", icon="🏠", url_path="overview"),
        st.Page("views/package.py", title="Package", icon="📄", url_path="package"),
        st.Page("views/prices.py", title="Prices", icon="💲", url_path="prices"),
        st.Page("views/market.py", title="Market", icon="📈", url_path="market"),
        st.Page("views/export.py", title="Export", icon="⬇️", url_path="export"),
    ],
}  # fmt: skip
st.navigation(pages).run()
