"""Step 4.1: every app page renders without errors on the prepared sample package."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))  # Streamlit puts the main script's folder on the path
READY = (ROOT / "data" / "interim" / "app" / "04-0W0504" / "summary.json").exists()
PAGES = [
    "app/Home.py",
    "app/pages/1_Package.py",
    "app/pages/2_Prices.py",
    "app/pages/3_Market.py",
    "app/pages/4_Export.py",
]


@pytest.mark.skipif(not READY, reason="run `python -m bidlens.estimate 04-0W0504` first")
@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
    assert not at.exception, at.exception
    # Every page opens with the shared header naming the contract (D-066).
    assert any("Contract 04-0W0504" in m.value for m in at.markdown)
