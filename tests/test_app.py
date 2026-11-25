"""Step 4.1: every app page renders without errors on the prepared sample package."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))  # Streamlit puts the main script's folder on the path
PAGES = [
    "app/views/overview.py",
    "app/views/package.py",
    "app/views/prices.py",
    "app/views/market.py",
    "app/views/export.py",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
    assert not at.exception, at.exception
    # Every page opens with the shared header naming the contract.
    assert any("Contract 04-0W0504" in m.value for m in at.markdown)


def test_home_labels_the_sample_and_keeps_tiles_short():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app/views/overview.py"), default_timeout=60).run()
    text = " ".join(m.value for m in at.markdown)
    assert "Sample job, already bid" in text
    assert "$14.54M" in text and "$14,539,427" not in text  # short amounts in tiles
    assert "Why 178" in " ".join(c.value for c in at.caption)


def test_market_explains_the_two_low_bid_views():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app/views/market.py"), default_timeout=60).run()
    text = " ".join(m.value for m in at.markdown)
    assert "Two ways to estimate the low bid" in text and "$14.54M" in text


def test_hosted_demo_does_not_claim_to_run_locally(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("SPACE_ID", "user/bidlens")  # set by Hugging Face Spaces
    at = AppTest.from_file(str(ROOT / "app/views/overview.py"), default_timeout=60).run()
    text = " ".join(m.value for m in at.markdown)
    assert "Demo on public sample data" in text
    assert "documents never leave this computer" not in text
    links = " ".join(m.value for m in at.sidebar.markdown)
    assert "github.com/Tanmaypathak18/bidlens" in links  # the demo links back to the code


def test_landing_page_is_evaluate():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app/Home.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("Evaluate a bid" in m.value for m in at.markdown)


def test_evaluate_runs_a_past_job_live(monkeypatch):
    """Pressing Evaluate runs all five steps and shows the dashboard and the bid check."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("BIDLENS_MODEL", "lightgbm")  # fast; Kumo runs in its own process
    at = AppTest.from_file(str(ROOT / "app/views/evaluate.py"), default_timeout=180).run()
    assert not at.exception, at.exception
    at.button[0].click().run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Contract 04-0W0504" in text  # dashboard heading
    assert "BidLens draft" in text and "Expected bidders" in text
    assert "Risks in the documents" in text  # the sample job has documents
    assert any("Check the actual low bid" in h.value for h in at.subheader)


def test_track_record_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app/views/track_record.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "178" in text and "Second bid above the low bid" in text
